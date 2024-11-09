from __future__ import annotations

import pytest

from inkstone.cli.parser import build_parser

COMMANDS = [
    "new",
    "build",
    "serve",
    "check",
    "clean",
    "config",
    "list",
    "highlight-css",
    "version",
]


def parse(*argv):
    return build_parser().parse_args(list(argv))


def test_global_options_default_to_off():
    args = parse("build")
    assert args.command == "build"
    assert (args.root, args.config) == (None, None)
    assert not (args.quiet or args.verbose or args.debug or args.no_color)
    assert callable(args.run)


@pytest.mark.parametrize(
    "argv",
    [
        "-C elsewhere -c other.toml -q --debug --no-color build",
        "build -C elsewhere -c other.toml -q --debug --no-color",
        "-C elsewhere -q build -c other.toml --debug --no-color",
        "--root elsewhere build --config other.toml --quiet --debug --no-color",
    ],
)
def test_global_options_work_before_and_after_the_command(argv):
    args = parse(*argv.split())
    assert (args.root, args.config) == ("elsewhere", "other.toml")
    assert args.quiet and args.debug and args.no_color
    assert not args.verbose


def test_options_after_the_command_do_not_reset_earlier_ones():
    args = parse("-v", "-C", "x", "list", "--drafts")
    assert args.verbose and args.root == "x"
    args = parse("-C", "first", "list", "-C", "second")
    assert args.root == "second"


@pytest.mark.parametrize("command", [c for c in COMMANDS if c != "new"])
def test_every_command_parses_bare(command):
    args = parse(command)
    assert args.command == command
    assert callable(args.run)


BUILD_FLAGS = (
    "drafts",
    "future",
    "clean",
    "no_incremental",
    "minify",
    "fingerprint",
    "profile",
)


def test_build_options():
    args = parse("build")
    assert not any(getattr(args, flag) for flag in BUILD_FLAGS)
    assert args.output is None and args.base_url is None
    line = (
        "build --drafts --future --output out --base-url https://e.org/ --clean "
        "--no-incremental --minify --fingerprint --profile"
    )
    args = parse(*line.split())
    assert all(getattr(args, flag) for flag in BUILD_FLAGS)
    assert (args.output, args.base_url) == ("out", "https://e.org/")


def test_serve_options():
    args = parse("serve")
    assert (args.host, args.port) == (None, None)
    assert not (args.no_livereload or args.open or args.drafts or args.future)
    line = "serve --host 0.0.0.0 --port 8080 --no-livereload --open --drafts --future"
    args = parse(*line.split())
    assert (args.host, args.port) == ("0.0.0.0", 8080)
    assert args.no_livereload and args.open and args.drafts and args.future


def test_check_list_config_and_highlight_options():
    args = parse("check", "--external", "--strict")
    assert args.external and args.strict

    args = parse("list")
    assert (args.section, args.tag, args.drafts) == (None, None, False)
    assert (args.format, args.sort) == ("table", "date")
    line = "list --section posts --tag x --drafts --format json --sort title"
    args = parse(*line.split())
    assert (args.section, args.tag, args.drafts) == ("posts", "x", True)
    assert (args.format, args.sort) == ("json", "title")

    args = parse("config")
    assert args.key is None and not args.json and not args.defaults
    args = parse("config", "--json", "--defaults", "build.minify")
    assert args.key == "build.minify" and args.json and args.defaults

    args = parse("highlight-css")
    assert (args.style, args.selector) == (None, ".highlight")
    args = parse("highlight-css", "--style", "dusk", "--selector", "pre code")
    assert (args.style, args.selector) == ("dusk", "pre code")


def test_new_options():
    args = parse("new", "site", "blog")
    assert (args.kind, args.path, args.theme, args.title, args.force) == (
        "site",
        "blog",
        "default",
        None,
        False,
    )
    args = parse("new", "site", "blog", "--theme", "paper", "--title", "T", "--force")
    assert (args.theme, args.title, args.force) == ("paper", "T", True)

    args = parse("new", "post", "Hello world")
    assert args.title == ["Hello world"]
    assert (args.section, args.draft, args.date, args.slug, args.tags) == (
        "posts",
        False,
        None,
        None,
        None,
    )
    line = "Two words --section notes --draft --date 2024-06-01 --slug s --tags a,b"
    args = parse("new", "post", *line.split())
    assert args.title == ["Two", "words"]
    assert (args.section, args.draft, args.date, args.slug, args.tags) == (
        "notes",
        True,
        "2024-06-01",
        "s",
        "a,b",
    )

    args = parse("new", "page", "projects/widget.md", "-q")
    assert (args.kind, args.path, args.quiet) == ("page", "projects/widget.md", True)


@pytest.mark.parametrize(
    "argv, message",
    [
        (("biuld",), "'biuld' is not a command, did you mean 'build'?"),
        (("sevre",), "did you mean 'serve'?"),
        (("lsit",), "did you mean 'list'?"),
        (("highlight",), "did you mean 'highlight-css'?"),
        (("frobnicate",), "'frobnicate' is not a command"),
        (("new", "psot", "x"), "'psot' is not a command, did you mean 'post'?"),
        (("new", "sight", "x"), "did you mean 'site'?"),
    ],
)
def test_mistyped_commands_get_a_suggestion(capsys, argv, message):
    with pytest.raises(SystemExit) as caught:
        parse(*argv)
    assert caught.value.code == 2
    err = capsys.readouterr().err
    assert message in err
    assert "--help" in err
    assert "choose from" not in err


def test_no_suggestion_for_something_unlike_any_command(capsys):
    with pytest.raises(SystemExit):
        parse("frobnicate")
    assert "did you mean" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv, message",
    [
        (("build", "--nope"), "unrecognized arguments: --nope"),
        (("build", "--output"), "expected one argument"),
        (("serve", "--port", "http"), "not a port number: 'http'"),
        (("serve", "--port", "70000"), "ports go from 0 to 65535"),
        (("list", "--format", "xml"), "argument --format: invalid choice: 'xml'"),
        (("new",), "required"),
        (("new", "post"), "required"),
        (("new", "site"), "required"),
        (("config", "a", "b"), "unrecognized arguments: b"),
    ],
)
def test_usage_errors_are_short_and_exit_with_2(capsys, argv, message):
    with pytest.raises(SystemExit) as caught:
        parse(*argv)
    assert caught.value.code == 2
    err = capsys.readouterr().err
    assert message in err
    assert len(err.strip().splitlines()) == 2


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit) as caught:
        parse("--help")
    assert caught.value.code == 0
    out = capsys.readouterr().out
    for command in COMMANDS:
        assert f"\n    {command} " in out
    assert "global options:" in out and "--no-color" in out


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_has_help_with_the_global_options(capsys, command):
    with pytest.raises(SystemExit) as caught:
        parse(command, "--help")
    assert caught.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith(f"usage: inkstone {command}")
    assert "--root DIR" in out and "--debug" in out
