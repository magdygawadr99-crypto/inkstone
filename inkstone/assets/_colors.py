from __future__ import annotations

import colorsys

# The CSS named colours, as rrggbb.
_TABLE = """
aliceblue:f0f8ff antiquewhite:faebd7 aqua:00ffff aquamarine:7fffd4 azure:f0ffff
beige:f5f5dc bisque:ffe4c4 black:000000 blanchedalmond:ffebcd blue:0000ff
blueviolet:8a2be2 brown:a52a2a burlywood:deb887 cadetblue:5f9ea0
chartreuse:7fff00 chocolate:d2691e coral:ff7f50 cornflowerblue:6495ed
cornsilk:fff8dc crimson:dc143c cyan:00ffff darkblue:00008b darkcyan:008b8b
darkgoldenrod:b8860b darkgray:a9a9a9 darkgreen:006400 darkgrey:a9a9a9
darkkhaki:bdb76b darkmagenta:8b008b darkolivegreen:556b2f darkorange:ff8c00
darkorchid:9932cc darkred:8b0000 darksalmon:e9967a darkseagreen:8fbc8f
darkslateblue:483d8b darkslategray:2f4f4f darkslategrey:2f4f4f
darkturquoise:00ced1 darkviolet:9400d3 deeppink:ff1493 deepskyblue:00bfff
dimgray:696969 dimgrey:696969 dodgerblue:1e90ff firebrick:b22222
floralwhite:fffaf0 forestgreen:228b22 fuchsia:ff00ff gainsboro:dcdcdc
ghostwhite:f8f8ff gold:ffd700 goldenrod:daa520 gray:808080 green:008000
greenyellow:adff2f grey:808080 honeydew:f0fff0 hotpink:ff69b4 indianred:cd5c5c
indigo:4b0082 ivory:fffff0 khaki:f0e68c lavender:e6e6fa lavenderblush:fff0f5
lawngreen:7cfc00 lemonchiffon:fffacd lightblue:add8e6 lightcoral:f08080
lightcyan:e0ffff lightgoldenrodyellow:fafad2 lightgray:d3d3d3
lightgreen:90ee90 lightgrey:d3d3d3 lightpink:ffb6c1 lightsalmon:ffa07a
lightseagreen:20b2aa lightskyblue:87cefa lightslategray:778899
lightslategrey:778899 lightsteelblue:b0c4de lightyellow:ffffe0 lime:00ff00
limegreen:32cd32 linen:faf0e6 magenta:ff00ff maroon:800000
mediumaquamarine:66cdaa mediumblue:0000cd mediumorchid:ba55d3
mediumpurple:9370db mediumseagreen:3cb371 mediumslateblue:7b68ee
mediumspringgreen:00fa9a mediumturquoise:48d1cc mediumvioletred:c71585
midnightblue:191970 mintcream:f5fffa mistyrose:ffe4e1 moccasin:ffe4b5
navajowhite:ffdead navy:000080 oldlace:fdf5e6 olive:808000 olivedrab:6b8e23
orange:ffa500 orangered:ff4500 orchid:da70d6 palegoldenrod:eee8aa
palegreen:98fb98 paleturquoise:afeeee palevioletred:db7093 papayawhip:ffefd5
peachpuff:ffdab9 peru:cd853f pink:ffc0cb plum:dda0dd powderblue:b0e0e6
purple:800080 rebeccapurple:663399 red:ff0000 rosybrown:bc8f8f
royalblue:4169e1 saddlebrown:8b4513 salmon:fa8072 sandybrown:f4a460
seagreen:2e8b57 seashell:fff5ee sienna:a0522d silver:c0c0c0 skyblue:87ceeb
slateblue:6a5acd slategray:708090 slategrey:708090 snow:fffafa
springgreen:00ff7f steelblue:4682b4 tan:d2b48c teal:008080 thistle:d8bfd8
tomato:ff6347 turquoise:40e0d0 violet:ee82ee wheat:f5deb3 white:ffffff
whitesmoke:f5f5f5 yellow:ffff00 yellowgreen:9acd32
"""

NAMED = dict(pair.split(":") for pair in _TABLE.split())

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def is_hex_colour(text: str) -> bool:
    """True for `#rgb`, `#rgba`, `#rrggbb` and `#rrggbbaa`."""
    return (
        text.startswith("#")
        and len(text) in (4, 5, 7, 9)
        and all(c in _HEX_DIGITS for c in text[1:])
    )


def _squeeze(digits: str) -> str:
    """rrggbb -> rgb when every channel is a doubled digit."""
    if all(digits[i] == digits[i + 1] for i in range(0, len(digits), 2)):
        return digits[::2]
    return digits


def _build_lookups() -> tuple[dict[str, str], dict[str, str]]:
    to_name: dict[str, str] = {}
    to_hex: dict[str, str] = {}
    for name in sorted(NAMED):
        short = "#" + _squeeze(NAMED[name])
        if len(name) < len(short):
            # sorted order means gray wins over grey, and so on
            best = to_name.get(short)
            if best is None or len(name) < len(best):
                to_name[short] = name
        elif len(short) < len(name):
            to_hex[name] = short
    return to_name, to_hex


_HEX_TO_NAME, _NAME_TO_HEX = _build_lookups()


def shorten_hex(text: str) -> str:
    """Shortest spelling of a hex colour: `#FFFFFF` -> `#fff`, `#ff0000` -> `red`."""
    digits = text[1:].lower()
    if len(digits) in (4, 8):
        opaque = digits.endswith("f" if len(digits) == 4 else "ff")
        if opaque:
            digits = digits[:3] if len(digits) == 4 else digits[:6]
    if len(digits) in (6, 8):
        digits = _squeeze(digits)
    short = "#" + digits
    return _HEX_TO_NAME.get(short, short)


def shorten_name(name: str) -> str | None:
    """Hex form of a colour keyword if that is shorter (`white` -> `#fff`)."""
    return _NAME_TO_HEX.get(name.lower())


def _channel(value: float) -> int | None:
    # Browsers disagree on how to round .5, so only whole channels convert.
    nearest = round(value)
    if abs(value - nearest) > 1e-6:
        return None
    return min(max(nearest, 0), 255)


def rgb_to_hex(r: float, g: float, b: float) -> str | None:
    channels = [_channel(v) for v in (r, g, b)]
    if None in channels:
        return None
    return "#%02x%02x%02x" % tuple(channels)


def hsl_to_hex(h: float, s: float, l: float) -> str | None:
    """h in degrees, s and l in percent."""
    s = min(max(s, 0.0), 100.0)
    l = min(max(l, 0.0), 100.0)
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return rgb_to_hex(r * 255, g * 255, b * 255)
