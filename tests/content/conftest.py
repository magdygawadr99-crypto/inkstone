from __future__ import annotations

import datetime as dt
import textwrap

import pytest

from inkstone.config import load_config
from inkstone.content import load_site
from inkstone.utils import log

NOW = dt.datetime(2024, 6, 15, 12, 0, tzinfo=dt.timezone.utc)


class SiteFiles:
    """Writes a throwaway site into a directory and loads it."""

    def __init__(self, root):
        self.root = root
        self.settings = ""
        (root / "content").mkdir()

    def configure(self, text: str) -> None:
        self.settings = textwrap.dedent(text)

    def write(self, relpath: str, text: str = "", *, base: str = "content"):
        path = self.root / base / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
        return path

    def page(self, relpath: str, body: str = "Text.\n", **meta):
        """A Markdown file with YAML front matter made from keyword arguments."""
        lines = ["---"]
        for key, value in meta.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            elif isinstance(value, (list, tuple)):
                value = "[" + ", ".join(str(item) for item in value) + "]"
            lines.append(f"{key}: {value}")
        lines.append("---")
        text = "\n".join(lines) + "\n" + textwrap.dedent(body)
        path = self.root / "content" / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def config(self, **overrides):
        # YAML so the fixtures also work on Python 3.10, which reads no TOML
        (self.root / "inkstone.yaml").write_text(
            "theme: none-needed\n" + self.settings, encoding="utf-8"
        )
        return load_config(self.root, overrides=overrides)

    def load(self, *, now=NOW, drafts=None, future=None, strict=True, **overrides):
        config = self.config(**overrides)
        return load_site(config, now=now, drafts=drafts, future=future, strict=strict)


@pytest.fixture
def files(tmp_path):
    return SiteFiles(tmp_path)


@pytest.fixture(autouse=True)
def quiet_log():
    yield
    log.reset()
