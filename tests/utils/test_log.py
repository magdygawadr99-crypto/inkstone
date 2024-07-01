from __future__ import annotations

import io

import pytest

from inkstone.utils import log, term
from inkstone.utils.log import Logger


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture(autouse=True)
def plain_environment(monkeypatch):
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(term, "_vt_mode", True)
    term.set_color(None)


@pytest.fixture
def stream():
    buffer = io.StringIO()
    log.set_stream(buffer)
    log.set_level(log.NORMAL)
    log.reset()
    yield buffer
    log.set_stream(None)
    log.set_level(log.NORMAL)
    log.reset()


def emit_everything(logger):
    logger.error("e")
    logger.warning("w")
    logger.info("i")
    logger.verbose("v")
    logger.debug("d")


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (log.QUIET, "error: e\nwarning: w\n"),
        (log.NORMAL, "error: e\nwarning: w\ni\n"),
        (log.VERBOSE, "error: e\nwarning: w\ni\nv\n"),
        (log.DEBUG, "error: e\nwarning: w\ni\nv\ndebug: d\n"),
        ("quiet", "error: e\nwarning: w\n"),
        ("Verbose", "error: e\nwarning: w\ni\nv\n"),
    ],
)
def test_levels(level, expected):
    buffer = io.StringIO()
    emit_everything(Logger(level, buffer))
    assert buffer.getvalue() == expected


def test_level_values_are_clamped_and_names_checked():
    assert Logger(99).level == log.DEBUG
    assert Logger(-5).level == log.QUIET
    with pytest.raises(ValueError, match="unknown log level: 'chatty'"):
        Logger("chatty")


def test_counters():
    logger = Logger(log.QUIET, io.StringIO())
    logger.warning("one")
    logger.warning("two")
    logger.error("bad")
    logger.info("not counted")
    assert (logger.warnings, logger.errors) == (2, 1)
    logger.reset()
    assert (logger.warnings, logger.errors) == (0, 0)


def test_once_deduplicates():
    buffer = io.StringIO()
    logger = Logger(stream=buffer)
    assert logger.once("deprecated thing") is True
    assert logger.once("deprecated thing") is False
    assert logger.once("another thing") is True
    assert buffer.getvalue() == "warning: deprecated thing\nwarning: another thing\n"
    assert logger.warnings == 2


def test_once_with_arguments_and_explicit_key():
    buffer = io.StringIO()
    logger = Logger(stream=buffer)
    assert logger.once("missing image %s", "a.png")
    assert logger.once("missing image %s", "b.png")
    assert not logger.once("missing image %s", "a.png")
    assert logger.once("layout %r not found", "x", key="layout")
    assert not logger.once("layout %r not found", "y", key="layout")
    assert buffer.getvalue().count("\n") == 3
    logger.reset()
    assert logger.once("missing image %s", "a.png")


def test_message_formatting():
    buffer = io.StringIO()
    logger = Logger(stream=buffer)
    logger.info("built %d pages in %s", 12, "1.2 s")
    logger.info("100% done")
    logger.info(ValueError("an exception object"))
    logger.warning("%r is not a date", "soon")
    assert buffer.getvalue() == (
        "built 12 pages in 1.2 s\n"
        "100% done\n"
        "an exception object\n"
        "warning: 'soon' is not a date\n"
    )


def test_prefixes_are_coloured_on_a_terminal():
    stream = FakeTerminal()
    emit_everything(Logger(log.DEBUG, stream))
    assert stream.getvalue() == (
        "\x1b[1;31merror:\x1b[0m e\n"
        "\x1b[33mwarning:\x1b[0m w\n"
        "i\n"
        "v\n"
        "\x1b[90mdebug:\x1b[0m d\n"
    )


def test_no_color_is_respected(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    stream = FakeTerminal()
    Logger(stream=stream).warning("plain")
    assert stream.getvalue() == "warning: plain\n"


def test_default_stream_is_stderr_looked_up_late(capsys):
    Logger().warning("to stderr")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "warning: to stderr\n"


def test_stream_can_be_swapped_on_an_instance():
    logger = Logger()
    first, second = io.StringIO(), io.StringIO()
    logger.stream = first
    logger.info("one")
    logger.stream = second
    logger.info("two")
    assert (first.getvalue(), second.getvalue()) == ("one\n", "two\n")


def test_module_level_functions(stream):
    log.info("hello %s", "there")
    log.verbose("hidden")
    log.warning("careful")
    log.error("broken")
    log.debug("hidden too")
    assert stream.getvalue() == "hello there\nwarning: careful\nerror: broken\n"
    assert log.warning_count() == 1
    assert log.error_count() == 1


def test_module_level_once_and_reset(stream):
    assert log.once("only once")
    assert not log.once("only once")
    assert log.warning_count() == 1
    log.reset()
    assert log.warning_count() == 0
    assert log.once("only once")
    assert stream.getvalue() == "warning: only once\nwarning: only once\n"


def test_module_level_set_level(stream):
    log.set_level("debug")
    assert log.get_level() == log.DEBUG
    log.debug("now visible")
    log.set_level(log.QUIET)
    log.info("silenced")
    assert stream.getvalue() == "debug: now visible\n"


def test_module_level_stream_reset_goes_back_to_stderr(stream, capsys):
    log.set_stream(None)
    log.info("on stderr again")
    assert stream.getvalue() == ""
    assert capsys.readouterr().err == "on stderr again\n"
