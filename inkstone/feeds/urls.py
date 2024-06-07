from __future__ import annotations

import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

_TAG = re.compile(r"""<[a-zA-Z](?:[^>"']|"[^"]*"|'[^']*')*>""")
# Matches any attribute with a value, not just the interesting ones, so that
# a quoted value is consumed whole and 'title="set href=x"' is not mistaken
# for a link.
_ATTR = re.compile(r"""(\s+)([^\s"'<>/=]+)(\s*=\s*)("[^"]*"|'[^']*'|[^\s"'>]+)""")
_URL_ATTRS = ("href", "src", "srcset", "poster")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:\S+\Z")

# Characters quote() should leave alone in a path or query: the reserved set
# plus "%", so text that is already escaped is not escaped twice.
_SAFE = "/%:@!$&'()*+,;=~"


def is_absolute(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def has_scheme(url: str) -> bool:
    """True for anything shaped like scheme:rest, be it https:, urn: or tag:."""
    return _SCHEME.match(url) is not None


def absolutize(url: str, base: str) -> str:
    """Resolve url against base. mailto:, data: and friends pass through."""
    url = url.strip()
    if not url:
        return url
    try:
        return urljoin(base, url)
    except ValueError:
        # something like "http://[oops"; not ours to fix
        return url


def _absolutize_srcset(value: str, base: str) -> str:
    # "small.png 480w, large.png 2x". Splitting on commas is wrong because a
    # URL may contain them; the HTML rule is that a URL runs up to the next
    # whitespace and only commas at its very end separate candidates.
    candidates = []
    pos, n = 0, len(value)
    while pos < n:
        while pos < n and (value[pos].isspace() or value[pos] == ","):
            pos += 1
        end = pos
        while end < n and not value[end].isspace():
            end += 1
        url = value[pos:end]
        if not url:
            break
        pos = end
        descriptor = ""
        if url.endswith(","):
            url = url.rstrip(",")
        else:
            comma = value.find(",", pos)
            if comma < 0:
                comma = n
            descriptor = value[pos:comma].strip()
            pos = comma
        candidates.append(f"{absolutize(url, base)} {descriptor}".strip())
    return ", ".join(candidates)


def absolutize_html(html: str, base: str) -> str:
    """Make href, src, srcset and poster URLs in an HTML fragment absolute.

    Feed readers show the content away from the page it came from, so a
    relative link or image would point nowhere. The markup is patched as
    text rather than parsed and re-serialised, which leaves everything else
    exactly as it was written.
    """

    def fix_attribute(match: re.Match[str]) -> str:
        space, name, equals, value = match.groups()
        if name.lower() not in _URL_ATTRS:
            return match.group()
        if value[0] in "\"'":
            value = value[1:-1]
        if not value.strip():
            return match.group()
        if name.lower() == "srcset":
            value = _absolutize_srcset(value, base)
        else:
            value = absolutize(value, base)
        # always quoted: the resolved URL may contain a "=" that the
        # unquoted original did not
        return f'{space}{name}{equals}"{value}"'

    def fix_tag(match: re.Match[str]) -> str:
        return _ATTR.sub(fix_attribute, match.group())

    return _TAG.sub(fix_tag, html)


def to_uri(url: str) -> str:
    """Percent-encode an IRI so it only uses ASCII, as sitemaps require."""
    if url.isascii() and " " not in url:
        return url
    parts = urlsplit(url)
    netloc = parts.netloc
    if not netloc.isascii():
        userinfo, at, hostport = netloc.rpartition("@")
        host, colon, port = hostport.partition(":")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            pass
        netloc = f"{userinfo}{at}{host}{colon}{port}"
    return urlunsplit(
        (
            parts.scheme,
            netloc,
            quote(parts.path, safe=_SAFE),
            quote(parts.query, safe=_SAFE + "?"),
            quote(parts.fragment, safe=_SAFE + "?"),
        )
    )
