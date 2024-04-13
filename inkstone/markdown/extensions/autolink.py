from __future__ import annotations

import re

from ..inlines import InlineParser
from ..nodes import Document, Link, Node, Text
from ..utils import normalize_uri
from . import Extension, replace_in_text

# A bare link may only start at the beginning of the text or after
# whitespace or one of * _ ~ ( so that "xhttp://foo" stays as it is.
_URL_START = re.compile(r"(?<![^\s*_~(])(?:https?://|ftp://|www\.)", re.I)
_URL_BODY = re.compile(r"[^\s<\[\]]*")
_DOMAIN = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*")
_TRAILING_ENTITY = re.compile(r"&[A-Za-z0-9]+;$")
# XXX ASCII only, as on GitHub. An address with an umlaut in either half
# stays plain text and has to be linked by hand.
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._+/:-])[A-Za-z0-9._+-]+@[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+"
)


def _valid_domain(domain: str, need_dot: bool) -> bool:
    segments = domain.split(".")
    if need_dot and len(segments) < 2:
        return False
    # underscores are fine in subdomains but not in the registered part
    return not any("_" in segment for segment in segments[-2:])


def _trim_url(url: str) -> str:
    """Cut off trailing characters that are more likely prose than URL."""
    while url:
        last = url[-1]
        if last in "?!.,:*_~'\"":
            url = url[:-1]
        elif last == ")":
            # keep balanced parens: en.wikipedia.org/wiki/Foo_(bar)
            if url.count(")") <= url.count("("):
                break
            url = url[:-1]
        elif last == ";":
            m = _TRAILING_ENTITY.search(url)
            if m is None:
                break
            url = url[: m.start()]
        else:
            break
    return url


def _bare_url(parser: InlineParser, m: re.Match) -> bool:
    subject = parser.subject
    has_scheme = not m.group().lower().startswith("www")
    domain_start = m.end() if has_scheme else m.start()
    domain = _DOMAIN.match(subject, domain_start)
    if domain is None or not _valid_domain(domain.group(), need_dot=not has_scheme):
        return False

    end = _URL_BODY.match(subject, domain.end()).end()
    url = _trim_url(subject[m.start() : end])
    if len(url) <= len(m.group()):
        return False

    link = Link(normalize_uri(url if has_scheme else "http://" + url))
    link.bare = True
    link.children = [Text(url)]
    parser.add(link)
    parser.pos = m.start() + len(url)
    return True


def _email_link(m: re.Match) -> Node | None:
    address = m.group()
    if address[-1] in "-_":
        return None
    link = Link(normalize_uri("mailto:" + address))
    link.bare = True
    link.append(Text(address))
    return link


class AutolinkExtension(Extension):
    """Links for bare URLs and e-mail addresses, no angle brackets needed."""

    name = "autolink"

    def setup_inlines(self, parser: InlineParser) -> None:
        parser.add_scanner(_URL_START, _bare_url)

    def after_inlines(self, doc: Document) -> None:
        # Addresses are picked out afterwards rather than while parsing: by
        # the time the parser gets to the "@" the local part is long gone.
        replace_in_text(doc, _EMAIL, _email_link)
