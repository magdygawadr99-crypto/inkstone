# Changelog

Not every commit, just what you would notice as a user.

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
