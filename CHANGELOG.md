# Changelog

Not every commit, just what you would notice as a user.

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
