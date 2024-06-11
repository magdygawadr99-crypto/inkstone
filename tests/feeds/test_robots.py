from __future__ import annotations

import pytest

from inkstone.feeds import FeedError, RobotsRule, RobotsTxt, parse_robots, render_robots

EXAMPLE = """\
# robots.txt for example.com
User-agent: *
Disallow: /drafts/
Disallow: /*.json$
Allow: /drafts/public/
Crawl-delay: 2.5

User-agent: Googlebot
User-agent: Bingbot
Disallow: /search

User-agent: BadBot
Disallow: /

Sitemap: https://example.com/sitemap.xml
"""


def robots(*lines: str) -> RobotsTxt:
    return parse_robots("\n".join(lines))


def rules_for_everyone(*lines: str) -> RobotsTxt:
    return robots("User-agent: *", *lines)


def test_default_allows_everything():
    text = render_robots()
    assert text == "User-agent: *\nDisallow:\n"
    assert parse_robots(text).can_fetch("AnyBot", "/anything")


def test_render_groups_and_sitemaps():
    text = render_robots(
        [
            RobotsRule(
                "*", allow=["/drafts/public/"], disallow=["/drafts/", "/*.json$"]
            ),
            RobotsRule(["BadBot", "WorseBot"], disallow=["/"], crawl_delay=10),
        ],
        sitemaps=["https://example.com/sitemap.xml", "https://example.com/news.xml"],
    )
    assert text == (
        "User-agent: *\n"
        "Allow: /drafts/public/\n"
        "Disallow: /drafts/\n"
        "Disallow: /*.json$\n"
        "\n"
        "User-agent: BadBot\n"
        "User-agent: WorseBot\n"
        "Disallow: /\n"
        "Crawl-delay: 10\n"
        "\n"
        "Sitemap: https://example.com/sitemap.xml\n"
        "Sitemap: https://example.com/news.xml\n"
    )


def test_render_accepts_plain_tables_from_a_config_file():
    text = render_robots(
        [
            {"user_agent": "*", "disallow": "/private/"},
            {"User-Agent": ["A", "B"], "allow": ["/x"], "crawl-delay": 0.5},
        ]
    )
    assert text == (
        "User-agent: *\nDisallow: /private/\n\n"
        "User-agent: A\nUser-agent: B\nAllow: /x\nCrawl-delay: 0.5\n"
    )


def test_group_without_rules_gets_an_empty_disallow():
    assert (
        render_robots([RobotsRule("Friendly")]) == "User-agent: Friendly\nDisallow:\n"
    )


def test_sitemaps_without_rules():
    text = render_robots(sitemaps=["https://example.com/sitemap.xml"])
    assert (
        text == "User-agent: *\nDisallow:\n\nSitemap: https://example.com/sitemap.xml\n"
    )


@pytest.mark.parametrize(
    ("delay", "expected"), [(5, "5"), (5.0, "5"), (0.5, "0.5"), (0, "0")]
)
def test_crawl_delay_format(delay, expected):
    text = render_robots([RobotsRule("*", crawl_delay=delay)])
    assert f"Crawl-delay: {expected}\n" in text


@pytest.mark.parametrize(
    "rule",
    [
        RobotsRule("*", disallow=["drafts/"]),
        RobotsRule("*", allow=["public"]),
        RobotsRule("*", disallow=["/a\nAllow: /"]),
        RobotsRule("*", disallow=["/a\rAllow: /"]),
        RobotsRule("*", disallow=["/a # not a comment"]),
        RobotsRule("Bot\nUser-agent: *"),
        RobotsRule(""),
        RobotsRule([]),
        RobotsRule(["Good", ""]),
        RobotsRule("*", crawl_delay=-1),
        RobotsRule("*", crawl_delay="soon"),
        RobotsRule("*", crawl_delay=True),
        {"user_agent": "*", "dissallow": "/typo/"},
    ],
)
def test_render_refuses_rules_that_would_not_mean_what_they_say(rule):
    with pytest.raises(FeedError):
        render_robots([rule])


@pytest.mark.parametrize(
    "sitemap", ["/sitemap.xml", "sitemap.xml", "https://e.com/a\nDisallow: /"]
)
def test_render_refuses_bad_sitemap_urls(sitemap):
    with pytest.raises(FeedError):
        render_robots(sitemaps=[sitemap])


def test_parse_groups():
    parsed = parse_robots(EXAMPLE)
    assert [group.user_agent for group in parsed.groups] == [
        ["*"],
        ["Googlebot", "Bingbot"],
        ["BadBot"],
    ]
    everyone = parsed.groups[0]
    assert everyone.disallow == ["/drafts/", "/*.json$"]
    assert everyone.allow == ["/drafts/public/"]
    assert everyone.crawl_delay == 2.5
    assert parsed.sitemaps == ["https://example.com/sitemap.xml"]


def test_rendered_file_parses_back():
    rules = [
        RobotsRule(["*"], ["/drafts/public/"], ["/drafts/", "/*.json$"], 2.5),
        RobotsRule(["Googlebot", "Bingbot"], [], ["/search"]),
    ]
    parsed = parse_robots(render_robots(rules, sitemaps=["https://example.com/s.xml"]))
    assert parsed.groups == rules
    assert parsed.sitemaps == ["https://example.com/s.xml"]


def test_parse_is_forgiving_about_layout():
    parsed = robots(
        "\ufeffUSER-AGENT:   Spaced   ",
        "disallow:/tight",
        "Disallow : /loose   # trailing comment",
        "   Allow: /indented",
        "",
        "# a full-line comment",
        "this line has no colon",
        "Crawl-Delay: not-a-number",
        "sitemap: https://example.com/sitemap.xml",
    )
    [group] = parsed.groups
    assert group.user_agent == ["Spaced"]
    assert group.disallow == ["/tight", "/loose"]
    assert group.allow == ["/indented"]
    assert group.crawl_delay is None
    assert parsed.sitemaps == ["https://example.com/sitemap.xml"]


def test_parse_handles_windows_line_endings():
    parsed = parse_robots("User-agent: *\r\nDisallow: /a\r\nDisallow: /b\r\n")
    assert parsed.groups[0].disallow == ["/a", "/b"]


def test_rules_before_any_user_agent_are_ignored():
    parsed = robots("Disallow: /orphan", "User-agent: *", "Disallow: /real")
    assert not parsed.can_fetch("Bot", "/real")
    assert parsed.can_fetch("Bot", "/orphan")


def test_unknown_lines_do_not_break_a_group_apart():
    parsed = robots(
        "User-agent: A",
        "Host: example.com",
        "Sitemap: https://example.com/sitemap.xml",
        "User-agent: B",
        "Disallow: /x",
        "Clean-param: ref /articles/",
        "Disallow: /y",
    )
    [group] = parsed.groups
    assert group.user_agent == ["A", "B"]
    assert group.disallow == ["/x", "/y"]


def test_a_user_agent_line_after_rules_starts_a_new_group():
    parsed = robots("User-agent: A", "Disallow: /a", "User-agent: B", "Disallow: /b")
    assert [(g.user_agent, g.disallow) for g in parsed.groups] == [
        (["A"], ["/a"]),
        (["B"], ["/b"]),
    ]


# The path matching examples from Google's robots.txt documentation.
@pytest.mark.parametrize(
    ("pattern", "matching", "not_matching"),
    [
        (
            "/fish",
            [
                "/fish",
                "/fish.html",
                "/fish/salmon.html",
                "/fishheads",
                "/fish.php?id=x",
            ],
            ["/Fish.asp", "/catfish", "/?id=fish", "/desert/fish"],
        ),
        (
            "/fish*",
            ["/fish", "/fish.html", "/fishheads/yummy.html"],
            ["/Fish.asp", "/catfish", "/desert/fish"],
        ),
        (
            "/fish/",
            ["/fish/", "/fish/?id=anything", "/fish/salmon.htm"],
            ["/fish", "/fish.html", "/animals/fish/", "/Fish/Salmon.asp"],
        ),
        (
            "/*.php",
            [
                "/index.php",
                "/folder/filename.php?parameters",
                "/folder/any.php.file.html",
            ],
            ["/", "/windows.PHP"],
        ),
        (
            "/*.php$",
            ["/filename.php", "/folder/filename.php"],
            ["/filename.php?parameters", "/filename.php/", "/filename.php5"],
        ),
        (
            "/fish*.php",
            ["/fish.php", "/fishheads/catfish.php?parameters"],
            ["/Fish.PHP", "/fish.html"],
        ),
        ("/", ["/", "/anything", "/a/b?c=d"], []),
        ("/$", ["/"], ["/index.html", "/a/"]),
        ("*", ["/", "/anything"], []),
        ("/a*b*c", ["/abc", "/a/x/b/y/c", "/axbxc.html"], ["/acb", "/ab"]),
        ("/search?q=", ["/search?q=robots"], ["/search", "/search?p=1&q=robots"]),
    ],
)
def test_path_patterns(pattern, matching, not_matching):
    parsed = rules_for_everyone(f"Disallow: {pattern}")
    assert [path for path in matching if parsed.can_fetch("Bot", path)] == []
    assert [path for path in not_matching if not parsed.can_fetch("Bot", path)] == []


# ... and its examples of which rule wins.
@pytest.mark.parametrize(
    ("allow", "disallow", "path", "expected"),
    [
        ("/p", "/", "/page", True),
        ("/folder", "/folder", "/folder/page", True),
        ("/page", "/*.htm", "/page.htm", False),
        ("/page", "/*.ph", "/page.php5", True),
        ("/$", "/", "/", True),
        ("/$", "/", "/page.htm", False),
        ("/drafts/public/", "/drafts/", "/drafts/public/post", True),
        ("/drafts/public/", "/drafts/", "/drafts/secret", False),
    ],
)
def test_longest_rule_wins_and_allow_wins_ties(allow, disallow, path, expected):
    for lines in (
        [f"Allow: {allow}", f"Disallow: {disallow}"],
        [f"Disallow: {disallow}", f"Allow: {allow}"],
    ):
        assert rules_for_everyone(*lines).can_fetch("Bot", path) is expected


def test_empty_disallow_allows_everything():
    parsed = rules_for_everyone("Disallow:")
    assert parsed.can_fetch("Bot", "/") and parsed.can_fetch("Bot", "/deep/path")


def test_robots_txt_itself_is_always_fetchable():
    assert rules_for_everyone("Disallow: /").can_fetch("Bot", "/robots.txt")


def test_file_without_groups_allows_everything():
    assert parse_robots("").can_fetch("Bot", "/x")
    assert parse_robots("Sitemap: https://example.com/s.xml").can_fetch("Bot", "/x")
    assert RobotsTxt().can_fetch("Bot", "/x")


@pytest.mark.parametrize(
    ("agent", "path", "expected"),
    [
        ("SomeBot", "/search", True),
        ("SomeBot", "/drafts/post", False),
        ("Googlebot", "/search", False),
        ("Googlebot", "/drafts/post", True),
        ("googlebot", "/search", False),
        ("GOOGLEBOT/2.1 (+http://www.google.com/bot.html)", "/search", False),
        ("Googlebot-News", "/search", False),
        ("Bingbot/2.0", "/search?q=x", False),
        ("BadBot", "/", False),
        ("BadBot", "/drafts/public/", False),
        ("Bad", "/", True),
        ("NotBadBot", "/", True),
    ],
)
def test_the_most_specific_group_applies_and_replaces_the_wildcard(
    agent, path, expected
):
    assert parse_robots(EXAMPLE).can_fetch(agent, path) is expected


def test_longer_user_agent_match_beats_a_shorter_one():
    parsed = robots(
        "User-agent: Googlebot",
        "Disallow: /web",
        "User-agent: Googlebot-News",
        "Disallow: /news",
    )
    assert not parsed.can_fetch("Googlebot-News", "/news")
    assert parsed.can_fetch("Googlebot-News", "/web")
    assert not parsed.can_fetch("Googlebot-Image", "/web")


def test_groups_for_the_same_agent_are_combined():
    parsed = robots(
        "User-agent: A",
        "Disallow: /one",
        "User-agent: B",
        "Disallow: /b-only",
        "User-agent: a",
        "Disallow: /two",
        "Crawl-delay: 3",
    )
    assert not parsed.can_fetch("A", "/one") and not parsed.can_fetch("A", "/two")
    assert parsed.can_fetch("A", "/b-only")
    assert parsed.crawl_delay("A") == 3


def test_version_numbers_in_the_file_are_ignored():
    parsed = robots("User-agent: ExampleBot/1.0", "Disallow: /private")
    assert not parsed.can_fetch("examplebot/2.3 (+https://example.com/bot)", "/private")
    assert parsed.can_fetch("OtherBot", "/private")


def test_agent_without_a_group_or_wildcard_is_unrestricted():
    parsed = robots("User-agent: OnlyThisOne", "Disallow: /")
    assert parsed.can_fetch("Other", "/anything")
    assert parsed.crawl_delay("Other") is None


def test_can_fetch_accepts_full_urls():
    parsed = parse_robots(EXAMPLE)
    assert not parsed.can_fetch("Bot", "https://example.com/drafts/post?x=1")
    assert parsed.can_fetch("Bot", "https://example.com/drafts/public/post")
    assert not parsed.can_fetch("Bot", "https://example.com/data/feed.json")
    assert parsed.can_fetch("Bot", "https://example.com/data/feed.json?v=2")
    assert parsed.can_fetch("Bot", "https://example.com")


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        ("/café/", "/caf%C3%A9/menu"),
        ("/caf%C3%A9/", "/café/menu"),
        ("/caf%c3%a9/", "/caf%C3%A9/menu"),
        ("/caf%C3%A9/", "/caf%c3%a9/menu"),
        ("/日本語", "/%E6%97%A5%E6%9C%AC%E8%AA%9E/page"),
    ],
)
def test_percent_encoding_is_normalised_before_matching(pattern, path):
    assert not rules_for_everyone(f"Disallow: {pattern}").can_fetch("Bot", path)


def test_crawl_delay_lookup():
    parsed = parse_robots(EXAMPLE)
    assert parsed.crawl_delay("SomeBot") == 2.5
    assert parsed.crawl_delay("Googlebot") is None
