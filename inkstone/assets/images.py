from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import AssetError

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ImageInfo:
    format: str
    width: int
    height: int
    mime: str
    animated: bool = False

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0

    def as_attrs(self) -> str:
        """`width="..." height="..."`, ready to drop into an <img> tag."""
        return f'width="{self.width}" height="{self.height}"'


class _Corrupt(Exception):
    pass


def _png(data: bytes) -> ImageInfo:
    if data[12:16] != b"IHDR":
        raise _Corrupt("PNG does not start with an IHDR chunk")
    width, height = struct.unpack(">II", data[16:24])
    # APNG announces itself with an acTL chunk ahead of the pixel data
    animated = False
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        if kind == b"acTL":
            animated = True
            break
        if kind in (b"IDAT", b"IEND"):
            break
        pos += 12 + length
    return ImageInfo("png", width, height, "image/png", animated)


# start-of-frame markers; C4, C8 and CC in the same range are something else
_SOF_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def _exif_orientation(tiff: bytes) -> int:
    if tiff[:2] == b"II":
        order = "<"
    elif tiff[:2] == b"MM":
        order = ">"
    else:
        return 1
    try:
        magic, offset = struct.unpack(order + "HI", tiff[2:8])
        if magic != 42:
            return 1
        (count,) = struct.unpack(order + "H", tiff[offset : offset + 2])
        for i in range(count):
            entry = tiff[offset + 2 + 12 * i : offset + 14 + 12 * i]
            tag, _kind, _count, value = struct.unpack(order + "HHIH2x", entry)
            if tag == 0x0112:
                return value if 1 <= value <= 8 else 1
    except struct.error:
        pass
    return 1


def _jpeg(data: bytes) -> ImageInfo:
    orientation = 1
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            # not at a marker; stray bytes do turn up, so resynchronise
            pos += 1
            continue
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        pos += 2
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue
        if marker in (0xD9, 0xDA):
            break
        (length,) = struct.unpack(">H", data[pos : pos + 2])
        if marker in _SOF_MARKERS:
            height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
            if orientation >= 5:
                # the camera was held sideways; browsers rotate on display
                width, height = height, width
            return ImageInfo("jpeg", width, height, "image/jpeg")
        if marker == 0xE1 and data[pos + 2 : pos + 8] == b"Exif\0\0":
            orientation = _exif_orientation(data[pos + 8 : pos + length])
        pos += length
    raise _Corrupt("JPEG has no frame header")


def _skip_sub_blocks(data: bytes, pos: int) -> int:
    while True:
        size = data[pos]
        pos += 1 + size
        if size == 0:
            return pos


def _gif(data: bytes) -> ImageInfo:
    width, height, flags = struct.unpack("<HHB", data[6:11])
    pos = 13
    if flags & 0x80:
        pos += 3 * (2 << (flags & 7))
    frames = 0
    try:
        while frames < 2:
            block = data[pos]
            if block == 0x2C:
                frames += 1
                local = data[pos + 9]
                pos += 10
                if local & 0x80:
                    pos += 3 * (2 << (local & 7))
                pos = _skip_sub_blocks(data, pos + 1)
            elif block == 0x21:
                pos = _skip_sub_blocks(data, pos + 2)
            else:
                break
    except IndexError:
        # cut short; the size is still good
        pass
    return ImageInfo("gif", width, height, "image/gif", frames > 1)


def _webp(data: bytes) -> ImageInfo:
    chunk = data[12:16]
    animated = False
    if chunk == b"VP8 ":
        if data[23:26] != b"\x9d\x01\x2a":
            raise _Corrupt("bad VP8 start code")
        width, height = struct.unpack("<HH", data[26:30])
        width &= 0x3FFF
        height &= 0x3FFF
    elif chunk == b"VP8L":
        if data[20] != 0x2F:
            raise _Corrupt("bad VP8L signature")
        (bits,) = struct.unpack("<I", data[21:25])
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
    elif chunk == b"VP8X":
        if len(data) < 30:
            raise _Corrupt("truncated VP8X header")
        animated = bool(data[20] & 0x02)
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
    else:
        raise _Corrupt(f"unknown WebP chunk {chunk!r}")
    return ImageInfo("webp", width, height, "image/webp", animated)


def _bmp(data: bytes) -> ImageInfo:
    (header_size,) = struct.unpack("<I", data[14:18])
    if header_size == 12:
        # OS/2 flavour, 16-bit fields
        width, height = struct.unpack("<HH", data[18:22])
    else:
        width, height = struct.unpack("<ii", data[18:26])
    # negative height means the rows are stored top-down
    return ImageInfo("bmp", abs(width), abs(height), "image/bmp")


def _ico(data: bytes) -> ImageInfo:
    _reserved, _kind, count = struct.unpack("<HHH", data[:6])
    if count == 0:
        raise _Corrupt("icon file with no images")
    best = (0, 0)
    for i in range(count):
        entry = data[6 + 16 * i : 22 + 16 * i]
        width = entry[0] or 256
        height = entry[1] or 256
        (offset,) = struct.unpack("<I", entry[12:16])
        if data[offset : offset + 8] == _PNG_SIGNATURE:
            # the directory tops out at 256; an embedded PNG knows better
            width, height = struct.unpack(">II", data[offset + 16 : offset + 24])
        if width * height > best[0] * best[1]:
            best = (width, height)
    return ImageInfo("ico", best[0], best[1], "image/x-icon")


def _boxes(data: bytes, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """Yield (type, body_start, body_end) for the ISO BMFF boxes in a range."""
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos : pos + 8])
        header = 8
        if size == 1:
            (size,) = struct.unpack(">Q", data[pos + 8 : pos + 16])
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield kind, pos + header, pos + size
        pos += size


def _find_box(data: bytes, start: int, end: int, kind: bytes):
    for found, body_start, body_end in _boxes(data, start, end):
        if found == kind:
            return body_start, body_end
    return None


def _avif_brands(data: bytes) -> set[bytes]:
    if data[4:8] != b"ftyp":
        return set()
    (size,) = struct.unpack(">I", data[:4])
    size = min(size, len(data))
    brands = {data[8:12]}
    brands.update(data[i : i + 4] for i in range(16, size - 3, 4))
    return brands


def _primary_properties(data: bytes, meta: tuple[int, int], count: int) -> list[int]:
    """1-based ipco indexes of the properties attached to the primary item."""
    pitm = _find_box(data, meta[0], meta[1], b"pitm")
    iprp = _find_box(data, meta[0], meta[1], b"iprp")
    ipma = _find_box(data, iprp[0], iprp[1], b"ipma") if iprp else None
    if not pitm or not ipma:
        return []
    version = data[pitm[0]]
    if version == 0:
        (primary,) = struct.unpack(">H", data[pitm[0] + 4 : pitm[0] + 6])
    else:
        (primary,) = struct.unpack(">I", data[pitm[0] + 4 : pitm[0] + 8])

    pos = ipma[0]
    version = data[pos]
    wide = data[pos + 3] & 1
    (entries,) = struct.unpack(">I", data[pos + 4 : pos + 8])
    pos += 8
    for _ in range(entries):
        if version < 1:
            (item,) = struct.unpack(">H", data[pos : pos + 2])
            pos += 2
        else:
            (item,) = struct.unpack(">I", data[pos : pos + 4])
            pos += 4
        associations = data[pos]
        pos += 1
        indexes = []
        for _ in range(associations):
            if wide:
                (raw,) = struct.unpack(">H", data[pos : pos + 2])
                indexes.append(raw & 0x7FFF)
                pos += 2
            else:
                indexes.append(data[pos] & 0x7F)
                pos += 1
        if item == primary:
            return [i for i in indexes if 1 <= i <= count]
    return []


def _avif(data: bytes) -> ImageInfo:
    meta = _find_box(data, 0, len(data), b"meta")
    if meta is None:
        raise _Corrupt("AVIF has no meta box")
    # meta is a "full box": four bytes of version and flags come first
    meta = (meta[0] + 4, meta[1])
    iprp = _find_box(data, meta[0], meta[1], b"iprp")
    ipco = _find_box(data, iprp[0], iprp[1], b"ipco") if iprp else None
    if ipco is None:
        raise _Corrupt("AVIF has no item properties")
    properties = list(_boxes(data, ipco[0], ipco[1]))

    size = None
    quarter_turns = 0
    for index in _primary_properties(data, meta, len(properties)):
        kind, start, _end = properties[index - 1]
        if kind == b"ispe":
            size = struct.unpack(">II", data[start + 4 : start + 12])
        elif kind == b"irot":
            quarter_turns = data[start] & 3
    if size is None:
        # No usable item table. Thumbnails and tiles are smaller than the
        # picture itself, so the biggest extent is a decent guess.
        sizes = [
            struct.unpack(">II", data[start + 4 : start + 12])
            for kind, start, _end in properties
            if kind == b"ispe"
        ]
        if not sizes:
            raise _Corrupt("AVIF has no ispe box")
        size = max(sizes, key=lambda wh: wh[0] * wh[1])
    width, height = size
    if quarter_turns % 2:
        width, height = height, width
    animated = data[8:12] == b"avis"
    return ImageInfo("avif", width, height, "image/avif", animated)


_SVG_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SVG_TAG_RE = re.compile(r"<svg\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.I)
_SVG_ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_SVG_LENGTH_RE = re.compile(
    r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)\s*"
)
_SVG_UNITS = {
    "": 1.0,
    "px": 1.0,
    "pt": 96 / 72,
    "pc": 16.0,
    "in": 96.0,
    "cm": 96 / 2.54,
    "mm": 96 / 25.4,
    "q": 96 / 101.6,
    # relative units have nothing to be relative to here; assume the
    # 16px default font
    "em": 16.0,
    "rem": 16.0,
    "ex": 8.0,
}
# what browsers fall back to for a replaced element with no size at all
_SVG_DEFAULT_SIZE = (300, 150)


def _svg_length(text: str | None) -> float | None:
    if not text:
        return None
    match = _SVG_LENGTH_RE.fullmatch(text)
    if match is None:
        return None
    scale = _SVG_UNITS.get(match.group(2).lower())
    if scale is None:
        return None
    value = float(match.group(1)) * scale
    return value if value > 0 else None


def _decode_text(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def _svg_root(data: bytes) -> re.Match | None:
    head = data[:256].lstrip(b"\xef\xbb\xbf\xff\xfe \t\r\n\0")
    if not head.startswith(b"<"):
        return None
    text = _SVG_COMMENT_RE.sub("", _decode_text(data))
    match = _SVG_TAG_RE.search(text)
    if match is None:
        return None
    # only the XML prolog and a doctype may come before the root element
    if re.search(r"<[a-zA-Z]", text[: match.start()]):
        return None
    return match


def _svg(match: re.Match) -> ImageInfo:
    attrs = {}
    for name, double, single in _SVG_ATTR_RE.findall(match.group(1)):
        attrs.setdefault(name, double or single)
    width = _svg_length(attrs.get("width"))
    height = _svg_length(attrs.get("height"))
    box = None
    numbers = re.split(r"[\s,]+", attrs.get("viewBox", "").strip())
    if len(numbers) == 4:
        try:
            box_width, box_height = float(numbers[2]), float(numbers[3])
        except ValueError:
            pass
        else:
            if box_width > 0 and box_height > 0:
                box = (box_width, box_height)

    if box and width is None and height is None:
        width, height = box
    elif box and height is None:
        height = width * box[1] / box[0]
    elif box and width is None:
        width = height * box[0] / box[1]
    if width is None:
        width = _SVG_DEFAULT_SIZE[0]
    if height is None:
        height = _SVG_DEFAULT_SIZE[1]
    return ImageInfo("svg", round(width), round(height), "image/svg+xml")


def _identify(data: bytes) -> ImageInfo | None:
    if data.startswith(_PNG_SIGNATURE):
        return _png(data)
    if data.startswith(b"\xff\xd8\xff"):
        return _jpeg(data)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return _gif(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp(data)
    if _avif_brands(data) & {b"avif", b"avis"}:
        return _avif(data)
    if data[:2] == b"BM" and len(data) >= 18:
        return _bmp(data)
    if data[:4] in (b"\0\0\1\0", b"\0\0\2\0"):
        return _ico(data)
    root = _svg_root(data)
    if root is not None:
        return _svg(root)
    return None


def image_info(source: str | os.PathLike | bytes) -> ImageInfo:
    """Work out the format and pixel size of an image from its header.

    Takes a path or the file contents. Nothing is decoded, so this is cheap
    enough to run on every image in a site. JPEGs carrying an EXIF
    orientation of "rotated a quarter turn" report the size as displayed.
    An SVG with neither width/height nor a viewBox reports 300x150, which is
    how a browser would lay it out.
    """
    path = None
    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
    else:
        path = Path(source)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise AssetError(f"cannot read image: {exc.strerror}", path=path) from None
    try:
        info = _identify(data)
    except _Corrupt as exc:
        raise AssetError(str(exc), path=path) from None
    except (struct.error, IndexError):
        raise AssetError("truncated or corrupt image", path=path) from None
    if info is None:
        raise AssetError("not an image format we know", path=path)
    return info
