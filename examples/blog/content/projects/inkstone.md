---
title: inkstone
description: The static site generator that builds this site. Pure Python, no runtime dependencies.
weight: 10
tags: [inkstone, python]
---

A static site generator that fits in my head. Markdown in, HTML out, and
every piece in between (the Markdown parser, the template engine, the syntax
highlighter, the YAML reader, the dev server, the search index) written
from scratch on the standard library.

It is not trying to compete with anything. It builds this site and two
others, a clean build takes about two seconds, and when it breaks I know
whose fault it is.

## What it does

- Markdown with tables, footnotes, task lists, definition lists, admonitions
- Jinja-flavoured templates with inheritance and macros
- Syntax highlighting at build time for about twenty languages
- Sections, tags, pagination, page bundles
- RSS, Atom and JSON feeds, a sitemap
- Client-side search from a prebuilt index
- Incremental builds and a dev server with live reload

## Read more

The whole story is in the posts tagged
[inkstone](/tags/inkstone/), starting with
[why I am writing it at all](/2024/04/why-i-am-writing-my-own-generator/).

```bash
git clone https://github.com/magdygawadr99-crypto/inkstone
cd inkstone && pip install -e .
inkstone new site myblog
```
