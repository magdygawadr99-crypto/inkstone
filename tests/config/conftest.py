from __future__ import annotations

import os
import textwrap

import pytest

from inkstone.utils import log


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    # a stray INKSTONE_* variable on the machine running the tests would
    # leak into every config loaded here
    for name in list(os.environ):
        if name.startswith("INKSTONE_"):
            monkeypatch.delenv(name)
    yield
    log.reset()


@pytest.fixture
def site(tmp_path):
    """A site directory, and a function to write its config file."""

    class SiteDir:
        root = tmp_path

        def write(self, text: str, name: str = "inkstone.toml"):
            path = tmp_path / name
            path.write_text(textwrap.dedent(text), encoding="utf-8")
            return path

        def theme(self, name: str, text: str):
            directory = tmp_path / "themes" / name
            (directory / "templates").mkdir(parents=True, exist_ok=True)
            path = directory / "theme.toml"
            path.write_text(textwrap.dedent(text), encoding="utf-8")
            return directory

    return SiteDir()
