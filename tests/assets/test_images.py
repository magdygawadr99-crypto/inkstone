from __future__ import annotations

import struct

import pytest

from inkstone.assets import AssetError, ImageInfo, image_info


def png_chunk(kind, body):
    # the CRC is never looked at
    return struct.pack(">I", len(body)) + kind + body + bytes(4)


def make_png(width, height, *, animated=False):
    out = b"\x89PNG\r\n\x1a\n"
    out += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    out += png_chunk(b"gAMA", struct.pack(">I", 45455))
    if animated:
        out += png_chunk(b"acTL", struct.pack(">II", 3, 0))
    return out + png_chunk(b"IDAT", bytes(12)) + png_chunk(b"IEND", b"")


def jpeg_segment(marker, body):
    return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body


def make_exif(orientation, order=">"):
    tiff = b"MM" if order == ">" else b"II"
    tiff += struct.pack(order + "HI", 42, 8)
    tiff += struct.pack(order + "H", 2)
    # ImageWidth first, so the orientation is not simply the first entry
    tiff += struct.pack(order + "HHII", 0x0100, 4, 1, 4000)
    tiff += struct.pack(order + "HHIHH", 0x0112, 3, 1, orientation, 0)
    tiff += struct.pack(order + "I", 0)
    return jpeg_segment(0xE1, b"Exif\0\0" + tiff)


def make_jpeg(width, height, *, sof=0xC0, exif=b"", fill=b""):
    out = b"\xff\xd8"
    out += jpeg_segment(0xE0, b"JFIF\0" + bytes(9))
    out += exif
    out += jpeg_segment(0xDB, bytes(65))
    # a Huffman table sits in the SOF marker range but is not a frame header
    out += jpeg_segment(0xC4, bytes(28))
    out += fill
    out += jpeg_segment(sof, struct.pack(">BHHB", 8, height, width, 3) + bytes(9))
    out += jpeg_segment(0xDA, bytes(10)) + b"\x12\x34\x56\xff\xd9"
    return out


def make_gif(width, height, frames=1, *, version=b"GIF89a", local_table=False):
    out = version + struct.pack("<HHBBB", width, height, 0x81, 0, 0)
    out += bytes(3 * 4)
    out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    for _ in range(frames):
        out += b"\x21\xf9\x04" + bytes(4) + b"\x00"
        flags = 0x80 if local_table else 0
        out += b"\x2c" + struct.pack("<HHHHB", 0, 0, width, height, flags)
        if local_table:
            out += bytes(3 * 2)
        out += b"\x02" + b"\x02\x4c\x01" + b"\x00"
    return out + b"\x3b"


def make_webp(kind, payload):
    if len(payload) % 2:
        payload += b"\0"
    body = b"WEBP" + kind + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def webp_lossy(width, height):
    payload = b"\x30\x01\x00\x9d\x01\x2a" + struct.pack("<HH", width, height)
    return make_webp(b"VP8 ", payload + bytes(8))


def webp_lossless(width, height):
    bits = (width - 1) | ((height - 1) << 14)
    return make_webp(b"VP8L", b"\x2f" + struct.pack("<I", bits) + bytes(4))


def webp_extended(width, height, *, animated=False):
    flags = 0x12 if animated else 0x10
    payload = bytes([flags, 0, 0, 0])
    payload += (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return make_webp(b"VP8X", payload)


def make_bmp(width, height, *, core=False):
    if core:
        dib = struct.pack("<IHHHH", 12, width, height, 1, 24)
    else:
        dib = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, 0, 0, 0, 0, 0)
    offset = 14 + len(dib)
    return b"BM" + struct.pack("<IHHI", offset, 0, 0, offset) + dib


def make_ico(images, *, kind=1):
    """images: (width, height, payload) triples; 256 is stored as 0."""
    out = struct.pack("<HHH", 0, kind, len(images))
    offset = 6 + 16 * len(images)
    for width, height, payload in images:
        out += struct.pack(
            "<BBBBHHII", width % 256, height % 256, 0, 0, 1, 32, len(payload), offset
        )
        offset += len(payload)
    return out + b"".join(payload for _w, _h, payload in images)


def box(kind, body):
    return struct.pack(">I", len(body) + 8) + kind + body


def full_box(kind, body, *, version=0, flags=0):
    return box(kind, bytes([version]) + flags.to_bytes(3, "big") + body)


def make_avif(
    width,
    height,
    *,
    brand=b"avif",
    compatible=b"avifmif1miaf",
    other_size=None,
    rotation=None,
    item_table=True,
    wide=False,
):
    properties = []
    if other_size:
        # a thumbnail or a tile: present, but not the primary item's
        properties.append(full_box(b"ispe", struct.pack(">II", *other_size)))
    properties.append(full_box(b"ispe", struct.pack(">II", width, height)))
    mine = [len(properties)]
    properties.append(box(b"pixi", bytes([0, 0, 0, 0, 3, 8, 8, 8])))
    if rotation is not None:
        properties.append(box(b"irot", bytes([rotation])))
        mine.append(len(properties))

    iprp = box(b"ipco", b"".join(properties))
    meta = full_box(b"hdlr", bytes(4) + b"pict" + bytes(13))
    if item_table:
        if wide:
            links = b"".join(struct.pack(">H", 0x8000 | i) for i in mine)
            head = struct.pack(">I", 2) + struct.pack(">IB", 9, 0)
            head += struct.pack(">IB", 1, len(mine))
            iprp += full_box(b"ipma", head + links, version=1, flags=1)
            meta += full_box(b"pitm", struct.pack(">I", 1), version=1)
        else:
            links = bytes(0x80 | i for i in mine)
            head = struct.pack(">I", 1) + struct.pack(">HB", 1, len(mine))
            iprp += full_box(b"ipma", head + links)
            meta += full_box(b"pitm", struct.pack(">H", 1))
    meta += box(b"iprp", iprp)
    ftyp = box(b"ftyp", brand + bytes(4) + compatible)
    return ftyp + full_box(b"meta", meta) + box(b"mdat", bytes(32))


def size(data):
    info = image_info(data)
    return info.width, info.height


def test_png():
    assert image_info(make_png(640, 480)) == ImageInfo("png", 640, 480, "image/png")
    assert image_info(make_png(1, 70000)).height == 70000


def test_apng_is_animated():
    assert image_info(make_png(10, 10)).animated is False
    assert image_info(make_png(10, 10, animated=True)).animated is True


@pytest.mark.parametrize("sof", [0xC0, 0xC1, 0xC2, 0xC9, 0xCF])
def test_jpeg_frame_markers(sof):
    info = image_info(make_jpeg(800, 600, sof=sof))
    assert info == ImageInfo("jpeg", 800, 600, "image/jpeg")


def test_jpeg_with_fill_bytes_and_restart_markers():
    assert size(make_jpeg(31, 17, fill=b"\xff\xff\xff\xd0\xff\x01")) == (31, 17)


def test_jpeg_with_stray_bytes_between_segments():
    assert size(make_jpeg(31, 17, fill=b"\x00\x00")) == (31, 17)


@pytest.mark.parametrize(
    "orientation, expected",
    [
        (1, (4000, 3000)),
        (2, (4000, 3000)),
        (3, (4000, 3000)),
        (4, (4000, 3000)),
        (5, (3000, 4000)),
        (6, (3000, 4000)),
        (7, (3000, 4000)),
        (8, (3000, 4000)),
        (9, (4000, 3000)),
    ],
)
@pytest.mark.parametrize("order", [">", "<"])
def test_jpeg_exif_orientation(orientation, expected, order):
    data = make_jpeg(4000, 3000, exif=make_exif(orientation, order))
    assert size(data) == expected


def test_jpeg_with_garbage_exif_still_has_a_size():
    exif = jpeg_segment(0xE1, b"Exif\0\0" + b"MM\x00\x2a\x00\x00\xff\xff")
    assert size(make_jpeg(20, 10, exif=exif)) == (20, 10)
    exif = jpeg_segment(0xE1, b"Exif\0\0" + b"XX" + bytes(20))
    assert size(make_jpeg(20, 10, exif=exif)) == (20, 10)


def test_jpeg_without_frame_header():
    data = b"\xff\xd8" + jpeg_segment(0xE0, b"JFIF\0" + bytes(9)) + b"\xff\xd9"
    with pytest.raises(AssetError, match="no frame header"):
        image_info(data)


@pytest.mark.parametrize("version", [b"GIF87a", b"GIF89a"])
def test_gif(version):
    info = image_info(make_gif(320, 200, version=version))
    assert info == ImageInfo("gif", 320, 200, "image/gif", False)


@pytest.mark.parametrize(
    "frames, local_table, animated",
    [(1, False, False), (1, True, False), (2, False, True), (5, True, True)],
)
def test_gif_animation(frames, local_table, animated):
    data = make_gif(8, 8, frames, local_table=local_table)
    assert image_info(data).animated is animated


def test_truncated_gif_still_has_a_size():
    data = make_gif(320, 200, 3)
    assert size(data[:40]) == (320, 200)
    assert size(data[:13]) == (320, 200)


@pytest.mark.parametrize(
    "data, expected",
    [
        (webp_lossy(550, 368), (550, 368)),
        (webp_lossy(16383, 1), (16383, 1)),
        (webp_lossless(550, 368), (550, 368)),
        (webp_lossless(1, 16384), (1, 16384)),
        (webp_extended(550, 368), (550, 368)),
        (webp_extended(70000, 3), (70000, 3)),
    ],
)
def test_webp(data, expected):
    info = image_info(data)
    assert (info.width, info.height) == expected
    assert (info.format, info.mime, info.animated) == ("webp", "image/webp", False)


def test_animated_webp():
    assert image_info(webp_extended(64, 64, animated=True)).animated is True


@pytest.mark.parametrize(
    "data",
    [
        make_webp(b"VP8 ", bytes(20)),
        make_webp(b"VP8L", b"\x00" + bytes(8)),
        make_webp(b"JUNK", bytes(20)),
        make_webp(b"VP8X", bytes(4)),
    ],
)
def test_corrupt_webp(data):
    with pytest.raises(AssetError):
        image_info(data)


@pytest.mark.parametrize(
    "data, expected",
    [
        (make_bmp(100, 50), (100, 50)),
        (make_bmp(100, -50), (100, 50)),
        (make_bmp(100, 50, core=True), (100, 50)),
    ],
)
def test_bmp(data, expected):
    assert size(data) == expected
    assert image_info(data).mime == "image/bmp"


def test_ico_reports_the_largest_image():
    data = make_ico([(16, 16, bytes(40)), (48, 48, bytes(40)), (32, 32, bytes(40))])
    assert image_info(data) == ImageInfo("ico", 48, 48, "image/x-icon")


def test_ico_zero_means_256():
    assert size(make_ico([(256, 256, bytes(40))])) == (256, 256)


def test_ico_with_embedded_png():
    data = make_ico([(32, 32, bytes(40)), (0, 0, make_png(512, 512))])
    assert size(data) == (512, 512)


def test_cursor_files_are_read_like_icons():
    assert size(make_ico([(32, 32, bytes(40))], kind=2)) == (32, 32)


def test_ico_without_images():
    with pytest.raises(AssetError):
        image_info(make_ico([]))


def test_avif():
    assert image_info(make_avif(1280, 720)) == ImageInfo(
        "avif", 1280, 720, "image/avif"
    )


def test_avif_uses_the_primary_item():
    assert size(make_avif(640, 360, other_size=(4096, 4096))) == (640, 360)
    assert size(make_avif(640, 360, other_size=(160, 90))) == (640, 360)


def test_avif_with_wide_item_table():
    assert size(make_avif(640, 360, other_size=(4096, 4096), wide=True)) == (640, 360)


def test_avif_without_item_table_takes_the_largest_extent():
    data = make_avif(640, 360, other_size=(160, 90), item_table=False)
    assert size(data) == (640, 360)


@pytest.mark.parametrize(
    "rotation, expected",
    [(0, (640, 360)), (1, (360, 640)), (2, (640, 360)), (3, (360, 640))],
)
def test_avif_rotation(rotation, expected):
    assert size(make_avif(640, 360, rotation=rotation)) == expected


def test_avif_sequence_is_animated():
    assert image_info(make_avif(64, 64, brand=b"avis")).animated is True


def test_avif_recognised_by_compatible_brand():
    assert image_info(make_avif(64, 32, brand=b"mif1")).format == "avif"


def test_other_iso_media_is_not_avif():
    data = make_avif(64, 32, brand=b"isom", compatible=b"isomiso2mp41")
    with pytest.raises(AssetError, match="not an image"):
        image_info(data)


def test_avif_without_properties():
    data = box(b"ftyp", b"avif" + bytes(4) + b"avif") + full_box(b"meta", b"")
    with pytest.raises(AssetError, match="no item properties"):
        image_info(data)


@pytest.mark.parametrize(
    "svg, expected",
    [
        ('<svg width="100" height="50"></svg>', (100, 50)),
        ("<svg width='10px' height='20.6px'/>", (10, 21)),
        ('<svg viewBox="0 0 24 24"></svg>', (24, 24)),
        ('<svg viewBox="-5,-5,30,40"></svg>', (30, 40)),
        ('<svg width="2in" height="1in"></svg>', (192, 96)),
        ('<svg width="72pt" height="1pc"></svg>', (96, 16)),
        ('<svg width="100" viewBox="0 0 200 100"></svg>', (100, 50)),
        ('<svg height="50" viewBox="0 0 200 100"></svg>', (100, 50)),
        ('<svg width="100%" height="100%" viewBox="0 0 30 40"></svg>', (30, 40)),
        ('<svg width="100%" height="40"></svg>', (300, 40)),
        ('<svg viewBox="0 0 0 0"></svg>', (300, 150)),
        ('<svg viewBox="oops"></svg>', (300, 150)),
        ("<svg></svg>", (300, 150)),
        ('<svg data-note="a > b" width="5" height="6"></svg>', (5, 6)),
        ('<SVG WIDTH="5" width="7" height="6"></SVG>', (7, 6)),
        (
            '<?xml version="1.0"?>\n<!-- <svg width="1" height="1"> -->\n'
            '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "x.dtd">\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="34"/>',
            (12, 34),
        ),
    ],
)
def test_svg(svg, expected):
    info = image_info(svg.encode("utf-8"))
    assert (info.width, info.height) == expected
    assert (info.format, info.mime, info.animated) == ("svg", "image/svg+xml", False)


def test_svg_with_bom_and_utf16():
    svg = '<svg width="8" height="9"></svg>'
    assert size(b"\xef\xbb\xbf  \n" + svg.encode("utf-8")) == (8, 9)
    assert size(svg.encode("utf-16")) == (8, 9)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"hello world",
        b"\x00\x01\x02\x03" * 8,
        b'<html><body><svg width="1" height="1"></svg></body></html>',
        b"<p>not an image</p>",
        b"GIF88a" + bytes(20),
    ],
)
def test_unknown_data(data):
    with pytest.raises(AssetError, match="not an image format we know"):
        image_info(data)


@pytest.mark.parametrize(
    "data",
    [
        make_png(10, 10)[:20],
        make_png(10, 10)[:8] + png_chunk(b"IDAT", bytes(20)),
        make_jpeg(10, 10)[:30],
        make_gif(10, 10)[:8],
        webp_lossy(10, 10)[:24],
        make_bmp(10, 10)[:20],
        make_ico([(16, 16, bytes(4))])[:10],
    ],
)
def test_truncated_or_corrupt_headers(data):
    with pytest.raises(AssetError):
        image_info(data)


def test_reads_from_a_path(tmp_path):
    path = tmp_path / "pic.png"
    path.write_bytes(make_png(3, 4))
    assert size(path) == (3, 4)
    assert size(str(path)) == (3, 4)
    assert size(bytearray(make_png(3, 4))) == (3, 4)


def test_errors_name_the_file(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(make_png(3, 4)[:18])
    with pytest.raises(AssetError) as info:
        image_info(path)
    assert info.value.path == path
    with pytest.raises(AssetError, match="cannot read image") as info:
        image_info(tmp_path / "missing.png")
    assert info.value.path == tmp_path / "missing.png"


def test_image_info_helpers():
    info = image_info(make_png(300, 200))
    assert info.as_attrs() == 'width="300" height="200"'
    assert info.aspect_ratio == 1.5
    assert ImageInfo("svg", 1, 0, "image/svg+xml").aspect_ratio == 0.0
    with pytest.raises(AttributeError):
        info.width = 1
