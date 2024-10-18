# Content

Everything under `content/` is a page or belongs to one. This page describes
how files turn into URLs, what you can put in front matter, and the handful
of conventions (sections, bundles, drafts, summaries) that make a pile of
Markdown files behave like a site.

## From file to URL

```
content/
  _index.md                         /
  about.md                          /about/
  posts/
    _index.md                       /posts/
    2024-05-03-hello-world.md       /2024/05/hello-world/   (see Permalinks)
    trip/
      index.md                      /2024/06/trip/
      photo.jpg                     /2024/06/trip/photo.jpg
  docs/
    _index.md                       /docs/
    install.md                      /docs/install/
    guide/
      _index.md                     /docs/guide/
      first-steps.md                /docs/guide/first-steps/
```

The rules behind that:

- A Markdown file is a page. Its URL is its path without the extension,
  with a trailing slash: `about.md` becomes `/about/`, written to
  `about/index.html`.
- A directory is a **section**. `_index.md` inside it holds the section's
  own title and settings; the file is optional.
- A directory with an `index.md` (no underscore) is a **page bundle**: one
  page whose images and other files live next to it.
- The top-level `_index.md` is the home page.
- Files matching the `ignore` patterns in the config (editor swap files,
  `.DS_Store`) are skipped.
- Anything else that is not Markdown (an image next to a post, a PDF) is
  copied to the same place in the output. `static/` is still the better
  home for files that do not belong to one page.

If you prefer `/about.html` to `/about/`, set `build.pretty_urls = false`.

## Front matter

A page starts with a block of metadata. Three formats are accepted, and
you can mix them within a site:

```markdown
---
title: Hello world
date: 2024-05-03
tags: [meta, python]
---
```

```markdown
+++
title = "Hello world"
date = 2024-05-03
tags = ["meta", "python"]
+++
```

```markdown
{
  "title": "Hello world",
  "date": "2024-05-03",
  "tags": ["meta", "python"]
}
```

`---` is YAML, `+++` is TOML, and a file that starts with `{` is JSON up to
the matching brace. YAML is read by inkstone's own small parser; see the
[FAQ](faq.md#which-yaml-is-supported) for what it leaves out. TOML front
matter needs Python 3.11.

Front matter is optional in principle, but a page without a `title` gets one
made up from its file name, and that is rarely the title you wanted.

### Keys inkstone understands

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `title` | string | from the file name | The page title. |
| `date` | date or datetime | from the file name, else none | Publication date. Feeds only carry pages that have one. |
| `updated` | date or datetime | none | Last significant change. Shown by the default theme and used as `<updated>` in the Atom feed. |
| `slug` | string | from the file name | The last part of the URL. |
| `description` | string | `""` | One or two sentences for `<meta name="description">`, feeds and link previews. |
| `summary` | string (Markdown) | see [Summaries](#summaries) | Overrides the automatic summary. |
| `draft` | boolean | `false` | Drafts are left out unless you build with `--drafts`. |
| `weight` | integer | `0` | Sort key for sections with `sort_by: weight`. Lower comes first. |
| `tags`, `categories` | list of strings | `[]` | Terms in the taxonomies of the same name. Any taxonomy you define in the config works the same way. |
| `template` | string | by kind and section | Render this page with a specific template, e.g. `search.html`. |
| `aliases` | list of URLs | `[]` | Old addresses of this page. The `redirects` plugin writes a redirect at each. |

Everything else you put in front matter is kept and handed to templates as
`page.params`. That is how theme and plugin options per page work. The
default theme looks at these:

| Key | Meaning |
|-----|---------|
| `toc` | `false` hides the table of contents on this page, `true` forces it on when the theme setting is off. |
| `image` | Site-relative path of an image for `og:image`. |
| `author` | Shown in the post header, for sites with guest posts. |
| `series` | Name of a series; needs the `series` plugin. |

The complete, uninterpreted front matter is also available as `page.meta`.

A wrong type is an error, not a guess. `draft: yes` is the string `"yes"`
in inkstone's YAML, and the build stops and tells you that `draft` has to
be `true` or `false`, with the file name.

### Dates

Dates can be written as `2024-05-03`, `2024-05-03 14:30`,
`2024-05-03T14:30:00+02:00`, or in words (`May 3, 2024`). A date without a
time zone is taken to be in the zone set by `timezone` in the config:
`"UTC"` by default, or an offset such as `"+01:00"`.

If a file is named like `2024-05-03-hello-world.md`, the date and the slug
come from the name and you can leave both out of the front matter:

| File name | `date` | `slug` |
|-----------|--------|--------|
| `2024-05-03-hello-world.md` | 2024-05-03 | `hello-world` |
| `2024-05-03_hello.md` | 2024-05-03 | `hello` |
| `hello-world.md` | none | `hello-world` |
| `trip/index.md` (a bundle) | none | `trip` |

Front matter wins when both are present. That lets you keep a file name
for sorting in your editor and still publish under a different date.

Pages dated in the future are skipped until that date arrives, or until you
build with `--future` (or `build.future = true`). This is "scheduled
posts" for people who rebuild their site from a cron job.

### Permalinks

By default a page's URL mirrors its path. A section can have a pattern
instead:

```toml
[permalinks]
posts = "/:year/:month/:slug/"
notes = "/n/:slug/"
```

| Token | Value |
|-------|-------|
| `:year`, `:month`, `:day` | from the page date, zero-padded |
| `:slug` | the page slug |
| `:title` | the slugified title |
| `:section` | the section name |
| `:filename` | the file name without extension, date prefix and all |

The date tokens need a date to work with, so every page in a section with
such a pattern should have one. The pattern applies to the pages of the
section, not to the section's own list page, which stays at `/posts/`.

## Sections

Each directory under `content/` is a section, and gets a list page. The
section's `_index.md` configures it:

```markdown
---
title: Projects
description: Things I have made that are still alive.
sort_by: weight
paginate: 12
---

This text appears above the list.
```

| Key | Default | Meaning |
|-----|---------|---------|
| `title` | from the directory name | Heading of the list page, and what breadcrumbs and menus fall back to. |
| `description` | `""` | Shown under the title. |
| `sort_by` | `date` | `date` (newest first), `weight` (lowest first) or `title` (A to Z). |
| `paginate` | `pagination.per_page` | Items per page for this section. |
| `template` | `<section>/section.html`, then `section.html` | Template for the list page. |

The order chosen here is also the order `page.prev` and `page.next` follow,
so the previous/next links at the bottom of a post always agree with the
list.

Sections nest. `content/docs/guide/` is the section `docs/guide`, its
parent is `docs`, and `docs` lists it among its `subsections`. Pages
belong to the innermost section only.

Second and later pages of a list live at `/posts/page/2/` and so on; the
word `page` comes from `pagination.path`.

The home page is special: it has no section. It lists the newest pages of
the sections named in `feeds.sections` (by default just `posts`), with the
same pagination settings.

## Page bundles

When a post has images, keeping them next to the text is more pleasant
than a shared `static/img/` folder:

```
content/posts/trip/
  index.md
  harbour.jpg
  map.svg
```

`index.md` is the page; the other files are its **resources**. They are
copied next to the page in the output, so relative links work:

```markdown
![The harbour at six in the morning](harbour.jpg)
```

In templates the resources are available as `page.resources`, each with a
`name`, a `url` and a `source_path`.

The slug of a bundle is the name of its directory. I put the date of a
bundle in its front matter and keep the directory name clean, since the
directory name is what shows up in every image URL.

## Summaries

List pages and feeds show a summary of each page. inkstone picks the first
of these that exists:

1. The text before a `<!-- more -->` marker in the body.
2. `summary` in the front matter (Markdown is allowed).
3. The first paragraph.

```markdown
This paragraph is the summary. It can contain *formatting* and
[links](https://example.com).

<!-- more -->

The rest of the post.
```

The marker itself never appears in the output. On the page itself the full
text is shown; the summary is not cut off or repeated.

## Drafts

```yaml
draft: true
```

A draft is invisible to a normal build: no page, not in lists, feeds,
the sitemap or the search index. To see it:

```
inkstone serve --drafts
inkstone list --drafts
```

The default theme marks drafts with a badge and a dashed line under the
header, so you do not mistake a preview for the published site. The
`drafts_banner` plugin goes further and puts a banner on every draft page.

There is no separate drafts folder. Publishing is deleting one line.

## Taxonomies

Tags and categories are two instances of the same thing: a *taxonomy* is a
named way of grouping pages, and each value is a *term*.

```toml
[taxonomies]
tags = "tag"
categories = "category"
```

The key is the plural, used as the front matter key and the URL prefix;
the value is the singular, used in headings. With the configuration above:

- `tags: [python, parsing]` in a page's front matter files it under two
  terms,
- `/tags/` lists all tags with their page counts,
- `/tags/python/` lists the pages tagged `python`, paginated like a section.

To add a taxonomy, add a line: `series = "series"` or `authors = "author"`.
To have none, set `[taxonomies]` to an empty table.

Term names are used as written for display and slugified for URLs, so
`Site Generators` lives at `/tags/site-generators/`. Terms are keyed by
that slug, which means two spellings that slugify the same (`Python` and
`python`) end up as one term. Pick a spelling and stick to it;
`inkstone list --tag python` is a quick way to see what a term catches.

## Data files

Files in `data/` are loaded once and available to every template as
`site.data.<name>`:

| File | In templates |
|------|--------------|
| `data/links.yaml` | `site.data.links` |
| `data/projects.json` | `site.data.projects` |
| `data/team/roles.toml` | `site.data.team.roles` |
| `data/prices.csv` | `site.data.prices`, a list of rows keyed by the header line |

JSON, YAML, TOML, CSV and TSV are understood. Sub-directories nest, and two
files that would land on the same name (`links.yaml` next to `links.json`)
are an error rather than a coin toss.

Use data files for content that is structured rather than prose: a list of
talks, a blogroll, opening hours. The example site drives its projects
page from one.

## Static files

`static/` is copied to the output root as it is: `static/robots.txt`
becomes `/robots.txt`, `static/img/me.jpg` becomes `/img/me.jpg`. Themes
have a `static/` of their own; when both have a file of the same name,
yours wins.

inkstone generates `robots.txt`, `sitemap.xml`, the feeds and
`search-index.json` itself. Do not also keep files with those names in
`static/`. If you want a hand-written `robots.txt`, turn the generated one
off first (`robots.enabled = false`), so it is clear which one you get.

## Seeing what you have

`inkstone list` prints a table of every page with its date, section, title
and URL. The options narrow it down:

```
inkstone list --section posts --sort title
inkstone list --tag python
inkstone list --drafts
inkstone list --format json
inkstone list --tag python --format paths
```

`--drafts` includes the drafts, which a plain `list` leaves out like a
build would. The `json` format is for scripts. The `paths` format prints
one source file per line and is meant for piping into other tools:

```
inkstone list --tag python --format paths | xargs wc -w
```
