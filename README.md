# inkstone

A small static site generator with no dependencies. Markdown in, HTML out.

Still early. What works so far:

- Markdown parser (CommonMark-ish, plus tables, footnotes, task lists)
- Jinja-like templates with inheritance, includes, macros and filters
- `python -m inkstone build` turns `content/` into `public/`

## Usage

    python -m inkstone build [site-dir]

Content goes in `content/*.md` with a front matter block at the top:

    ---
    title: Hello
    date: 2024-05-03
    tags: meta, python
    ---

Front matter is `key: value` lines only for now. Templates are looked up in
`templates/` in your site first and then in `inkstone/templates`, so copy
the ones from there and change them.

Site-wide settings go in `inkstone.toml`:

    title = "My site"
    base_url = "https://example.com/"

## Tests

    python -m pytest
