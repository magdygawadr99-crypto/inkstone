from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlsplit

from .errors import FeedError
from .urls import is_absolute

_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
_PRODUCT = re.compile(r"[a-z_-]+")


@dataclass
class RobotsRule:
    """One group of robots.txt: who it is for and what they may fetch."""

    user_agent: str | list[str] = "*"
    allow: list[str] = field(default_factory=list)
    disallow: list[str] = field(default_factory=list)
    crawl_delay: float | None = None

    @property
    def agents(self) -> list[str]:
        if isinstance(self.user_agent, str):
            return [self.user_agent]
        return list(self.user_agent)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _coerce_rule(rule: RobotsRule | Mapping[str, Any]) -> RobotsRule:
    if isinstance(rule, RobotsRule):
        return RobotsRule(
            rule.agents, _as_list(rule.allow), _as_list(rule.disallow), rule.crawl_delay
        )
    # config files hand us plain tables, and people write user-agent with a
    # hyphen because that is how it looks in robots.txt
    data = {str(key).lower().replace("-", "_"): value for key, value in rule.items()}
    unknown = set(data) - {"user_agent", "allow", "disallow", "crawl_delay"}
    if unknown:
        raise FeedError(f"unknown robots.txt setting: {', '.join(sorted(unknown))}")
    return RobotsRule(
        _as_list(data.get("user_agent", "*")),
        _as_list(data.get("allow")),
        _as_list(data.get("disallow")),
        data.get("crawl_delay"),
    )


def _check_line(value: str, what: str) -> str:
    value = str(value).strip()
    # a newline would start a directive of the attacker's choosing, and "#"
    # silently comments out the rest of the line
    if "\n" in value or "\r" in value or "#" in value:
        raise FeedError(f"robots.txt {what} contains a line break or '#': {value!r}")
    return value


def _check_path(path: str, directive: str) -> str:
    path = _check_line(path, f"{directive} path")
    if path and path[0] not in "/*":
        raise FeedError(f"robots.txt {directive} path must start with '/': {path!r}")
    return path


def _check_delay(delay: Any) -> float:
    if isinstance(delay, bool) or not isinstance(delay, (int, float)) or delay < 0:
        raise FeedError(f"robots.txt crawl delay must be a number >= 0: {delay!r}")
    return delay


def render_robots(
    rules: Iterable[RobotsRule | Mapping[str, Any]] | None = None,
    *,
    sitemaps: Iterable[str] = (),
) -> str:
    """Build robots.txt. Without rules everything is allowed for everyone."""
    groups = [_coerce_rule(rule) for rule in rules or ()]
    if not groups:
        groups = [RobotsRule()]

    blocks = []
    for group in groups:
        agents = [_check_line(agent, "user agent") for agent in group.agents]
        if not agents or not all(agents):
            raise FeedError("robots.txt rule without a user agent")
        lines = [f"User-agent: {agent}" for agent in agents]
        for directive, paths in (("Allow", group.allow), ("Disallow", group.disallow)):
            lines += [f"{directive}: {_check_path(path, directive)}" for path in paths]
        if not group.allow and not group.disallow:
            # a group needs at least one rule; an empty Disallow allows all
            lines.append("Disallow:")
        if group.crawl_delay is not None:
            lines.append(f"Crawl-delay: {_check_delay(group.crawl_delay):g}")
        blocks.append("\n".join(lines))

    sitemap_lines = []
    for url in sitemaps:
        url = _check_line(url, "sitemap URL")
        if not is_absolute(url):
            raise FeedError(f"robots.txt sitemap must be an absolute URL, got {url!r}")
        sitemap_lines.append(f"Sitemap: {url}")
    if sitemap_lines:
        blocks.append("\n".join(sitemap_lines))
    return "\n\n".join(blocks) + "\n"


def _normalize_path(path: str) -> str:
    """Bring a path or pattern into one spelling so they can be compared.

    Non-ASCII is percent-encoded and existing escapes get uppercase hex, as
    RFC 9309 asks for. "*" and "$" survive because they are pattern syntax.
    """
    # FIXME: "%7Euser" and "~user" ought to compare equal too. Unreserved
    # characters are never written escaped in practice, so it has not come up.
    path = quote(path, safe="/%:@!$&'()*+,;=~?#[]")
    return _PERCENT.sub(lambda match: match.group().upper(), path)


def _product_token(user_agent: str) -> str:
    """Reduce "Googlebot/2.1 (+http://www.google.com/bot.html)" to "googlebot"."""
    user_agent = user_agent.strip().lower()
    if user_agent == "*":
        return user_agent
    match = _PRODUCT.match(user_agent)
    return match.group() if match else ""


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    regex = ".*".join(re.escape(piece) for piece in pattern.split("*"))
    return re.compile(regex + ("$" if anchored else ""), re.DOTALL)


class RobotsTxt:
    """A parsed robots.txt that can be asked what a crawler may fetch.

    Matching follows RFC 9309: the group with the most specific user agent
    applies, and within it the longest matching path wins, Allow beating
    Disallow on a tie.
    """

    def __init__(self, groups: Iterable[RobotsRule] = (), sitemaps: Iterable[str] = ()):
        self.groups = list(groups)
        self.sitemaps = list(sitemaps)
        self._patterns: dict[str, re.Pattern[str]] = {}

    @classmethod
    def parse(cls, text: str) -> RobotsTxt:
        groups: list[RobotsRule] = []
        sitemaps: list[str] = []
        current: RobotsRule | None = None
        in_agents = False
        for line in text.lstrip("\ufeff").splitlines():
            line = line.split("#", 1)[0].strip()
            key, colon, value = line.partition(":")
            if not colon:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == "sitemap":
                sitemaps.append(value)
            elif key == "user-agent":
                # consecutive User-agent lines share one group
                if not in_agents:
                    current = RobotsRule(user_agent=[])
                    groups.append(current)
                current.user_agent.append(value)
                in_agents = True
            elif key in ("allow", "disallow", "crawl-delay"):
                in_agents = False
                if current is None:
                    # rules before the first User-agent line apply to nobody
                    continue
                if key == "allow":
                    current.allow.append(value)
                elif key == "disallow":
                    current.disallow.append(value)
                else:
                    try:
                        current.crawl_delay = float(value)
                    except ValueError:
                        pass
            # anything else (Host, Clean-param, typos) is skipped without
            # ending the group it sits in
        return cls(groups, sitemaps)

    def _group_for(self, user_agent: str) -> RobotsRule | None:
        token = _product_token(user_agent)
        best, best_length = None, -1
        for group in self.groups:
            for agent in map(_product_token, group.agents):
                if agent == "*":
                    length = 0
                elif agent and token.startswith(agent):
                    # "googlebot" also speaks for "googlebot-news", unless
                    # that one has a group of its own
                    length = len(agent)
                else:
                    continue
                if length > best_length:
                    best, best_length = agent, length
        if best is None:
            return None
        # the same agent may appear in several groups; their rules add up
        merged = RobotsRule(user_agent=best)
        for group in self.groups:
            if best in map(_product_token, group.agents):
                merged.allow += group.allow
                merged.disallow += group.disallow
                if merged.crawl_delay is None:
                    merged.crawl_delay = group.crawl_delay
        return merged

    def _matches(self, pattern: str, path: str) -> bool:
        regex = self._patterns.get(pattern)
        if regex is None:
            regex = self._patterns[pattern] = _pattern_regex(_normalize_path(pattern))
        return regex.match(path) is not None

    def can_fetch(self, user_agent: str, url: str) -> bool:
        """May this crawler fetch the URL (or path)? Unknown means yes."""
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        path = _normalize_path(path)
        if path == "/robots.txt":
            return True
        group = self._group_for(user_agent)
        if group is None:
            return True
        allowed, longest = True, -1
        for verdict, patterns in ((True, group.allow), (False, group.disallow)):
            for pattern in patterns:
                # an empty Disallow is the traditional way to say "nothing"
                if not pattern or not self._matches(pattern, path):
                    continue
                # allow is looked at first, so ">" lets it keep a tie
                if len(pattern) > longest:
                    allowed, longest = verdict, len(pattern)
        return allowed

    def crawl_delay(self, user_agent: str) -> float | None:
        group = self._group_for(user_agent)
        return group.crawl_delay if group else None


def parse_robots(text: str) -> RobotsTxt:
    return RobotsTxt.parse(text)
