"""The example blog: config, content files, data and its template overrides.

Nothing is built here. The checks are the ones that can be made by reading
the files, so a broken example is noticed even while the builder is not.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from . import layout

CONTENT = layout.EXAMPLE / "content"
CONTENT_FILES = sorted(CONTENT.rglob("*.md"))
SITE_TEMPLATES = sorted((layout.EXAMPLE / "templates").rglob("*.html"))

FENCES = {"---": "yaml", "+++": "toml"}
DATE_PREFIX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")
SHORTCODE_OPEN = re.compile(r"\{\{<\s*(\w+)\b[^>]*>\}\}")
SHORTCODE_CLOSE = re.compile(r"\{\{<\s*/(\w+)\s*>\}\}")
PAIRED_SHORTCODES = {"note", "details"}
INLINE_SHORTCODES = {"figure", "youtube"}


def rel(path):
    return path.relative_to(layout.EXAMPLE).as_posix()


def split_front_matter(path):
    """(format, front matter text, body). Fails the test on a broken fence."""
    lines = layout.read(path).split("\n")
    assert lines[0] in FENCES, f"{rel(path)}: first line is not a front matter fence"
    fence = lines[0]
    try:
        end = lines.index(fence, 1)
    except ValueError:
        pytest.fail(f"{rel(path)}: front matter fence {fence} is never closed")
    return FENCES[fence], "\n".join(lines[1:end]), "\n".join(lines[end + 1 :])


def simple_keys(fmt, text):
    """Top-level scalar keys, read naively. Enough for title, slug and date."""
    sep = ":" if fmt == "yaml" else "="
    found = {}
    for line in text.splitlines():
        match = re.match(rf"^([A-Za-z_][\w-]*)\s*{sep}\s*(.*)$", line)
        if match:
            found[match.group(1)] = match.group(2).strip().strip("\"'")
    return found


def slug_and_date(path):
    fmt, text, _body = split_front_matter(path)
    keys = simple_keys(fmt, text)
    stem = path.parent.name if path.name == "index.md" else path.stem
    date = keys.get("date")
    match = DATE_PREFIX.match(stem)
    if match:
        stem = match.group(4)
        date = date or "-".join(match.group(1, 2, 3))
    return keys.get("slug", stem), date


def section_of(path):
    parts = path.relative_to(CONTENT).parts
    if path.name == "index.md":
        parts = parts[:-1]
    return "/".join(parts[:-1])


def regular_pages():
    return [path for path in CONTENT_FILES if path.name != "_index.md"]


def test_site_has_the_expected_shape():
    for name in ("inkstone.toml", "content", "data", "templates", "static"):
        assert (layout.EXAMPLE / name).exists(), name
    posts = [p for p in regular_pages() if section_of(p) == "posts"]
    assert 10 <= len(posts) <= 16
    assert (CONTENT / "_index.md").is_file()
    assert (CONTENT / "posts" / "_index.md").is_file()
    assert (CONTENT / "projects" / "_index.md").is_file()
    static = sorted(
        rel(p) for p in (layout.EXAMPLE / "static").rglob("*") if p.is_file()
    )
    assert static == ["static/css/custom.css"]


def test_config_parses_and_points_at_real_things():
    tomllib = pytest.importorskip("tomllib")
    with open(layout.EXAMPLE / "inkstone.toml", "rb") as f:
        config = tomllib.load(f)
    assert config["title"] and config["base_url"].endswith("/")
    assert config["theme"] in layout.THEME_NAMES
    assert re.fullmatch(r"UTC|[+-]\d{2}:\d{2}", config["timezone"])
    assert {"shortcodes", "toc", "reading_time"} <= set(config["plugins"])
    # settings for a plugin that is not switched on are a typo waiting to happen
    assert set(config.get("plugin", {})) <= set(config["plugins"])
    for menu in config["menus"].values():
        weights = [item["weight"] for item in menu]
        assert weights == sorted(weights)
        for item in menu:
            assert item["name"] and item["url"].startswith(("/", "https://"))
    for href in config["params"]["custom_css"]:
        assert (layout.EXAMPLE / "static" / href).is_file(), href
    sections = {section_of(path) for path in regular_pages()} - {""}
    assert set(config["permalinks"]) <= sections
    assert set(config["feeds"]["sections"]) <= sections


@pytest.mark.parametrize("path", CONTENT_FILES, ids=rel)
def test_front_matter_looks_parseable(path):
    fmt, text, body = split_front_matter(path)
    assert text.strip(), "empty front matter"
    assert body.strip(), "no body"
    assert "title" in simple_keys(fmt, text)
    if fmt == "toml":
        tomllib = pytest.importorskip("tomllib")
        assert tomllib.loads(text)["title"]
        return
    for number, line in enumerate(text.splitlines(), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        assert "\t" not in line, f"{rel(path)}:{number}: tab in YAML"
        assert re.match(
            r"^(\s+\S|-\s|[A-Za-z_][\w-]*:(\s|$))", line
        ), f"{rel(path)}:{number}: not a key, list item or continuation: {line!r}"


@pytest.mark.parametrize("path", CONTENT_FILES, ids=rel)
def test_front_matter_parses_with_the_real_reader(path):
    frontmatter = pytest.importorskip("inkstone.frontmatter")
    meta, body = frontmatter.parse(layout.read(path), path=path)
    assert isinstance(meta["title"], str) and meta["title"]
    assert body.strip()
    for key in ("tags", "categories", "aliases"):
        if key in meta:
            assert isinstance(meta[key], list), key
            assert all(isinstance(item, str) for item in meta[key])
    for key in ("draft", "toc"):
        if key in meta:
            assert isinstance(meta[key], bool), key
    for key in ("date", "updated"):
        if key in meta:
            assert isinstance(meta[key], dt.date), key
    if "weight" in meta:
        assert isinstance(meta["weight"], int)


def test_slugs_are_unique_within_a_section():
    seen = {}
    for path in regular_pages():
        slug, _date = slug_and_date(path)
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug), f"{rel(path)}: {slug!r}"
        key = (section_of(path), slug)
        assert key not in seen, f"{rel(path)} and {rel(seen[key])} share a slug"
        seen[key] = path


def test_titles_are_unique():
    titles = [simple_keys(*split_front_matter(p)[:2])["title"] for p in CONTENT_FILES]
    assert len(titles) == len(set(titles))


def test_posts_are_dated_and_spread_over_the_year():
    dates = []
    for path in regular_pages():
        if section_of(path) != "posts":
            continue
        _slug, date = slug_and_date(path)
        assert date, f"{rel(path)}: no date in the file name or the front matter"
        dates.append(dt.date.fromisoformat(date))
    assert len(set(dates)) == len(dates)
    assert len({(d.year, d.month) for d in dates}) >= 6


def test_example_uses_the_features_it_is_there_to_show():
    bodies = {rel(p): layout.read(p) for p in CONTENT_FILES}
    everything = "\n".join(bodies.values())
    assert sum("<!-- more -->" in body for body in bodies.values()) >= 5
    assert sum(1 for body in bodies.values() if body.startswith("+++\n")) == 1
    drafts = [
        name for name, body in bodies.items() if re.search(r"^draft: true$", body, re.M)
    ]
    assert len(drafts) == 1
    bundles = [p for p in CONTENT_FILES if p.name == "index.md"]
    assert len(bundles) == 1
    assert [p.name for p in bundles[0].parent.iterdir() if p.suffix == ".svg"]
    for marker in (
        "[^",
        "- [x]",
        "- [ ]",
        "!!! ",
        "\n:   ",
        "|---",
        "[TOC]",
        "aliases:",
    ):
        assert marker in everything, marker
    languages = set(re.findall(r"^```(\w+)", everything, re.M))
    assert {
        "python",
        "javascript",
        "bash",
        "yaml",
        "toml",
        "json",
        "html",
        "css",
    } <= languages
    used = set(SHORTCODE_OPEN.findall(everything))
    assert used == PAIRED_SHORTCODES | INLINE_SHORTCODES


@pytest.mark.parametrize("path", CONTENT_FILES, ids=rel)
def test_code_fences_and_shortcodes_are_closed(path):
    _fmt, _text, body = split_front_matter(path)
    fence = None
    stack = []
    for number, line in enumerate(body.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)
            elif line.strip() == fence:
                fence = None
            continue
        if fence is not None:
            continue
        for name in SHORTCODE_CLOSE.findall(line):
            assert stack and stack[-1] == name, f"{rel(path)}:{number}: stray /{name}"
            stack.pop()
        for name in SHORTCODE_OPEN.findall(line):
            assert name in PAIRED_SHORTCODES | INLINE_SHORTCODES, name
            if name in PAIRED_SHORTCODES:
                stack.append(name)
    assert fence is None, f"{rel(path)}: unclosed code fence"
    assert not stack, f"{rel(path)}: unclosed shortcode {stack}"


@pytest.mark.parametrize("path", CONTENT_FILES, ids=rel)
def test_footnotes_are_defined_and_used(path):
    body = split_front_matter(path)[2]
    # code, fenced or inline, is full of things like [^"] that are not notes
    body = re.sub(r"^(`{3,}).*?^\1\s*$", "", body, flags=re.S | re.M)
    body = re.sub(r"`[^`\n]+`", "", body)
    defined = set(re.findall(r"^\[\^([^\]]+)\]:", body, re.M))
    used = set(re.findall(r"\[\^([^\]]+)\](?!:)", body))
    assert defined == used


def test_bundle_resources_exist():
    for path in CONTENT_FILES:
        if path.name != "index.md":
            continue
        body = layout.read(path)
        for src in re.findall(r'src="([^"/:]+\.\w+)"', body):
            assert (path.parent / src).is_file(), f"{rel(path)}: {src}"
        for svg in path.parent.glob("*.svg"):
            text = layout.read(svg)
            assert text.lstrip().startswith("<svg") and "<title" in text
            assert svg.stat().st_size < 4096


def expected_urls():
    """URLs the build should produce, worked out from file names and the
    permalink patterns in the example config."""
    urls = {"/", "/rss.xml", "/atom.xml", "/feed.json", "/archive/", "/tags/"}
    for path in CONTENT_FILES:
        section = section_of(path)
        if path.name == "_index.md":
            urls.add("/" + path.parent.relative_to(CONTENT).as_posix().strip(".") + "/")
            continue
        slug, date = slug_and_date(path)
        if section == "posts":
            year, month, _day = date.split("-")
            urls.add(f"/{year}/{month}/{slug}/")
        elif section:
            urls.add(f"/{section}/{slug}/")
        else:
            urls.add(f"/{slug}/")
        fmt, text, _body = split_front_matter(path)
        tags = re.search(r"^tags\s*[:=]\s*\[(.*)\]", text, re.M)
        for tag in tags.group(1).split(",") if tags else []:
            urls.add("/tags/" + tag.strip().strip("\"'") + "/")
    return {url.replace("//", "/") for url in urls}


@pytest.mark.parametrize("path", CONTENT_FILES, ids=rel)
def test_internal_links_point_at_pages_that_exist(path):
    known = expected_urls()
    body = split_front_matter(path)[2]
    for target in re.findall(r"\]\((/[^)\s#]*)", body):
        assert target in known, f"{rel(path)}: link to {target}"


def test_data_files_parse():
    data = layout.EXAMPLE / "data"
    projects = json.loads(layout.read(data / "projects.json"))
    project_slugs = {
        slug_and_date(p)[0] for p in regular_pages() if section_of(p) == "projects"
    }
    assert set(projects) == project_slugs
    for info in projects.values():
        assert {"status", "language", "since", "repo"} <= set(info)

    yamlite = pytest.importorskip("inkstone.yamlite")
    groups = yamlite.loads(layout.read(data / "links.yaml"))
    assert isinstance(groups, list) and len(groups) >= 2
    for group in groups:
        assert group["title"]
        for link in group["links"]:
            assert link["name"] and link["url"].startswith("https://")


def test_projects_are_ordered_by_distinct_weights():
    weights = []
    for path in regular_pages():
        if section_of(path) == "projects":
            keys = simple_keys(*split_front_matter(path)[:2])
            weights.append(int(keys["weight"]))
    assert len(weights) >= 3 and len(set(weights)) == len(weights)
    index = simple_keys(*split_front_matter(CONTENT / "projects" / "_index.md")[:2])
    assert index["sort_by"] == "weight"


def test_site_templates_resolve_against_the_theme():
    names = [
        p.relative_to(layout.EXAMPLE / "templates").as_posix() for p in SITE_TEMPLATES
    ]
    assert "projects/section.html" in names
    custom = [n for n in names if layout.find_template("default", n) is None]
    assert [n for n in custom if n.startswith("partials/")], "no custom partial"
    for path, name in zip(SITE_TEMPLATES, names):
        source = layout.COMMENT_RE.sub("", layout.read(path))
        for _kind, _quote, target in layout.REFERENCE_RE.findall(source):
            in_site = (layout.EXAMPLE / "templates" / target).is_file()
            assert in_site or layout.find_template("default", target), (name, target)
        assert source.count("{%") == source.count("%}")
        for tag in ("if", "for", "block"):
            opened = len(re.findall(rf"\{{%-?\s*{tag}\s", source))
            closed = len(re.findall(rf"\{{%-?\s*end{tag}\s", source))
            assert opened == closed, f"{name}: {tag}"
        for key in re.findall(r"site\.data\.(\w+)", source):
            assert list(
                (layout.EXAMPLE / "data").glob(key + ".*")
            ), f"{name}: data.{key}"


def test_site_templates_render():
    tmpl = pytest.importorskip("inkstone.tmpl")
    pytest.importorskip("tomllib")
    from . import test_render as stand_ins

    world = stand_ins.make_site("default")
    world.site.data = {
        "projects": json.loads(layout.read(layout.EXAMPLE / "data" / "projects.json")),
        "links": [
            {"title": "Reading", "links": [{"name": "Spec", "url": "https://x.test/"}]}
        ],
    }
    projects = [
        stand_ins.make_page(
            "inkstone", "/projects/inkstone/", description="A generator."
        ),
        stand_ins.make_page("unlisted", "/projects/unlisted/"),
    ]
    env = stand_ins.make_env("default")
    env.loader = tmpl.FileSystemLoader(
        [layout.EXAMPLE / "templates"] + layout.template_dirs("default")
    )
    page = stand_ins.make_page("Projects", "/projects/", kind="section")
    html = env.get_template("projects/section.html").render(
        site=world.site,
        config=world.config,
        page=page,
        pages=projects,
        now=stand_ins.NOW,
        inkstone={"version": "0.0.test"},
    )
    assert html.count('<li class="project-card">') == 2
    assert "project-card__status--active" in html
    assert html.count("project-card__facts") == 1
    assert '<a href="https://x.test/" rel="noopener">Spec</a>' in html
    assert '<h2 class="link-list__title">Reading</h2>' in html
    assert '<a class="skip-link" href="#main">' in html


def test_custom_css_only_uses_theme_tokens():
    css = layout.strip_css_noise(
        layout.read(layout.EXAMPLE / "static" / "css" / "custom.css")
    )
    assert css.count("{") == css.count("}")
    main = layout.read(layout.THEMES / "default" / "static" / "css" / "main.css")
    theme_tokens = set(re.findall(r"(--[\w-]+)\s*:", main))
    assert set(re.findall(r"var\(\s*(--[\w-]+)", css)) <= theme_tokens


@pytest.mark.parametrize("path", CONTENT_FILES + SITE_TEMPLATES, ids=rel)
def test_example_files_are_tidy(path):
    text = layout.assert_tidy(path, rel(path))
    assert "lorem ipsum" not in text.lower()
