from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import inkstone
from inkstone.cli import app as cli_app
from inkstone.cli import main, version
from inkstone.errors import BuildError, ContentError
from inkstone.utils import log, term

from .conftest import write


def test_no_command_prints_help_and_fails(run):
    result = run()
    assert result.code == 2
    assert result.out == ""
    assert result.err.startswith("usage: inkstone")
    assert "commands:" in result.err


def test_help_and_version_flags_succeed(run):
    assert run("--help").code == 0
    result = run("--version")
    assert (result.code, result.out) == (0, f"inkstone {inkstone.__version__}\n")


def test_usage_errors_return_2_instead_of_exiting(run):
    result = run("build", "--no-such-option")
    assert result.code == 2
    assert "unrecognized arguments" in result.err
    assert run("biuld").code == 2


def test_main_uses_sys_argv_by_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["inkstone", "version"])
    assert main() == 0
    assert capsys.readouterr().out.startswith("inkstone ")


def test_python_dash_m_inkstone():
    project = Path(inkstone.__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONPATH=str(project))
    done = subprocess.run(
        [sys.executable, "-m", "inkstone", "version"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert done.returncode == 0
    assert done.stdout.strip() == f"inkstone {inkstone.__version__}"


class TestFindingTheSite:
    def test_in_the_site_root(self, run, site):
        assert run("config", "title").out == "Test Site\n"

    def test_walks_up_from_a_subdirectory(self, run, site, monkeypatch):
        monkeypatch.chdir(site / "content" / "posts")
        assert run("config", "title").out == "Test Site\n"

    def test_the_nearest_site_wins(self, run, site, monkeypatch):
        inner = site / "nested"
        write(inner / "inkstone.toml", 'title = "Inner"\n')
        (inner / "content").mkdir()
        monkeypatch.chdir(inner / "content")
        assert run("config", "title").out == "Inner\n"

    @pytest.mark.parametrize("name", ["inkstone.yaml", "inkstone.yml", "inkstone.json"])
    def test_other_config_formats_count_too(self, run, tmp_path, monkeypatch, name):
        text = '{"title": "J"}' if name.endswith("json") else "title: J\n"
        write(tmp_path / name, text)
        monkeypatch.chdir(tmp_path)
        assert run("config", "title").out == "J\n"

    def test_dash_c_names_another_site(self, run, site, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert run("-C", "site", "config", "title").out == "Test Site\n"
        assert run("config", "-C", site, "title").out == "Test Site\n"

    def test_dash_c_beats_the_current_directory(self, run, site, tmp_path):
        other = tmp_path / "other"
        write(other / "inkstone.toml", 'title = "Other"\n')
        assert run("-C", other, "config", "title").out == "Other\n"

    def test_no_site_here(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("build")
        assert result.code == 1
        assert result.out == ""
        assert result.err.startswith("error: no inkstone site here")
        assert "inkstone new site NAME" in result.err
        assert "-C DIR" in result.err
        assert "Traceback" not in result.err

    @pytest.mark.parametrize(
        "command", ["build", "serve", "check", "clean", "list", "config"]
    )
    def test_every_site_command_says_so(self, run, tmp_path, monkeypatch, command):
        monkeypatch.chdir(tmp_path)
        result = run(command)
        assert result.code == 1
        assert "no inkstone site here" in result.err

    def test_dash_c_missing_directory(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("-C", "nowhere", "build")
        assert (result.code, result.err) == (1, "error: nowhere: no such directory\n")

    def test_dash_c_directory_without_a_config(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plain").mkdir()
        result = run("-C", "plain", "build")
        assert result.code == 1
        assert "plain is not an inkstone site (no inkstone.toml in it)" in result.err

    def test_config_file_option(self, run, site):
        write(site / "production.toml", 'title = "Live"\nbase_url = "https://e.org/"\n')
        assert run("-c", "production.toml", "config", "title").out == "Live\n"
        assert run("config", "--config", "production.toml", "base_url").out == (
            "https://e.org/\n"
        )

    def test_config_file_is_relative_to_the_cwd(self, run, site, monkeypatch):
        write(site / "content" / "alt.toml", 'title = "Alt"\n')
        monkeypatch.chdir(site / "content")
        assert run("-c", "alt.toml", "config", "title").out == "Alt\n"

    def test_config_file_falls_back_to_the_site_directory(
        self, run, site, tmp_path, monkeypatch
    ):
        write(site / "production.toml", 'title = "Live"\n')
        monkeypatch.chdir(tmp_path)
        result = run("-C", "site", "-c", "production.toml", "config", "title")
        assert result.out == "Live\n"
        # a file of that name right here wins
        write(tmp_path / "production.toml", 'title = "Here"\n')
        result = run("-C", "site", "-c", "production.toml", "config", "title")
        assert result.out == "Here\n"

    def test_config_file_alone_names_the_site(self, run, tmp_path, monkeypatch):
        write(tmp_path / "elsewhere" / "custom.json", '{"title": "Custom"}')
        monkeypatch.chdir(tmp_path)
        assert run("-c", "elsewhere/custom.json", "config", "title").out == "Custom\n"

    def test_missing_config_file(self, run, site):
        result = run("-c", "nope.toml", "config")
        assert result.code == 1
        assert "config file not found" in result.err

    def test_find_site_root(self, site, tmp_path):
        assert cli_app.find_site_root(site / "content" / "posts") == site.resolve()
        assert cli_app.find_site_root(site) == site.resolve()
        assert cli_app.find_site_root(tmp_path) is None


class TestErrors:
    @pytest.fixture
    def failing(self, monkeypatch):
        """Make `inkstone version` raise whatever the test wants."""

        def install(exc):
            def run(app, args):
                raise exc

            monkeypatch.setattr(version, "run", run)

        return install

    def test_inkstone_errors_are_one_line(self, run, failing):
        failing(ContentError("bad date", path="content/a.md", line=3))
        result = run("version")
        assert result.code == 1
        assert result.out == ""
        assert result.err == "error: content/a.md:3: bad date\n"

    def test_debug_adds_the_traceback(self, run, failing):
        failing(BuildError("no template"))
        result = run("--debug", "version")
        assert result.code == 1
        assert result.err.startswith("Traceback (most recent call last):")
        assert result.err.endswith("error: no template\n")
        assert "BuildError" in result.err

    def test_debug_after_the_command_works_too(self, run, failing):
        failing(BuildError("no template"))
        assert "Traceback" in run("version", "--debug").err

    def test_unexpected_exceptions_are_reported_as_bugs(self, run, failing):
        failing(ZeroDivisionError("division by zero"))
        result = run("version")
        assert result.code == 1
        assert result.err == (
            "error: ZeroDivisionError: division by zero "
            "(this is a bug; --debug shows where)\n"
        )
        assert "Traceback" in run("--debug", "version").err

    def test_ctrl_c(self, run, failing):
        failing(KeyboardInterrupt())
        result = run("version")
        assert result.code == 130
        assert result.err == "\ninterrupted\n"

    def test_percent_signs_in_messages_survive(self, run, failing):
        failing(BuildError("100% broken %s"))
        assert run("version").err == "error: 100% broken %s\n"

    def test_real_config_errors(self, run, site):
        write(site / "inkstone.toml", 'title = "unclosed\n')
        result = run("config")
        assert result.code == 1
        assert result.err.startswith("error: ")
        assert "inkstone.toml" in result.err
        assert len(result.err.strip().splitlines()) == 1

    def test_wrong_type_in_config(self, run, site):
        write(site / "inkstone.toml", "title = 5\n")
        result = run("build")
        assert result.code == 1
        assert "title must be a string" in result.err


class TestOutputOptions:
    def levels(self, run, *argv):
        run(*argv, "version")
        return log.get_level()

    def test_log_levels(self, run):
        assert self.levels(run) == log.NORMAL
        assert self.levels(run, "-q") == log.QUIET
        assert self.levels(run, "-v") == log.VERBOSE
        assert self.levels(run, "--debug") == log.DEBUG
        assert self.levels(run, "-q", "--debug") == log.DEBUG
        # and back: one run must not leave its level behind for the next
        assert self.levels(run) == log.NORMAL

    def test_no_color(self, run, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        run("version")
        assert term.supports_color() is True
        run("--no-color", "version")
        assert term.supports_color() is False
        assert term.style("x", "red") == "x"

    def test_errors_are_not_coloured_into_a_pipe(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert "\x1b[" not in run("build").err

    def test_warning_counters_start_fresh(self, run):
        log.warning("left over from something else")
        run("version")
        assert log.warning_count() == 0

    def test_output_survives_a_legacy_code_page(self, tmp_path, monkeypatch):
        title = "日本語 blog"
        config = json.dumps({"title": title}, ensure_ascii=False)
        (tmp_path / "inkstone.json").write_text(config, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        # what `inkstone config title > file` gets on Windows
        raw = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
        assert main(["config", "title"]) == 0
        sys.stdout.flush()
        # escaped rather than a UnicodeEncodeError half way through
        assert raw.getvalue().strip() == title.encode("ascii", "backslashreplace")
