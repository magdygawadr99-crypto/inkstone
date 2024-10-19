# inkstone

A static site generator that fits in my head.

I wanted to move my blog off a generator that pulled in ~40 packages and broke
every second upgrade, so I wrote my own. inkstone has **no runtime
dependencies**: the Markdown parser, the template engine, the syntax
highlighter, the YAML reader, the dev server (including the websocket bit for
live reload) and the search index are all in this repo. That is obviously more
code than `pip install` would have been, but it has been a good way to finally
learn how these things work, and nothing changes underneath me any more.

It is not trying to compete with Hugo or Pelican. It builds my sites, it is
reasonably fast, and the code is meant to be readable.

## What it does

- Markdown with the usual extras: tables, footnotes, task lists, definition
  lists, admonitions, heading ids, smart punctuation, a `[TOC]` marker
- Jinja-style templates with inheritance, includes and macros
- Syntax highlighting for ~20 languages at build time (no JS needed)
- Sections, tags/categories (any taxonomy really), pagination, page bundles
- RSS, Atom and JSON feeds, sitemap, robots.txt
- Client-side search from a prebuilt index
- Incremental builds: only pages whose inputs changed get rendered again
- `inkstone serve` with live reload and an error overlay in the browser
- CSS/JS/HTML minification and fingerprinted asset names
- Plugins (shortcodes, table of contents, series, archives, ... or your own)

## Install

Python 3.10 or newer (3.11+ if your config is TOML, which needs `tomllib`).

```
git clone https://github.com/magdygawadr99-crypto/inkstone
cd inkstone
pip install -e .
```

## Quick start

```
inkstone new site myblog
cd myblog
inkstone new post "Hello world"
inkstone serve
```

Then open http://127.0.0.1:8000/. Edit something under `content/` and the
browser reloads. When you are happy:

```
inkstone build --minify --fingerprint --base-url https://example.com/
```

and upload `public/` wherever you host things.

There is a complete example in [`examples/blog`](examples/blog):

```
inkstone -C examples/blog serve
```

## A post

```markdown
---
title: Hello world
date: 2024-05-03
tags: [meta, python]
---

The first paragraph doubles as the summary on list pages.

<!-- more -->

Everything else only shows on the page itself.
```

Front matter can be YAML (`---`), TOML (`+++`) or JSON. If the file is called
`2024-05-03-hello-world.md` the date and slug are taken from the name and you
can leave them out.

## Configuration

Everything lives in `inkstone.toml` at the site root. The smallest useful one:

```toml
title = "My blog"
base_url = "https://example.com/"

[author]
name = "Me"
```

`inkstone config --defaults` prints every option with its default value, and
[docs/configuration.md](docs/configuration.md) explains them.

## Commands

| | |
|---|---|
| `inkstone new site PATH` | scaffold a new site |
| `inkstone new post TITLE` | new post with front matter filled in |
| `inkstone build` | build into `public/` |
| `inkstone serve` | build, serve, watch, reload |
| `inkstone list` | list content (`--drafts`, `--tag`, `--format json`) |
| `inkstone config` | show the resolved configuration |
| `inkstone clean` | remove output and cache |

## Development

```
pip install -e ".[dev]"
python -m pytest
```

The layout is one package per concern:

```
inkstone/
  markdown/    block + inline parser, HTML and plain text renderers
  tmpl/        template lexer, parser, runtime, filters
  highlight/   regex lexers, HTML formatter, styles
  yamlite/     the subset of YAML that front matter needs
  content/     pages, sections, taxonomies, pagination
  build/       the builder, incremental cache, link checker
  assets/      minifiers, fingerprinting, image sizes
  feeds/       rss / atom / json feed / sitemap
  search/      index builder + the browser client
  server/      dev server, websocket, file watcher
  plugins/     plugin manager and the built-in plugins
  cli/         the `inkstone` command
  themes/      the default theme
```

Each of the lower-level packages is usable on its own, e.g.

```python
from inkstone.markdown import render
print(render("# hi\n\nsome *text*"))
```

## License

MIT, see [LICENSE](LICENSE).
