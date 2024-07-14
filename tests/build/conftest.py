from __future__ import annotations

import json
import textwrap

import pytest

from inkstone import yamlite
from inkstone.build import Builder
from inkstone.config import load_config
from inkstone.utils import log
from inkstone.utils.collections import deep_merge

CONFIG = """\
title: Test Site
base_url: https://example.com/
description: A site for tests.
theme: tiny
plugins: []
author:
  name: Magdy
pagination:
  per_page: 2
"""

THEME = """\
name = "tiny"
description = "Just enough templates to build a site."
version = "0.1.0"

[params]
footer = "tiny footer"
wide = false
"""

BASE_HTML = """\
<!doctype html>
<html lang="{{ site.language }}">
<head>
<title>{% block title %}{{ page.title }}{% endblock %} | {{ site.title }}</title>
<link rel="stylesheet" href="{{ asset('css/theme.css') }}">
</head>
<body class="kind-{{ page.kind }}">
{% block content %}{% endblock %}
{% include "partials/footer.html" %}
</body>
</html>
"""

FOOTER_HTML = """\
<footer>{{ config.params.footer }}</footer>
"""

PAGE_HTML = """\
{% extends "base.html" %}
{% block content %}
<article>
<h1>{{ page.title }}</h1>
{{ page.content }}
{% if page.prev %}
<a class="prev" href="{{ url_for(page.prev.url) }}">{{ page.prev.title }}</a>
{% endif %}
{% if page.next %}
<a class="next" href="{{ url_for(page.next.url) }}">{{ page.next.title }}</a>
{% endif %}
</article>
{% endblock %}
"""

SECTION_HTML = """\
{% extends "base.html" %}
{% block content %}
<h1>{{ page.title }}</h1>
{{ page.content }}
<ul class="list">
{% for post in pages %}
<li><a href="{{ url_for(post.url) }}">{{ post.title }}</a> {{ post.summary }}</li>
{% endfor %}
</ul>
<p class="pager">page {{ paginator.page }} of {{ paginator.pages }}</p>
{% if paginator.has_next %}
<a rel="next" href="{{ url_for(paginator.next_url) }}">older</a>
{% endif %}
{% endblock %}
"""

INDEX_HTML = """\
{% extends "base.html" %}
{% block title %}Home{% endblock %}
{% block content %}
<h1>{{ site.title }}</h1>
{{ page.content }}
<ul class="list">
{% for post in pages %}
<li><a href="{{ url_for(post.url) }}">{{ post.title }}</a></li>
{% endfor %}
</ul>
{% endblock %}
"""

TAXONOMY_HTML = """\
{% extends "base.html" %}
{% block content %}
<h1>All {{ taxonomy.name }}</h1>
<ul class="terms">
{% for term in taxonomy %}
<li><a href="{{ url_for(term.url) }}">{{ term.name }}</a> ({{ term.count }})</li>
{% endfor %}
</ul>
{% endblock %}
"""

TERM_HTML = """\
{% extends "base.html" %}
{% block content %}
<h1>{{ taxonomy.singular }}: {{ term.name }}</h1>
<ul class="list">
{% for post in pages %}
<li><a href="{{ url_for(post.url) }}">{{ post.title }}</a></li>
{% endfor %}
</ul>
{% endblock %}
"""

NOT_FOUND_HTML = """\
{% extends "base.html" %}
{% block content %}
<h1>Not found</h1>
{{ page.content }}
{% endblock %}
"""

TEMPLATES = {
    "base.html": BASE_HTML,
    "partials/footer.html": FOOTER_HTML,
    "page.html": PAGE_HTML,
    "section.html": SECTION_HTML,
    "index.html": INDEX_HTML,
    "taxonomy.html": TAXONOMY_HTML,
    "term.html": TERM_HTML,
    "404.html": NOT_FOUND_HTML,
}


class BuildSite:
    """A site on disk with a tiny local theme, and shortcuts for building it."""

    def __init__(self, root):
        self.root = root
        self.settings: dict = yamlite.loads(CONFIG)
        self.overrides: dict = {}
        self.config_path = root / "inkstone.json"
        self._save_config()
        self.write("themes/tiny/theme.toml", THEME)
        self.write("themes/tiny/static/css/theme.css", "body { margin: 0; }\n")
        for name, source in TEMPLATES.items():
            self.write(f"themes/tiny/templates/{name}", source)
        (root / "content").mkdir()

    def write(self, relpath: str, text: str = ""):
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def _save_config(self) -> None:
        # JSON, so the fixture also works on Python 3.10, which reads no TOML
        text = json.dumps(self.settings, indent=2)
        self.config_path.write_text(text, encoding="utf-8")

    def configure(self, text: str) -> None:
        """Merge settings, written as YAML, into the config file."""
        self.settings = deep_merge(self.settings, yamlite.loads(textwrap.dedent(text)))
        self._save_config()

    def page(self, relpath: str, body: str = "Some text.\n", **meta):
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

    def config(self):
        return load_config(self.root, overrides=self.overrides)

    def builder(self, **options) -> Builder:
        """A fresh Builder, as a new run of the command line would make."""
        return Builder(self.config(), **options)

    def build(self, **options):
        return self.builder(**options).build()

    @property
    def output(self):
        return self.root / "public"

    def read(self, relpath: str) -> str:
        return (self.output / relpath).read_text(encoding="utf-8")

    def exists(self, relpath: str) -> bool:
        return (self.output / relpath).is_file()

    def outputs(self) -> list[str]:
        return sorted(
            path.relative_to(self.output).as_posix()
            for path in self.output.rglob("*")
            if path.is_file()
        )


@pytest.fixture
def site(tmp_path):
    return BuildSite(tmp_path)


@pytest.fixture
def blog(site):
    """A small but complete blog: home, a page, a section with a few posts."""
    site.page("_index.md", "Welcome to the *test* site.\n", title="Home")
    site.page("about.md", "About **me**.\n", title="About")
    site.page("posts/_index.md", "Everything I wrote.\n", title="Posts")
    site.page(
        "posts/2024-01-10-first.md",
        "The first post.\n\n<!-- more -->\n\nIts second paragraph.\n",
        title="First",
        tags=["python", "notes"],
    )
    site.page(
        "posts/2024-02-10-second.md",
        "The second post.\n\n## A heading\n\nMore text.\n",
        title="Second",
        tags=["python"],
    )
    site.page(
        "posts/2024-03-10-third.md",
        "The third post links to [the first](2024-01-10-first.md).\n",
        title="Third",
        categories=["News"],
    )
    return site


@pytest.fixture(autouse=True)
def quiet_log():
    yield
    log.reset()
