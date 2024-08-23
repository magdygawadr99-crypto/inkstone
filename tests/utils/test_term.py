from __future__ import annotations

import io

import pytest

from inkstone.utils import term


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture(autouse=True)
def clean_colour_state(monkeypatch):
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM"):
        monkeypatch.delenv(name, raising=False)
    # pretend the console accepted VT mode so results do not depend on
    # where the tests run
    monkeypatch.setattr(term, "_vt_mode", True)
    term.set_color(None)
    yield
    term.set_color(None)


def test_supports_color_follows_the_stream():
    assert term.supports_color(FakeTerminal()) is True
    assert term.supports_color(io.StringIO()) is False
    assert term.supports_color(object()) is False


def test_closed_stream_does_not_blow_up():
    stream = io.StringIO()
    stream.close()
    assert term.supports_color(stream) is False
    assert term.ProgressBar(1, stream=stream).enabled is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "anything"])
def test_no_color_wins(monkeypatch, value):
    monkeypatch.setenv("NO_COLOR", value)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert term.supports_color(FakeTerminal()) is False


def test_empty_no_color_is_ignored(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "")
    assert term.supports_color(FakeTerminal()) is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("3", True),
        ("true", True),
        ("0", False),
        ("false", False),
        ("", False),
    ],
)
def test_force_color(monkeypatch, value, expected):
    monkeypatch.setenv("FORCE_COLOR", value)
    assert term.supports_color(io.StringIO()) is expected


def test_dumb_terminal_and_missing_vt_mode(monkeypatch):
    monkeypatch.setenv("TERM", "dumb")
    assert term.supports_color(FakeTerminal()) is False
    monkeypatch.delenv("TERM")
    monkeypatch.setattr(term, "_vt_mode", False)
    assert term.supports_color(FakeTerminal()) is False


def test_set_color_overrides_everything(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    term.set_color(True)
    assert term.supports_color(io.StringIO()) is True
    assert term.style("x", fg="red") == "\x1b[31mx\x1b[0m"
    term.set_color(False)
    assert term.supports_color(FakeTerminal()) is False
    assert term.style("x", fg="red") == "x"


def test_enable_vt_mode_is_cached_and_boolean(monkeypatch):
    monkeypatch.setattr(term, "_vt_mode", None)
    first = term.enable_vt_mode()
    assert isinstance(first, bool)
    assert term.enable_vt_mode() is first
    assert term._vt_mode is first


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"fg": "red"}, "\x1b[31mhi\x1b[0m"),
        ({"fg": "green", "bold": True}, "\x1b[1;32mhi\x1b[0m"),
        ({"bg": "blue"}, "\x1b[44mhi\x1b[0m"),
        ({"fg": "white", "bg": "red"}, "\x1b[37;41mhi\x1b[0m"),
        ({"fg": "bright_yellow"}, "\x1b[93mhi\x1b[0m"),
        ({"fg": "gray"}, "\x1b[90mhi\x1b[0m"),
        ({"fg": "Bright-Cyan", "bg": "grey"}, "\x1b[96;100mhi\x1b[0m"),
        ({"dim": True, "italic": True, "underline": True}, "\x1b[2;3;4mhi\x1b[0m"),
        ({}, "hi"),
    ],
)
def test_style(options, expected):
    assert term.style("hi", enabled=True, **options) == expected
    assert term.style("hi", enabled=False, **options) == "hi"


def test_style_edge_cases():
    assert term.style("", fg="red", enabled=True) == ""
    with pytest.raises(ValueError, match="unknown colour: 'salmon'"):
        term.style("x", fg="salmon", enabled=True)
    # checked even when colour is off, so typos do not hide on CI
    with pytest.raises(ValueError):
        term.style("x", bg="bright_", enabled=False)


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("plain", "plain"),
        ("\x1b[31mred\x1b[0m", "red"),
        ("\x1b[1;4;38;5;208mfancy\x1b[0m text", "fancy text"),
        ("\x1b[2K\x1b[1Gcleared", "cleared"),
        ("\x1b]8;;https://example.com\x1b\\link\x1b]8;;\x1b\\", "link"),
        ("\x1b]0;window title\x07after", "after"),
        ("", ""),
    ],
)
def test_strip_ansi(text, plain):
    assert term.strip_ansi(text) == plain
    assert term.visible_len(text) == len(plain)


def test_visible_len_counts_cells_not_characters():
    assert term.visible_len("日本語") == 6
    assert term.visible_len("ｗｉｄｅ") == 8
    assert term.visible_len("e\u0301") == 1
    assert term.visible_len(term.style("日本", fg="red", enabled=True)) == 4


def test_format_table():
    rows = [["index.md", 12, "1.2 KB"], ["about/team.md", 3, "640 B"]]
    assert term.format_table(rows, headers=["file", "words", "size"], align="lrr") == (
        "file           words    size\n"
        "-------------  -----  ------\n"
        "index.md          12  1.2 KB\n"
        "about/team.md      3   640 B"
    )


def test_format_table_without_headers_and_with_ragged_rows():
    assert term.format_table([["a", "bb"], ["ccc"], []]) == "a    bb\nccc\n"
    assert term.format_table([]) == ""
    assert term.format_table([], headers=["only", "head"]) == "only  head\n----  ----"
    assert term.format_table([["x", "y"]], padding=1, align="c") == "x y"


def test_format_table_alignment():
    table = term.format_table([["a", "b", "c"], ["long", "long", "long"]], align="lcr")
    assert table == "a      b       c\nlong  long  long"
    centred = term.format_table([["ab"], ["abcdef"]], align="C")
    assert centred.split("\n")[0] == "  ab"


def test_format_table_ignores_colour_codes_when_aligning():
    red = term.style("ok", fg="green", enabled=True)
    table = term.format_table([[red, "x"], ["failed", "y"]])
    first, second = table.split("\n")
    assert term.strip_ansi(first) == "ok      x"
    assert second == "failed  y"


def test_format_table_wide_characters():
    table = term.format_table([["日本", "a"], ["abcd", "b"]])
    assert table == "日本  a\nabcd  b"


def test_progress_bar_render():
    bar = term.ProgressBar(4, label="Rendering", width=8)
    assert bar.render() == "Rendering [--------]   0% (0/4)"
    bar.update()
    assert bar.render() == "Rendering [##------]  25% (1/4)"
    bar.update(2)
    assert bar.render() == "Rendering [######--]  75% (3/4)"
    bar.update(10)
    assert bar.render() == "Rendering [########] 100% (4/4)"
    assert term.ProgressBar(0, width=4).render() == "[####] 100% (0/0)"


def test_progress_bar_draws_in_place_on_a_terminal():
    stream = FakeTerminal()
    with term.ProgressBar(2, width=4, stream=stream) as bar:
        bar.update()
        bar.update()
    output = stream.getvalue()
    assert output.startswith("\r[----]   0% (0/2)")
    assert "\r[##--]  50% (1/2)" in output
    assert "\r[####] 100% (2/2)" in output
    assert "\n" not in output
    # finish() wipes the line
    assert output.endswith("\r" + " " * 17 + "\r")


def test_progress_bar_is_silent_when_not_a_terminal():
    stream = io.StringIO()
    with term.ProgressBar(3, stream=stream) as bar:
        bar.update(3)
    assert stream.getvalue() == ""
    assert bar.count == 3


def test_progress_bar_pads_over_longer_previous_line():
    stream = FakeTerminal()
    bar = term.ProgressBar(1, width=2, stream=stream)
    bar.label = "a long label"
    bar.update(0)
    bar.label = ""
    bar.update(0)
    last = stream.getvalue().split("\r")[-1]
    assert last == "[--]   0% (0/1)" + " " * len("a long label ")


def test_spinner():
    stream = FakeTerminal()
    spinner = term.Spinner("Working", stream=stream)
    for _ in range(5):
        spinner.tick()
    frames = stream.getvalue().split("\r")[1:]
    assert frames == ["| Working", "/ Working", "- Working", "\\ Working", "| Working"]
    spinner.stop("Done.")
    assert stream.getvalue().endswith("\r" + " " * 9 + "\rDone.\n")


def test_spinner_when_not_a_terminal_only_prints_the_final_message():
    stream = io.StringIO()
    spinner = term.Spinner(stream=stream)
    spinner.tick()
    spinner.stop()
    assert stream.getvalue() == ""
    spinner.stop("Finished")
    assert stream.getvalue() == "Finished\n"
    assert term.Spinner(enabled=True, stream=stream).render() == "|"
