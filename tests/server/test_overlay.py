from __future__ import annotations

import re

import pytest

from inkstone.errors import BuildError, ContentError
from inkstone.server.overlay import (
    describe_error,
    render_error_page,
    render_overlay,
    source_excerpt,
)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "post.md"
    path.write_text("".join(f"line {n}\n" for n in range(1, 13)), encoding="utf-8")
    return path


def test_excerpt_shows_the_lines_around_the_target(source):
    assert source_excerpt(source, 5).splitlines() == [
        "  2 | line 2",
        "  3 | line 3",
        "  4 | line 4",
        "> 5 | line 5",
        "  6 | line 6",
        "  7 | line 7",
        "  8 | line 8",
    ]


def test_excerpt_lines_up_numbers_of_different_widths(source):
    assert source_excerpt(source, 9, context=1).splitlines() == [
        "   8 | line 8",
        ">  9 | line 9",
        "  10 | line 10",
    ]


def test_excerpt_stops_at_the_ends_of_the_file(source):
    assert source_excerpt(source, 1).splitlines()[0] == "> 1 | line 1"
    assert source_excerpt(source, 12).splitlines()[-1] == "> 12 | line 12"
    assert len(source_excerpt(source, 12).splitlines()) == 4


def test_excerpt_tidies_awkward_lines(tmp_path):
    path = tmp_path / "template.html"
    path.write_text("\t<p>\n" + "x" * 500 + "\n\n", encoding="utf-8")
    first, second, third = source_excerpt(path, 2).splitlines()
    assert first == "  1 |     <p>"
    assert second.endswith("xxx...")
    assert len(second) < 260
    assert third == "  3 |"


def test_excerpt_survives_a_file_that_is_not_utf8(tmp_path):
    path = tmp_path / "latin1.md"
    path.write_bytes(b"title: caf\xe9\nbody\n")
    assert source_excerpt(path, 2).splitlines()[-1] == "> 2 | body"


@pytest.mark.parametrize("line", [None, 0, -3, 13, "5"])
def test_excerpt_is_empty_for_a_line_that_is_not_there(source, line):
    assert source_excerpt(source, line) == ""


def test_excerpt_is_empty_without_a_readable_file(tmp_path):
    assert source_excerpt(None, 3) == ""
    assert source_excerpt(tmp_path / "missing.md", 3) == ""
    assert source_excerpt(tmp_path, 3) == ""


def test_expected_error_gets_message_and_excerpt_but_no_traceback(source):
    title, detail = describe_error(ContentError("bad date", path=source, line=5))
    assert title == "Build failed"
    assert detail.splitlines()[0] == f"{source}:5: bad date"
    assert "> 5 | line 5" in detail
    assert "Traceback" not in detail


def test_expected_error_without_a_location(source):
    assert describe_error(BuildError("nothing to build")) == (
        "Build failed",
        "nothing to build",
    )
    _, detail = describe_error(ContentError("unreadable", path=source))
    assert detail == f"{source}: unreadable"


def test_cause_of_an_expected_error_is_mentioned():
    try:
        try:
            int("twelve")
        except ValueError as inner:
            raise BuildError("can't read the post count") from inner
    except BuildError as exc:
        _, detail = describe_error(exc)
    assert detail.startswith("can't read the post count\n\n")
    assert "Caused by ValueError: invalid literal for int()" in detail


def test_unexpected_exception_gets_the_whole_traceback():
    try:
        {}["title"]
    except KeyError as exc:
        title, detail = describe_error(exc)
    assert title == "Build failed: KeyError"
    assert detail.startswith("KeyError: 'title'\n\n")
    assert "Traceback (most recent call last):" in detail
    assert "test_overlay.py" in detail


def test_exception_without_a_message():
    try:
        raise RuntimeError
    except RuntimeError as exc:
        _, detail = describe_error(exc)
    assert detail.startswith("RuntimeError\n\n")


def test_syntax_error_points_into_the_file(tmp_path):
    plugin = tmp_path / "plugin.py"
    plugin.write_text("x = 1\ny = x +\nz = 3\n", encoding="utf-8")
    try:
        compile(plugin.read_text(encoding="utf-8"), str(plugin), "exec")
    except SyntaxError as exc:
        title, detail = describe_error(exc)
    assert title == "Build failed: SyntaxError"
    assert "> 2 | y = x +" in detail


def test_overlay_escapes_what_it_is_given():
    fragment = render_overlay(
        "<img src=x onerror=alert(1)>", "</pre><script>x</script>"
    )
    assert "<img" not in fragment
    assert "<script>" not in fragment
    assert "&lt;img src=x onerror=alert(1)&gt;" in fragment
    assert "&lt;/pre&gt;&lt;script&gt;x&lt;/script&gt;" in fragment


def test_overlay_can_be_dismissed_and_announces_itself():
    fragment = render_overlay("Build failed", "oops")
    assert re.search(r"<button[^>]*data-inkstone-dismiss", fragment)
    assert 'role="alertdialog"' in fragment
    assert fragment.lstrip().startswith("<style>")


def test_overlay_marks_the_guilty_line_and_dims_the_traceback():
    detail = (
        "post.md:2: oops\n\n  1 | one\n> 2 | <two>\n  3 | three\n\n"
        "Traceback (most recent call last):\n"
        '  File "build.py", line 7, in render\n'
        "    explode()"
    )
    fragment = render_overlay("Build failed", detail)
    assert '<span class="ink-hit">&gt; 2 | &lt;two&gt;</span>' in fragment
    assert fragment.count('<span class="ink-hit">') == 1
    assert fragment.count('<span class="ink-dim">') == 2
    assert "\n    explode()</pre>" in fragment


def test_error_page_is_a_complete_document():
    page = render_error_page("Build failed: KeyError", "boom & bust")
    assert page.startswith("<!doctype html>\n<html")
    assert "data-inkstone-error" in page.splitlines()[1]
    assert "<title>Build failed: KeyError</title>" in page
    assert "boom &amp; bust" in page
    assert page.rstrip().endswith("</body>\n</html>")
    # nothing to dismiss when the error is the whole page
    assert "data-inkstone-dismiss" not in page
    assert "<button" not in page
