# Configuration

A site is configured by one file at its root: `inkstone.toml`. Every key is
optional. A config with only a `title` and a `base_url` is a complete one.

```toml
title = "My blog"
base_url = "https://example.com/"

[author]
name = "Me"
```

This page lists every key with its default. To see the same list from the
tool itself:

```
inkstone config --defaults        # all defaults, as TOML
inkstone config                   # this site, after merging everything
inkstone config --json            # the same, for scripts
inkstone config markdown.smart    # a single value
```

## Formats and precedence

The file can also be `inkstone.yaml`, `inkstone.yml` or `inkstone.json`,
with the same keys. TOML needs Python 3.11; on 3.10 use one of the others.
Keep one config file per site: if several exist, one is used and the build
warns about the rest. `-c FILE` picks a file explicitly, which is how you
use a second config for staging.

Values are resolved in this order, later ones winning:

1. the built-in defaults on this page
2. the theme's `[params]` defaults (only for keys under `params`)
3. the config file
4. environment variables starting with `INKSTONE_`
5. command line flags (`--base-url`, `--drafts`, `--minify`, ...)

For environment variables, the name after the prefix is the key in upper
case, and a double underscore separates levels:

```
INKSTONE_BASE_URL=https://staging.example.com/ inkstone build
INKSTONE_BUILD__DRAFTS=1 inkstone build
INKSTONE_BUILD__MINIFY=true inkstone build
```

Two kinds of mistake are caught when the config is loaded:

- An unknown top-level key is a warning with a suggestion, along the lines
  of *unknown key `base_ur`, did you mean `base_url`?* The build goes on.
- A value of the wrong type (`jobs = "four"`) is an error that names the
  key. The build stops.

## Site

| Key | Default | Meaning |
|-----|---------|---------|
| `title` | `"My Site"` | The site's name. Used in `<title>`, the header and feeds. |
| `base_url` | `"http://localhost:8000/"` | Where the site will be served, with scheme and trailing slash. May include a path (`https://example.com/blog/`); see [Deploying](deploying.md#sites-in-a-sub-directory). |
| `description` | `""` | One sentence about the site. Fallback for the meta description and the feed subtitle. |
| `language` | `"en"` | A BCP 47 language tag, used for `<html lang>` and feeds. |
| `timezone` | `"UTC"` | The zone that dates without one are taken to be in. A fixed UTC offset (`"UTC"`, `"+02:00"`, `"-0530"`) always works. A named zone such as `Europe/Berlin` works where Python can find the time zone database: out of the box on Linux and macOS, on Windows only after `pip install tzdata`. |
| `theme` | `"default"` | A built-in theme (`default`, `paper`) or a directory under `themes/`. |
| `ignore` | `["*.swp", "*~", ".DS_Store"]` | Glob patterns for files to skip in `content/` and `static/`. |
| `plugins` | `["shortcodes", "toc", "reading_time"]` | Enabled plugins, in the order they run. See [Plugins](plugins.md). |

Setting `plugins` replaces the list, it does not add to it. If you want
the default three plus one more, list all four.

### Directories

All relative to the site root. I have never changed any of these, but they
are there.

| Key | Default | Holds |
|-----|---------|-------|
| `content_dir` | `"content"` | Markdown sources |
| `output_dir` | `"public"` | the built site |
| `static_dir` | `"static"` | files copied as they are |
| `data_dir` | `"data"` | data files for `site.data` |
| `templates_dir` | `"templates"` | your template overrides |
| `themes_dir` | `"themes"` | local themes |
| `plugins_dir` | `"plugins"` | local plugins |
| `cache_dir` | `".inkstone-cache"` | incremental build state |

`inkstone clean` deletes `output_dir` and `cache_dir`, and so does
`inkstone build --clean` before it builds. Do not point `output_dir` at a
directory that has anything else in it.

## `[author]`

| Key | Default | Meaning |
|-----|---------|---------|
| `name` | `""` | Your name: meta author tag, footer, feed author. |
| `email` | `""` | Used in feeds. Leave empty to keep it out of them. |
| `url` | `""` | A page about you. The footer links the name to it. |

## `[build]`

| Key | Default | Meaning |
|-----|---------|---------|
| `drafts` | `false` | Include pages with `draft: true`. Flag: `--drafts`. |
| `future` | `false` | Include pages dated after the build time. Flag: `--future`. |
| `incremental` | `true` | Only re-render pages whose inputs changed. Flag to turn off: `--no-incremental`. |
| `minify` | `false` | Minify HTML, CSS and JS. Flag: `--minify`. |
| `fingerprint` | `false` | Put a content hash in static file names and rewrite references to them. Flag: `--fingerprint`. |
| `pretty_urls` | `true` | `/about/` (written as `about/index.html`) rather than `/about.html`. |
| `jobs` | `0` | Worker count for rendering. `0` picks one based on the machine. |

The minifiers are deliberately conservative. The JS one strips comments and
whitespace and never renames anything.

With `fingerprint` on, `css/main.css` is written as `css/main.3f9a1c2e.css`
and every `asset("css/main.css")` in a template resolves to that name, so
you can serve static files with a far-future cache lifetime.

## `[markdown]`

| Key | Default | Meaning |
|-----|---------|---------|
| `extensions` | `[]` | Markdown extensions to enable. Empty means the default set. See [Markdown](markdown.md#extensions). |
| `smart` | `true` | Curly quotes, en and em dashes, ellipses. |
| `heading_ids` | `true` | Give headings an `id` derived from their text, so they can be linked to and appear in the table of contents. |
| `highlight` | `true` | Highlight fenced code blocks at build time and write `css/highlight.css`. |
| `highlight_style` | `"dusk"` | The colour scheme. Has to be a style the highlighter knows; an unknown name is a config error that lists the valid ones. |
| `hard_wraps` | `false` | Treat every line break in a paragraph as `<br>`. |

Like `plugins`, a non-empty `extensions` list replaces the default set
rather than adding to it.

To use a different highlighting style in dark mode, set
`highlight_style_dark` under `[params]`; `css/highlight.css` then carries
both, switched by `prefers-color-scheme` and by the theme's `data-theme`
attribute.

## `[permalinks]`

Maps a section name to a URL pattern for its pages.

```toml
[permalinks]
posts = "/:year/:month/:slug/"
```

That entry is the only default. Tokens: `:year`, `:month`, `:day`, `:slug`,
`:title`, `:section`, `:filename`; an unknown token is an error. Sections
without a pattern use their path. More in [Content](content.md#permalinks).

Most tables in the config are merged with their defaults, so you only
write what you change. Three are not: `[permalinks]`, `[taxonomies]` and
`search.fields` *replace* their default as soon as you define them. A
`[permalinks]` table that only mentions `notes` means posts go back to
plain paths, so repeat the `posts` line if you want to keep it.

## `[taxonomies]`

```toml
[taxonomies]
tags = "tag"
categories = "category"
```

Plural name (front matter key and URL prefix) to singular name (for
headings). These two are the defaults. The table replaces the default: a
`[taxonomies]` with only `tags` in it means there are no categories, and an
empty one means no taxonomies at all. More in
[Content](content.md#taxonomies).

## `[pagination]`

| Key | Default | Meaning |
|-----|---------|---------|
| `per_page` | `10` | Items on each page of a list. A section can override it with `paginate` in its `_index.md`. |
| `path` | `"page"` | The URL segment before the page number: `/posts/page/2/`. |

## `[feeds]`

| Key | Default | Meaning |
|-----|---------|---------|
| `rss` | `true` | Write `rss.xml`. |
| `atom` | `true` | Write `atom.xml`. |
| `json` | `false` | Write `feed.json` ([JSON Feed](https://www.jsonfeed.org/)). |
| `limit` | `20` | Newest entries to include. |
| `sections` | `["posts"]` | Sections whose pages go into the feeds. Empty means every page that has a date. Each listed section also gets a feed of its own at `<section>/rss.xml`. |
| `full_content` | `true` | Put the whole post in each entry. `false` sends the summary only. |

The same `sections` list decides what the home page shows.

## `[search]`

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | Build `search-index.json` and copy the search client to `js/inkstone-search.js`. |
| `fields` | `{ title = 3.0, tags = 2.0, body = 1.0 }` | Which fields are indexed and how much a match in each one counts. |

See [Search](search.md).

## `[sitemap]`

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | Write `sitemap.xml`. |
| `changefreq` | `"weekly"` | The `<changefreq>` hint on every entry. |

## `[robots]`

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | Write `robots.txt`, pointing at the sitemap. |
| `disallow` | `[]` | Paths to add as `Disallow:` lines, e.g. `["/search/", "/drafts/"]`. |

## `[server]`

Only used by `inkstone serve`.

| Key | Default | Meaning |
|-----|---------|---------|
| `host` | `"127.0.0.1"` | Address to listen on. `"0.0.0.0"` makes the site reachable from other devices on your network. |
| `port` | `8000` | Port. |
| `livereload` | `true` | Reload the browser after each rebuild. |
| `open` | `false` | Open the site in a browser when the server starts. |

## `[menus]`

Menus are lists of entries. The default theme uses `main` for the header
and `footer`, if present, for the footer; a theme can read any name.

```toml
[[menus.main]]
name = "Posts"
url = "/posts/"
weight = 10

[[menus.main]]
name = "About"
url = "/about/"
weight = 20

[[menus.main]]
name = "Code"
url = "https://github.com/me"
weight = 30
```

| Key | Meaning |
|-----|---------|
| `name` | The link text. Required. |
| `url` | A path on this site (`/posts/`) or a full URL. Required. |
| `weight` | Order within the menu, lowest first. |

An entry can also have `children`, a list of entries of the same shape.
The default theme shows them as a second level under their parent.

A page can put itself into a menu from its own front matter instead:
`menu: main` adds it under its title, with its `weight` as the position.

Without a `main` menu the default theme lists the top-level sections
instead, so a new site has navigation before you configure any.

## `[params]`

Free-form settings for themes. inkstone itself reads exactly one of them
(`highlight_style_dark`, above); the rest mean whatever the theme says they
mean. Templates see them as `config.params.<name>`.

```toml
[params]
accent = "#8c3b2a"
date_format = "long"
custom_css = ["css/custom.css"]

[params.social]
github = "https://github.com/me"
```

A theme ships defaults for its params in its `theme.toml`. Your values are
merged over them key by key, so you only write the ones you change. The
params of the default theme are listed in
[Templates](templates.md#theme-settings).

You can add params of your own for use in your own templates. Nothing
checks them.

## `[plugin]`

Settings for individual plugins, one table per plugin:

```toml
plugins = ["shortcodes", "toc", "reading_time", "related"]

[plugin.related]
limit = 5
```

A plugin only receives its own table. What each built-in plugin accepts is
in [Plugins](plugins.md).

## A complete example

The config of the example site, lightly trimmed:

```toml
title = "Wet Ink"
base_url = "https://wetink.example/"
description = "Notes from building small software."
language = "en"
timezone = "+01:00"
theme = "default"
plugins = ["shortcodes", "toc", "reading_time", "series", "related", "archives"]

[author]
name = "Magdy Gawad"
email = "magdy@wetink.example"

[permalinks]
posts = "/:year/:month/:slug/"
projects = "/projects/:slug/"

[pagination]
per_page = 6

[feeds]
json = true
limit = 15

[robots]
disallow = ["/search/"]

[[menus.main]]
name = "Posts"
url = "/posts/"
weight = 10

[[menus.main]]
name = "About"
url = "/about/"
weight = 40

[params]
accent = "#8c3b2a"
accent_dark = "#f0957a"
custom_css = ["css/custom.css"]

[plugin.related]
limit = 3
```

The full file is at
[`examples/blog/inkstone.toml`](../examples/blog/inkstone.toml).
