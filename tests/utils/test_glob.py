from __future__ import annotations

import re

import pytest

from inkstone.utils.glob import GlobSet, translate


def matches(pattern, path, is_dir=False):
    return GlobSet([pattern]).match(path, is_dir=is_dir)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("*.tmp", "a.tmp", True),
        ("*.tmp", "deep/down/a.tmp", True),
        ("*.tmp", "a.tmp.bak", False),
        ("*.tmp", "tmp", False),
        ("notes.txt", "notes.txt", True),
        ("notes.txt", "sub/notes.txt", True),
        ("notes.txt", "my-notes.txt", False),
        ("/notes.txt", "notes.txt", True),
        ("/notes.txt", "sub/notes.txt", False),
        ("docs/*.md", "docs/a.md", True),
        ("docs/*.md", "docs/sub/a.md", False),
        ("docs/*.md", "other/docs/a.md", False),
        ("*", "anything", True),
        ("*", "any/depth/at/all", True),
        ("a*c", "abc", True),
        ("a*c", "ac", True),
        ("a*c", "a/c", False),
        ("?.txt", "a.txt", True),
        ("?.txt", "ab.txt", False),
        ("a?c", "a/c", False),
        ("file[0-9].txt", "file7.txt", True),
        ("file[0-9].txt", "filex.txt", False),
        ("file[!0-9].txt", "filex.txt", True),
        ("file[^0-9].txt", "file7.txt", False),
        ("[abc]*", "banana", True),
        ("[abc]*", "date", False),
        ("x[]]y", "x]y", True),
        ("x[!]]y", "xay", True),
        ("x[!]]y", "x]y", False),
        ("a[!b]c", "a/c", False),
        ("a[", "a[", True),
        ("lit\\*eral", "lit*eral", True),
        ("lit\\*eral", "literal", False),
        ("a.b", "a.b", True),
        ("a.b", "axb", False),
        ("a+b(c)", "a+b(c)", True),
        ("**/x.py", "x.py", True),
        ("**/x.py", "a/b/x.py", True),
        ("src/**", "src/a", True),
        ("src/**", "src/a/b/c", True),
        ("src/**", "src", False),
        ("src/**", "other/src/a", False),
        ("a/**/z", "a/z", True),
        ("a/**/z", "a/b/c/z", True),
        ("a/**/z", "a/b/c/zz", False),
        ("**", "anything/at/all", True),
        ("a**b", "aXXb", True),
        ("a**b", "a/b", False),
        ("**/drafts/**", "content/drafts/post.md", True),
        ("**/drafts/**", "drafts/post.md", True),
        ("**/drafts/**", "content/drafts", False),
    ],
)
def test_single_pattern(pattern, path, expected):
    assert matches(pattern, path) is expected


@pytest.mark.parametrize(
    ("pattern", "path", "is_dir", "expected"),
    [
        ("build/", "build", True, True),
        ("build/", "build", False, False),
        ("build/", "build/out.html", False, True),
        ("build/", "pkg/build/deep/out.html", False, True),
        ("build/", "rebuild", True, False),
        ("/build/", "pkg/build", True, False),
        ("build", "build", True, True),
        ("build", "build", False, True),
        ("node_modules", "node_modules/pkg/index.js", False, True),
        ("docs/api/", "docs/api", True, True),
        ("docs/api/", "docs/api/index.html", False, True),
        ("docs/api/", "x/docs/api", True, False),
        ("*.egg-info/", "pkg.egg-info/PKG-INFO", False, True),
    ],
)
def test_directory_patterns(pattern, path, is_dir, expected):
    assert matches(pattern, path, is_dir) is expected


def test_last_matching_pattern_wins():
    rules = GlobSet(["*.log", "!important.log", "/important.log"])
    assert rules.match("debug.log")
    assert not rules.match("sub/important.log")
    assert rules.match("important.log")


def test_negation_can_reach_into_an_ignored_directory():
    rules = GlobSet(["build/", "!build/keep.txt"])
    assert rules.match("build", is_dir=True)
    assert rules.match("build/other.txt")
    assert not rules.match("build/keep.txt")
    assert rules.has_negation
    assert not GlobSet(["build/"]).has_negation


def test_negation_alone_matches_nothing():
    rules = GlobSet(["!*.md"])
    assert not rules.match("a.md")
    assert not rules.match("a.txt")


def test_comments_blank_lines_and_escapes():
    rules = GlobSet(["# a comment", "", "   ", "\\#literal", "\\!bang", "  *.bak  "])
    assert rules.patterns == ["\\#literal", "\\!bang", "*.bak"]
    assert len(rules) == 3
    assert rules.match("#literal")
    assert rules.match("!bang")
    assert rules.match("x.bak")
    assert not rules.match("# a comment")


@pytest.mark.parametrize(
    "path",
    ["a/b/c.txt", "a\\b\\c.txt", "./a/b/c.txt", "/a/b/c.txt", "a/b/c.txt/"],
)
def test_paths_are_normalised_before_matching(path):
    assert GlobSet(["a/b/*.txt"]).match(path)


def test_empty_set_and_degenerate_input():
    empty = GlobSet()
    assert not empty
    assert len(empty) == 0
    assert not empty.match("anything")
    assert not GlobSet(["/", "!", "!/"])
    assert not GlobSet(["*"]).match("")
    assert not GlobSet(["*"]).match(".")


def test_single_string_is_one_pattern():
    rules = GlobSet("*.md")
    assert rules.patterns == ["*.md"]
    assert rules.match("a.md") and not rules.match("m")


def test_ignore_case():
    assert not GlobSet(["*.JPG"]).match("photo.jpg")
    assert GlobSet(["*.JPG"], ignore_case=True).match("photo.jpg")
    assert GlobSet(["Docs/"], ignore_case=True).match("docs/readme.md")


def test_filter_returns_unmatched_paths_in_order():
    rules = GlobSet(["*.pyc", "__pycache__/", "!keep.pyc"])
    paths = ["b.py", "a.pyc", "__pycache__/x.py", "keep.pyc", "a.py"]
    assert rules.filter(paths) == ["b.py", "keep.pyc", "a.py"]


def test_bad_pattern_raises_value_error():
    with pytest.raises(ValueError, match="bad pattern"):
        GlobSet(["[z-a]"])


def test_repr():
    assert repr(GlobSet(["*.md", "!x.md"])) == "GlobSet(['*.md', '!x.md'])"


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("*.md", r"(?s:(?:.*/)?[^/]*\.md)\Z"),
        ("/top", r"(?s:top)\Z"),
        ("a/b", r"(?s:a/b)\Z"),
        ("src/**/*.py", r"(?s:src/(?:.*/)?[^/]*\.py)\Z"),
        ("a/**", r"(?s:a/.*)\Z"),
        ("dir/", r"(?s:(?:.*/)?dir)\Z"),
        ("x?[a-c]", r"(?s:(?:.*/)?x[^/](?!/)[a-c])\Z"),
    ],
)
def test_translate(pattern, expected):
    assert translate(pattern) == expected


def test_translated_pattern_works_with_re():
    regex = re.compile(translate("assets/**/*.min.js"))
    assert regex.match("assets/vendor/lib/x.min.js")
    assert regex.match("assets/x.min.js")
    assert not regex.match("assets/x.js")
    assert not regex.match("static/assets/x.min.js")
