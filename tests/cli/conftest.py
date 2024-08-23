from __future__ import annotations

import datetime as dt
import os
from typing import NamedTuple

import pytest

from inkstone import scaffold, tomlw
from inkstone.cli import main
from inkstone.scaffold import site as scaffold_site
from inkstone.utils import log, term

TODAY = dt.date(2024, 5, 3)
needs_toml = pytest.mark.skipif(
    tomlw.tomllib is None, reason="reading TOML needs Python 3.11 or newer"
)


class Result(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """Keep one test's logging, colours and environment out of the next."""
    for name in list(os.environ):
        if name.startswith("INKSTONE_"):
            monkeypatch.delenv(name)
    # `new site` asks git for a name; the answer depends on the machine
    monkeypatch.setattr(scaffold_site, "git_user_name", lambda: "Ada Example")
    log.reset()
    yield
    log.reset()
    log.set_level(log.NORMAL)
    log.set_stream(None)
    term.set_color(None)


@pytest.fixture
def run(capsys):
    """Call the command line in-process: ``run("build", "--drafts")``."""

    def run(*argv) -> Result:
        capsys.readouterr()
        code = main([str(arg) for arg in argv])
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return run


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A freshly scaffolded site; the working directory is its root."""
    if tomlw.tomllib is None:
        # the tests edit inkstone.toml and read it back
        pytest.skip("needs a TOML config, which Python 3.10 cannot read")
    root = tmp_path / "site"
    scaffold.create_site(
        root,
        title="Test Site",
        author="Ada Example",
        today=TODAY,
        config_format="toml",
    )
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def builder():
    """Skips the test while there is no builder to run it against."""
    return pytest.importorskip("inkstone.build")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def configure(site, *, prepend="", append="", replace=None):
    """Edit the inkstone.toml of a scaffolded site in place."""
    path = site / "inkstone.toml"
    text = path.read_text(encoding="utf-8")
    for old, new in (replace or {}).items():
        assert old in text, old
        text = text.replace(old, new)
    path.write_text(prepend + text + append, encoding="utf-8")
