"""The build, such as it is: content/*.md -> public/, through templates.

Still one file and still rebuilds everything every time.
"""
from __future__ import annotations

import os
import shutil
import tomllib
from datetime import date, datetime
from pathlib import Path

from .errors import ContentError
from .markdown import Markdown
from .tmpl import Environment, FileSystemLoader, Markup
from .utils.text import slugify

BUILTIN_TEMPLATES = Path(__file__).parent / "templates"


def load_config(src: Path) -> dict:
    path = src / "inkstone.toml"
    if not path.exists():
        return {"title": src.resolve().name, "base_url": "/"}
    with open(path, "rb") as f:
        return tomllib.load(f)


def split_front_matter(text):
    # FIXME: this is `key: value` only. Lists, nesting, quotes with colons in
    # them all go wrong. Needs a real parser.
    meta = {}
    if not text.startswith("---"):
        return meta, text
    head, sep, body = text[3:].partition("\n---")
    if not sep:
        return meta, text
    for line in head.splitlines():
        if line.lstrip().startswith("#"):
            continue
        key, colon, value = line.partition(":")
        if colon:
            meta[key.strip()] = value.strip().strip("\"'")
    return meta, body.lstrip("\n")


def parse_date(value, path):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ContentError(f"cannot read date {value!r}", path=path)


def load_page(path: Path, content: Path) -> dict:
    meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    rel = os.path.relpath(path, content)
    slug = meta.get("slug") or slugify(path.stem)
    return {
        "path": path,
        "source": rel,
        "title": meta.get("title") or path.stem.replace("-", " ").title(),
        "slug": slug,
        "url": "/" + os.path.join(os.path.dirname(rel), slug) + "/",
        "date": parse_date(meta.get("date"), path),
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "draft": meta.get("draft", "").lower() in ("true", "yes"),
        "template": meta.get("template", "page.html"),
        "body": body,
        "content": "",
    }


def build(src: Path, out: Path, drafts: bool = False) -> int:
    content = src / "content"
    if not content.is_dir():
        raise ContentError("no content directory", path=src)
    config = load_config(src)

    env = Environment(
        loader=FileSystemLoader([src / "templates", BUILTIN_TEMPLATES]),
        autoescape=True,
    )
    env.globals["today"] = date.today()
    env.globals["base_url"] = config["base_url"].rstrip("/")

    md = Markdown()
    pages = [load_page(p, content) for p in sorted(content.rglob("*.md"))]
    if not drafts:
        pages = [p for p in pages if not p["draft"]]
    for page in pages:
        page["content"] = Markup(md.convert(page["body"]))

    posts = sorted(
        (p for p in pages if p["date"]), key=lambda p: p["date"], reverse=True
    )
    site = {"title": config.get("title", ""), "pages": pages, "posts": posts}

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for page in pages:
        html = env.get_template(page["template"]).render(page=page, site=site)
        _write(out / page["url"].strip("/") / "index.html", html)
    _write(out / "index.html", env.get_template("index.html").render(site=site))

    static = src / "static"
    if static.is_dir():
        shutil.copytree(static, out, dirs_exist_ok=True)
    return len(pages)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
