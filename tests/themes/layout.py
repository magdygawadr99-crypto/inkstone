"""Where the themes, the example site and the docs live, plus a few helpers
for looking at template source without rendering it."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEMES = ROOT / "inkstone" / "themes"
EXAMPLE = ROOT / "examples" / "blog"
DOCS = ROOT / "docs"

THEME_NAMES = ["default", "paper"]

# Files the builder writes into the output; templates may point at them with
# asset() even though no theme ships them.
GENERATED_ASSETS = {"css/highlight.css", "js/inkstone-search.js"}

COMMENT_RE = re.compile(r"\{#.*?#\}", re.S)
TAG_RE = re.compile(r"\{%-?\s*(\w+)\s*(.*?)\s*-?%\}", re.S)
REFERENCE_RE = re.compile(
    r"\{%-?\s*(extends|include|import|from)\s+([\"'])(.+?)\2", re.S
)
ASSET_RE = re.compile(r"\basset\(\s*([\"'])(.+?)\1\s*\)")
BLOCK_RE = re.compile(r"\{%-?\s*block\s+(\w+)")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_exact(path: Path) -> str:
    """The text as it is on disk, except that CRLF counts as a line ending.

    The files are kept with LF, but a Windows checkout with core.autocrlf
    hands them out with CRLF, and that should not fail the tidiness checks.
    """
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def assert_tidy(path: Path, label: str) -> str:
    """No tabs, stray carriage returns, trailing blanks or missing last newline."""
    text = read_exact(path)
    assert "\r" not in text, f"{label}: stray carriage return"
    assert "\t" not in text, f"{label}: tab character"
    assert text.endswith("\n"), f"{label}: no newline at the end"
    assert not text.endswith("\n\n"), f"{label}: blank lines at the end"
    for number, line in enumerate(text.split("\n"), 1):
        assert line == line.rstrip(), f"{label}:{number}: trailing whitespace"
    return text


def parent_of(theme: str) -> str | None:
    """The `inherit` value of a theme, read without a TOML parser."""
    match = re.search(
        r'^inherit\s*=\s*"([^"]+)"', read(THEMES / theme / "theme.toml"), re.M
    )
    return match.group(1) if match else None


def chain(theme: str) -> list[str]:
    """The theme followed by its ancestors, nearest first."""
    names = [theme]
    while (parent := parent_of(names[-1])) is not None:
        assert parent not in names, f"themes inherit in a circle: {names + [parent]}"
        names.append(parent)
    return names


def template_dirs(theme: str) -> list[Path]:
    return [THEMES / name / "templates" for name in chain(theme)]


def static_dirs(theme: str) -> list[Path]:
    return [THEMES / name / "static" for name in chain(theme)]


def own_templates(theme: str) -> list[str]:
    """Template names (forward slashes) that live in the theme itself."""
    base = THEMES / theme / "templates"
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*.html"))


def all_templates(theme: str) -> list[str]:
    """Every template name the theme can render, inherited ones included."""
    names: set[str] = set()
    for name in chain(theme):
        names.update(own_templates(name))
    return sorted(names)


def find_template(theme: str, name: str) -> Path | None:
    for directory in template_dirs(theme):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def find_static(theme: str, name: str) -> Path | None:
    for directory in static_dirs(theme):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def source_of(theme: str, name: str) -> str:
    """Template source as the theme resolves it, comments removed."""
    path = find_template(theme, name)
    assert path is not None, f"{theme}: no template {name!r}"
    return COMMENT_RE.sub("", read(path))


def theme_template_params() -> list[tuple[str, str]]:
    """(theme, template) pairs for parametrize: each file once, in its owner."""
    return [(theme, name) for theme in THEME_NAMES for name in own_templates(theme)]


def strip_css_noise(css: str) -> str:
    """CSS without comments and string contents, so braces can be counted."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", '""', css)
