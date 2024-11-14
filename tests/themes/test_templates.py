"""Static checks on the theme templates. Nothing here renders anything, so
these run even when the template engine is broken."""

from __future__ import annotations

import re

import pytest

from . import layout

# Every template each theme ships. A new template has to be added here, which
# is the point: the list is what the docs are checked against.
EXPECTED = {
    "default": {
        "404.html",
        "base.html",
        "index.html",
        "page.html",
        "search.html",
        "section.html",
        "taxonomy.html",
        "term.html",
        "posts/page.html",
        "partials/breadcrumbs.html",
        "partials/footer.html",
        "partials/head.html",
        "partials/header.html",
        "partials/macros.html",
        "partials/pagination.html",
        "partials/post_card.html",
        "partials/post_meta.html",
        "partials/post_nav.html",
        "partials/related.html",
        "partials/search_box.html",
        "partials/series.html",
        "partials/tag_list.html",
        "partials/toc.html",
    },
    "paper": {
        "base.html",
        "partials/footer.html",
        "partials/header.html",
        "partials/post_card.html",
        "partials/post_meta.html",
    },
}

# What the builder looks up by name (see the table in docs/templates.md).
REQUIRED_BY_BUILDER = [
    "base.html",
    "index.html",
    "page.html",
    "section.html",
    "taxonomy.html",
    "term.html",
    "404.html",
]

OPENERS = {
    "block": "endblock",
    "if": "endif",
    "for": "endfor",
    "macro": "endmacro",
    "call": "endcall",
    "filter": "endfilter",
    "with": "endwith",
    "autoescape": "endautoescape",
}
CLOSERS = set(OPENERS.values()) | {"endset"}
STANDALONE = {"extends", "include", "import", "from", "set", "do", "break", "continue"}

ALL_TEMPLATES = layout.theme_template_params()


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_template_list_is_tracked(theme):
    assert set(layout.own_templates(theme)) == EXPECTED[theme]


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
@pytest.mark.parametrize("name", REQUIRED_BY_BUILDER)
def test_builder_templates_resolve(theme, name):
    assert layout.find_template(theme, name) is not None


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_block_tags_are_balanced(theme, name):
    source = layout.source_of(theme, name)
    stack = []
    for match in layout.TAG_RE.finditer(source):
        tag, rest = match.group(1), match.group(2)
        line = source.count("\n", 0, match.start()) + 1
        where = f"{theme}/{name}:{line}"
        if tag in OPENERS:
            stack.append((tag, line))
        elif tag == "set" and "=" not in rest:
            stack.append(("set", line))
        elif tag in ("elif", "else"):
            assert stack, f"{where}: {tag} outside of a block"
            allowed = ("if",) if tag == "elif" else ("if", "for")
            assert stack[-1][0] in allowed, f"{where}: {tag} inside {stack[-1][0]}"
        elif tag in CLOSERS:
            assert stack, f"{where}: {tag} without an opening tag"
            opened, opened_at = stack.pop()
            expected = OPENERS.get(opened, "endset")
            assert (
                tag == expected
            ), f"{where}: {tag} closes the {opened} opened on line {opened_at}"
        else:
            assert tag in STANDALONE, f"{where}: unknown tag {tag!r}"
    assert (
        not stack
    ), f"{theme}/{name}: unclosed {stack[-1][0]} from line {stack[-1][1]}"


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_delimiters_are_balanced(theme, name):
    source = layout.read(layout.find_template(theme, name))
    assert source.count("{#") == source.count("#}")
    source = layout.COMMENT_RE.sub("", source)
    assert source.count("{%") == source.count("%}")
    assert source.count("{{") == source.count("}}")
    # a tag that never closes swallows the next one
    for match in re.finditer(r"\{%(.*?)%\}|\{\{(.*?)\}\}", source, re.S):
        inner = match.group(1) or match.group(2) or ""
        assert "{%" not in inner and "{{" not in inner, f"{name}: {match.group()[:60]}"


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_referenced_templates_exist(theme, name):
    source = layout.source_of(theme, name)
    for kind, _quote, target in layout.REFERENCE_RE.findall(source):
        assert (
            layout.find_template(theme, target) is not None
        ), f"{theme}/{name}: {kind} of missing template {target!r}"


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_inherited_templates_resolve_in_the_child_theme(theme):
    # default's page.html extends "base.html"; under paper that is paper's
    # base.html, and whatever it pulls in has to be there too
    for name in layout.all_templates(theme):
        for _kind, _quote, target in layout.REFERENCE_RE.findall(
            layout.source_of(theme, name)
        ):
            assert layout.find_template(theme, target) is not None, (name, target)


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_asset_paths_exist(theme, name):
    source = layout.source_of(theme, name)
    for _quote, path in layout.ASSET_RE.findall(source):
        if path in layout.GENERATED_ASSETS:
            continue
        assert (
            layout.find_static(theme, path) is not None
        ), f"{theme}/{name}: asset({path!r}) is not in static/"


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_block_names_are_unique(theme, name):
    blocks = layout.BLOCK_RE.findall(layout.source_of(theme, name))
    assert len(blocks) == len(set(blocks))


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_children_only_override_blocks_the_base_has(theme):
    base_blocks = set(layout.BLOCK_RE.findall(layout.source_of(theme, "base.html")))
    assert {"title", "head", "content", "scripts"} <= base_blocks
    for name in layout.all_templates(theme):
        source = layout.source_of(theme, name)
        if not re.search(r"\{%-?\s*extends\s+[\"']base\.html[\"']", source):
            continue
        unknown = set(layout.BLOCK_RE.findall(source)) - base_blocks
        assert not unknown, f"{theme}: {name} overrides {sorted(unknown)}"


def test_paper_keeps_the_block_names_of_default():
    default = set(layout.BLOCK_RE.findall(layout.source_of("default", "base.html")))
    paper = set(layout.BLOCK_RE.findall(layout.source_of("paper", "base.html")))
    assert default == paper


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_macros_used_are_defined(theme, name):
    macros = set(
        re.findall(
            r"\{%-?\s*macro\s+(\w+)", layout.source_of(theme, "partials/macros.html")
        )
    )
    source = layout.source_of(theme, name)
    used = set(re.findall(r"\bm\.(\w+)\(", source))
    if used:
        assert re.search(r"import\s+[\"']partials/macros\.html[\"']\s+as\s+m\b", source)
    assert used <= macros, f"{theme}/{name}: no macro named {sorted(used - macros)}"


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_every_partial_is_used(theme):
    included = set()
    for name in layout.all_templates(theme):
        for _kind, _quote, target in layout.REFERENCE_RE.findall(
            layout.source_of(theme, name)
        ):
            included.add(target)
    # only the theme's own files: a child theme is free to stop using a
    # partial of its parent (paper has no search box in the header)
    partials = {n for n in layout.own_templates(theme) if n.startswith("partials/")}
    assert partials <= included, sorted(partials - included)


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_no_external_requests(theme, name):
    source = layout.source_of(theme, name)
    loads = re.findall(
        r"<(?:script|link|img|iframe|source|video|audio)\b[^>]*?"
        r"(?:src|href)\s*=\s*[\"'](?:https?:)?//[^\"']+",
        source,
        re.S | re.I,
    )
    assert not loads, f"{theme}/{name} loads from another host: {loads}"
    assert "@import" not in source
    assert "fonts.googleapis" not in source


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_base_has_the_accessibility_basics(theme):
    source = layout.source_of(theme, "base.html")
    assert re.search(r"<html lang=\"\{\{\s*site\.language\s*\}\}\"", source)
    assert '<a class="skip-link" href="#main">' in source
    assert re.search(r"<main id=\"main\"[^>]*tabindex=\"-1\"", source)
    assert source.index("skip-link") < source.index("<main")
    assert '<meta name="viewport"' in source
    assert source.lstrip().lower().startswith("<!doctype html>")


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_internal_links_go_through_url_for(theme, name):
    # a literal href="/..." breaks as soon as base_url has a sub-path
    source = layout.source_of(theme, name)
    literal = re.findall(r"(?:href|src|action)=\"/[^\"{]*\"", source)
    assert not literal, f"{theme}/{name}: {literal}"


@pytest.mark.parametrize("theme,name", ALL_TEMPLATES)
def test_images_and_icons_have_text_alternatives(theme, name):
    source = layout.source_of(theme, name)
    for tag in re.findall(r"<img\b[^>]*>", source, re.S):
        assert re.search(r"\balt=", tag), f"{theme}/{name}: {tag}"
    for tag in re.findall(r"<svg\b[^>]*>", source, re.S):
        assert 'aria-hidden="true"' in tag or "aria-label" in tag, f"{name}: {tag}"
    for tag in re.findall(r"<nav\b[^>]*>", source, re.S):
        assert "aria-label" in tag, f"{theme}/{name}: unlabelled {tag}"
