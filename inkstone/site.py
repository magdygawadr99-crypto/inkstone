"""The build, such as it is: content/*.md -> public/, through templates.

Still one file and still rebuilds everything every time.
"""
from __future__ import annotations

import os
import shutil
import tomllib
from datetime import date
from pathlib import Path

from . import frontmatter
from .errors import ContentError
from .feeds import FeedEntry, FeedMeta, Sitemap, render_atom, render_rss
from .markdown import Markdown
from .tmpl import Environment, FileSystemLoader, Markup
from .utils.dates import date_from_filename, parse_date
from .utils.text import slugify

BUILTIN_TEMPLATES = Path(__file__).parent / "templates"
FEED_LIMIT = 20


def load_config(src: Path) -> dict:
    path = src / "inkstone.toml"
    if not path.exists():
        return {"title": src.resolve().name, "base_url": "/"}
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_page(path: Path, content: Path) -> dict:
    meta, body = frontmatter.parse(path.read_text(encoding="utf-8"), path=path)
    rel = os.path.relpath(path, content)
    file_date, stem = date_from_filename(path.name)
    when = meta.get("date") or file_date
    try:
        when = parse_date(when) if when else None
    except ValueError as exc:
        raise ContentError(str(exc), path=path) from None
    slug = meta.get("slug") or slugify(stem)
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return {
        "path": path,
        "source": rel,
        "section": os.path.dirname(rel),
        "title": meta.get("title") or stem.replace("-", " ").title(),
        "slug": slug,
        "url": "/" + os.path.join(os.path.dirname(rel), slug) + "/",
        "date": when,
        "tags": tags,
        "draft": bool(meta.get("draft")),
        "template": meta.get("template", "page.html"),
        "summary": meta.get("summary", ""),
        "body": body,
        "content": "",
    }


def build(src: Path, out: Path, drafts: bool = False) -> int:
    content = src / "content"
    if not content.is_dir():
        raise ContentError("no content directory", path=src)
    config = load_config(src)
    base_url = config["base_url"].rstrip("/")

    env = Environment(
        loader=FileSystemLoader([src / "templates", BUILTIN_TEMPLATES]),
        autoescape=True,
    )
    env.globals["today"] = date.today()
    env.globals["base_url"] = base_url

    md = Markdown()
    pages = [load_page(p, content) for p in sorted(content.rglob("*.md"))]
    if not drafts:
        pages = [p for p in pages if not p["draft"]]
    for page in pages:
        page["content"] = Markup(md.convert(page["body"]))

    posts = sorted(
        (p for p in pages if p["date"]), key=lambda p: p["date"], reverse=True
    )
    tags: dict[str, list] = {}
    for post in posts:
        for tag in post["tags"]:
            tags.setdefault(tag, []).append(post)
    site = {
        "title": config.get("title", ""),
        "pages": pages,
        "posts": posts,
        "tags": tags,
    }

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for page in pages:
        html = env.get_template(page["template"]).render(page=page, site=site)
        _write(out / page["url"].strip("/") / "index.html", html)
    _write(out / "index.html", env.get_template("index.html").render(site=site))
    for tag, tagged in tags.items():
        html = env.get_template("tag.html").render(tag=tag, posts=tagged, site=site)
        _write(out / "tags" / slugify(tag) / "index.html", html)

    write_feeds(out, config, base_url, posts)
    write_sitemap(out, base_url, pages)

    static = src / "static"
    if static.is_dir():
        shutil.copytree(static, out, dirs_exist_ok=True)
    return len(pages)


def write_feeds(out: Path, config: dict, base_url: str, posts: list) -> None:
    if not base_url.startswith("http"):
        return  # feeds need absolute urls
    meta = FeedMeta(
        title=config.get("title", ""),
        link=base_url + "/",
        feed_url=base_url + "/rss.xml",
        description=config.get("description", ""),
    )
    entries = [
        FeedEntry(
            id=base_url + post["url"],
            title=post["title"],
            url=base_url + post["url"],
            published=post["date"],
            summary=post["summary"] or None,
            content_html=str(post["content"]),
            tags=post["tags"],
        )
        for post in posts[:FEED_LIMIT]
    ]
    _write(out / "rss.xml", render_rss(meta, entries))
    meta.feed_url = base_url + "/atom.xml"
    _write(out / "atom.xml", render_atom(meta, entries))


def write_sitemap(out: Path, base_url: str, pages: list) -> None:
    if not base_url.startswith("http"):
        return
    sitemap = Sitemap()
    sitemap.add(base_url + "/")
    for page in pages:
        sitemap.add(base_url + page["url"], lastmod=page["date"])
    _write(out / "sitemap.xml", sitemap.render())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
