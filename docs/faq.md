# FAQ

Questions I have been asked, or have asked myself at one in the morning.

## Why another static site generator?

Because the one I used pulled in about forty packages and broke on every
second upgrade, and because I wanted to know how the parts work. inkstone
is what came out: a generator with no runtime dependencies that I can read
from one end to the other.

It is not trying to replace Hugo, Pelican, Eleventy or Zola. If you are
happy with one of those, stay there. inkstone suits you if you want
something small, written in Python, that will still run unchanged in five
years because there is nothing underneath it to rot.

## Is it fast?

Fast enough. A blog with a hundred posts builds from scratch in a couple
of seconds and rebuilds after an edit in a fraction of one, because only
the pages whose inputs changed are rendered again. It is pure Python and
will never win a benchmark against a compiled generator. If you have
twenty thousand pages, use one of those.

## Which Python do I need?

3.10 or newer. 3.11 or newer if your config file or front matter is TOML,
since that is when `tomllib` joined the standard library. Nothing else:
`pip install` pulls in no other packages.

## Which YAML is supported?

A subset, read by inkstone's own parser. It covers what front matter and
data files use:

- mappings and lists, block style and flow style (`[a, b]`, `{a: 1}`)
- plain, single-quoted and double-quoted strings
- multi-line strings with `|` and `>`
- numbers, `true` / `false`, `null`, dates and datetimes
- comments, anchors and aliases, several documents in one file

Not supported, and reported as an error rather than silently misread:
custom tags (`!!python/object`), complex keys (`? [a, b]`) and directives
(`%YAML`).

One deliberate difference from older YAML parsers: only `true` and `false`
are booleans. `yes`, `no`, `on` and `off` are ordinary strings, so
`country: no` means Norway and `draft: yes` is an error about `draft`
needing a boolean instead of a surprise.

## My post does not show up

In rough order of likelihood:

1. It has `draft: true`. Build or serve with `--drafts` to see it.
2. Its date is in the future. Use `--future`, or check the year.
3. The front matter did not parse and the build printed an error you
   scrolled past. Run `inkstone check`.
4. The file is not under `content/`, or its name matches a pattern in
   `ignore`.
5. It is there, on page 2 of the list.

`inkstone list --drafts` shows every page inkstone knows about, with its
date and URL, which usually settles it.

## The date of my post is off by a day

A date without a time is midnight in the zone given by `timezone` in the
config, which defaults to UTC. If you live east or west of Greenwich and
publish around midnight, set `timezone` to your offset (`"+02:00"`).
A named zone such as `Europe/Berlin` also works wherever Python can find
the time zone database. On Windows it cannot, unless you install the
`tzdata` package, and I would rather write an offset twice a year than add
a dependency.

## Can I change the URL of a page?

Per page, with `slug` in the front matter. Per section, with a pattern in
`[permalinks]`. See [Content](content.md#permalinks). If the page has been
published before, add the old address to `aliases` and enable the
`redirects` plugin so existing links keep working.

## How do I add a page to the menu?

Either in the config, which keeps the whole menu in one place:

```toml
[[menus.main]]
name = "About"
url = "/about/"
weight = 20
```

or from the page itself, with `menu: main` in its front matter. I use the
config for the handful of fixed entries and never needed the second form,
but it is handy when a section of pages should all appear in a sidebar
menu without listing each one.

## Can I use HTML in Markdown?

Yes. It is passed through as it is. For a snippet you use repeatedly, a
[shortcode](plugins.md#shortcodes) is tidier.

## How do I change the look?

In increasing order of effort:

1. Theme settings: accent colour, date format, what is shown. See
   [Theme settings](templates.md#theme-settings).
2. A stylesheet of your own, listed in `params.custom_css`, overriding
   the theme's CSS custom properties.
3. Replacing single templates by putting a file of the same name in
   `templates/`. The footer is `templates/partials/footer.html`.
4. A theme that inherits from the default one and replaces a few pieces.
5. A theme from scratch.

Most people stop at 2 or 3. [Templates](templates.md) covers all five.

## Is there a dark mode?

The default theme follows the reader's system setting and has a switch in
the header that remembers their choice. Code highlighting follows along if
you set `highlight_style_dark` under `[params]`. The paper theme follows
the system setting and has no switch.

## Does the site need JavaScript?

No. Every page is complete HTML and reads fine with scripts off. What
JavaScript adds: the theme switch, the mobile menu button (without it the
menu is simply always open), copy buttons on code blocks, footnote
previews, the scroll position marker in the table of contents, and search.
Search is the only feature that does not work at all without it.

No script, font or stylesheet is loaded from another host.

## Can it resize images?

No. Reading an image's width and height is easy to do with the standard
library; decoding and resampling JPEGs is not. The `image_dims` plugin adds
`width` and `height` attributes to `<img>` tags so pages do not jump while
loading, and that is as far as it goes. Resize before you commit.

## Can I have comments?

Not built in. A static site cannot store them. People bolt on a hosted
comment service with a script tag in a template override. I link an e-mail
address instead and get fewer, better replies.

## How do I show something on every page?

Override the partial that is closest: `partials/footer.html` for a line
in the footer, `partials/head.html` or the `head_extra` block for a tag
in `<head>`. For a value rather than markup, add it under `[params]` and
print it in a template with `{{ config.params.my_value }}`.

## How do I list pages in a template?

`site.pages` is every regular page, newest first. `site.sections.posts.pages`
is one section in its own sort order. `site.taxonomies.tags.terms` maps
slugs to terms, each with `pages`. For example, the three newest posts
anywhere:

```html
<ul>
{% for post in site.pages[:3] %}
  <li><a href="{{ url_for(post.url) }}">{{ post.title }}</a></li>
{% endfor %}
</ul>
```

## A link works locally and breaks on the server

Three usual suspects:

- The site is served from a sub-directory and a template has a hand-written
  `href="/..."`. Use `url_for`. See
  [Deploying](deploying.md#sites-in-a-sub-directory).
- Case. `Photo.JPG` and `photo.jpg` are the same file on Windows and macOS
  and different files on a Linux server.
- The server does not map `/about/` to `/about/index.html`. Every common
  web server does this by default; object storage buckets sometimes need
  to be told.

`inkstone check` finds links between your own pages that point at nothing,
which covers a good part of this before anything is uploaded.

## The build is not picking up my change

It should. If it does not, run `inkstone build --clean` and compare. If
the clean build is right and the incremental one was wrong, that is a bug
in the cache: please report it with the smallest site that shows it. Known
blind spots are listed in [Internals](internals.md#the-incremental-cache).

## How do I upgrade?

```
cd inkstone
git pull
pip install -e .
```

The cache is keyed on the inkstone version, so the first build after an
upgrade renders everything once. Site-level template overrides are the
thing to look at after an upgrade: if a theme template you replaced has
changed upstream, your copy does not get the change.

## Can I use it as a library?

Yes, and the lower layers do not need a site at all:

```python
from inkstone.markdown import render
from inkstone.config import load_config
from inkstone.build import Builder

print(render("*hello*"))

report = Builder(load_config("path/to/site")).build()
print(report.summary())
```

## Where do I report a bug?

On the issue tracker of the repository. A good report has the inkstone
version (`inkstone version`), the command you ran with `--debug` added, and
if possible a tiny site that reproduces it. For Markdown bugs, the input
and the output you expected are enough.
