# Changelog

Not every commit, just what you would notice as a user.

## 0.6.0 (2024-10-26)

- Search. The build writes `search-index.json` and the default theme has a
  search box and a results page. No server involved; see `docs/search.md`.
- New plugin: `related` (related posts by shared tags and text similarity).
- Documentation in `docs/`.
- Fixed: "next" on the last page of a paginated list linked to itself.

## 0.5.0 (2024-09-28)

- Live reload. `inkstone serve` now pushes changes to the browser over a
  websocket, swaps stylesheets without a full reload and shows build
  errors as an overlay on the page.
- The dev server is new as well: clean URLs, range requests, a proper 404.
- New plugins: `series`, `archives`, `external_links`, `image_dims`,
  `minify`, `drafts_banner`, `footnote_previews`, `git_dates`.
- Default theme: dark mode switch, copy buttons on code blocks, print
  stylesheet.

## 0.4.0 (2024-08-31)

- `inkstone new site`, `new post`, `new page`, `list`, `config` and
  `highlight-css`.
- Plugins, with three to start: `shortcodes`, `toc`, `reading_time`.
- Highlighter: C, C++, Go, Rust, Java, SQL, diff, Markdown, Dockerfile and
  Makefile lexers; three more styles.
- An example site in `examples/blog`.

## 0.3.0 (2024-07-27)

- The build was rewritten. It now runs in phases, knows about sections,
  taxonomies, menus and pagination, and only renders pages whose inputs
  changed (`--no-incremental` to switch that off). `--profile` shows where
  the time goes.
- A real configuration file with validation; a typo in `inkstone.toml` is
  now a message instead of a `KeyError`.
- Syntax highlighting for fenced code blocks.
- A default theme, and themes as a concept (`theme = "..."`).
- The command is now `inkstone`, not `python -m inkstone` (that still works).

## 0.2.0 (2024-06-28)

- Front matter is real YAML (a subset), TOML with `+++` or JSON.
- Data files in `data/`.
- RSS, Atom, `sitemap.xml`.
- `serve`: builds, serves `public/` and rebuilds when a file changes.
- CSS, JS and HTML minifiers and fingerprinted file names.
- Fixed: URLs with backslashes in them when building on Windows.
- Fixed: front matter in files with CRLF line endings.

## 0.1.0 (2024-05-12)

- First version that builds a site: Markdown in `content/`, templates in
  `templates/`, HTML in `public/`.
