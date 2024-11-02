# Templates

Templates decide what a page looks like. inkstone's template language is a
Jinja look-alike: if you have written Jinja or Django templates you can
read these already, and the [syntax reference](#syntax-reference) below
covers the rest.

You do not have to write any templates to use inkstone. The default theme
is complete. This page is for when you want to change a piece of it, or
all of it.

## Where templates come from

When something asks for the template `partials/footer.html`, inkstone looks
in these places and takes the first hit:

1. `templates/` in your site
2. the theme's `templates/` (`themes/<name>/templates/` in your site if you
   have a local copy, otherwise the built-in theme inside inkstone)
3. the parent theme's `templates/`, if the theme's `theme.toml` says
   `inherit = "..."`, and so on up the chain

So to change the footer you do not copy the theme. You create one file,
`templates/partials/footer.html`, and it replaces the theme's. Everything
else keeps coming from the theme, including future fixes to it.

Template names always use forward slashes, on Windows too.

## Which template renders a page

Every page has a *kind*, and the kind decides which templates are tried.
The first one that exists wins.

| Kind | What it is | Templates tried, in order |
|------|-----------|---------------------------|
| `page` | a Markdown file | `template` from the front matter, `<section>/page.html`, `page.html` |
| `section` | the list page of a directory | `template` from `_index.md`, `<section>/section.html`, `section.html` |
| `home` | the front page | `index.html` |
| `taxonomy` | the list of terms, `/tags/` | `<plural>/taxonomy.html`, `taxonomy.html` |
| `term` | pages with one term, `/tags/python/` | `<plural>/term.html`, `term.html` |
| `404` | the not-found page | `404.html` |

That is why the default theme has a `posts/page.html`: pages in the
`posts` section get the blog-post layout, everything else falls through to
the plainer `page.html`. To give your `projects` section its own list
layout, add `templates/projects/section.html`; the example site does
exactly this.

Nested sections look upwards before giving up: a page in `docs/guide`
tries `docs/guide/page.html`, then `docs/page.html`, then `page.html`. So
one `docs/page.html` covers the whole documentation tree.

`page.layout` tells you which template was picked in the end, which is
handy when the answer surprises you.

## What a template can see

### Context

| Name | Value |
|------|-------|
| `site` | The whole site: pages, sections, taxonomies, menus, data. |
| `config` | The configuration. `config.params.accent`, `config.feeds.rss`. |
| `page` | The page being rendered. |
| `section` | The page's section, when it has one. |
| `pages` | On home, section and term pages: the items on this page of the list. |
| `paginator` | On the same pages: where we are in the list. |
| `taxonomy`, `term` | On taxonomy and term pages. |
| `now` | Build time, as a datetime with a time zone. |
| `inkstone` | `inkstone.version`. |

### Page

| Attribute | Meaning |
|-----------|---------|
| `kind` | `"page"`, `"section"`, `"home"`, `"taxonomy"`, `"term"`, `"404"` or `"virtual"` |
| `title`, `slug`, `description` | |
| `date`, `updated` | datetimes, or none |
| `draft`, `weight` | |
| `url` | site-relative, starts with `/`: `/2024/05/hello-world/` |
| `permalink` | absolute: `base_url` joined with `url` |
| `section` | the section it belongs to (none for the home page) |
| `tags`, `categories` | lists of strings |
| `taxonomies` | `{plural name: [term names]}`, for taxonomies you added yourself |
| `content` | the rendered HTML |
| `summary` | HTML of the summary |
| `truncated` | true when the summary is shorter than the content, i.e. there is more to read |
| `toc`, `toc_html` | the headings as a tree of entries (`level`, `id`, `title`, `children`), and as ready-made nested `<ul>` markup |
| `word_count`, `reading_time` | words, and minutes (at least 1) |
| `prev`, `next` | neighbours in the section, in the section's sort order |
| `params` | front matter keys inkstone does not interpret itself |
| `meta` | the front matter exactly as written |
| `resources` | files next to a page bundle's `index.md`: `name`, `url`, `source_path` |
| `aliases` | old URLs of this page |
| `source_path`, `output_path` | where it came from and where it goes, as POSIX paths |
| `template`, `layout` | the template asked for in front matter, and the one actually used |

Plugins add attributes. With the `related` plugin enabled there is
`page.related`, with `series` there is `page.series`. Test for them with
`is defined` so the template still works when the plugin is off:

```html
{% if page.related is defined and page.related %}
  ...
{% endif %}
```

### Section

`name` (`"posts"`, or `"docs/guide"` when nested), `title`, `url`, `pages`
(sorted as the section asks), `subsections`, `parent`, `index` (the page
made from `_index.md`), `meta` and `paginate`.

### Site

| Attribute | Meaning |
|-----------|---------|
| `title`, `base_url`, `language`, `author`, `params` | straight from the config |
| `pages` | every regular page, newest first |
| `all_pages` | everything that gets an output file, generated pages included |
| `sections` | `{name: Section}` |
| `home` | the home page |
| `taxonomies` | `{plural: Taxonomy}` |
| `menus` | `site.menus.main` is a list of entries, sorted by weight, each with `name`, `url`, `weight` and `children`; a menu that is not defined is an empty list |
| `data` | the contents of `data/` |
| `build_time` | same as `now` |

### Lists of pages

`site.pages`, `section.pages`, `term.pages` and `pages` are ordinary lists,
so slicing, `length` and every list filter work on them. They also have a
few methods of their own, each returning a new list, so they chain:

| Method | Keeps |
|--------|-------|
| `in_section("posts")` | pages of that section and the sections below it |
| `tagged("python")` | pages with that tag; `tagged("guides", "categories")` for another taxonomy |
| `where("draft")`, `where("kind", "page")`, `where("weight", ">", 3)` | pages whose attribute is truthy, equal, or compares that way |
| `exclude(...)` | the opposite of `where` |
| `dated()` | pages that have a date |
| `sort_by("title")`, `sort_by("-date")` | everything, reordered; a minus sign reverses |
| `limit(5)`, `offset(5)` | the first five, or all but the first five |
| `first()`, `last()` | one page, or nothing if the list is empty |
| `group_by_year()`, `group_by_month()` | pairs of year (or year and month) and pages, newest first |

```html
<h2>Latest on Python</h2>
<ul>
{% for post in site.pages.in_section("posts").tagged("python").limit(3) %}
  <li><a href="{{ url_for(post.url) }}">{{ post.title }}</a></li>
{% endfor %}
</ul>

{% for year, posts in site.pages.group_by_year() %}
  <h2>{{ year }}</h2>
  ...
{% endfor %}
```

### Taxonomy, term, paginator

A taxonomy has `name` (plural), `singular`, `url` and `terms` (a mapping
from slug to term). Looping over the taxonomy itself gives the terms sorted
by name. A term has `name`, `slug`, `url`, `pages` and `count`.

The paginator:

| Attribute | Meaning |
|-----------|---------|
| `items` | this page's slice, the same list as `pages` |
| `page`, `pages` | current page number (from 1) and how many there are |
| `total`, `per_page` | number of items overall, and per page |
| `has_prev`, `has_next` | |
| `prev_url`, `next_url`, `first_url`, `last_url` | |
| `page_urls` | a list of `(number, url)` pairs for numbered links |
| `window(around)` | the same pairs, shortened for long lists to the first page, the last page and `around` pages either side of the current one; a gap is a pair of nones |

```html
{% for number, url in paginator.page_urls %}
  {% if number == paginator.page %}
    <span aria-current="page">{{ number }}</span>
  {% else %}
    <a href="{{ url_for(url) }}">{{ number }}</a>
  {% endif %}
{% endfor %}
```

## Functions

These are available everywhere, including inside macros.

| Function | Returns |
|----------|---------|
| `url_for(path)` | A link to a path on this site. Use it for every internal link. |
| `absolute_url(path)` | The same with scheme and host, for feeds and Open Graph tags. |
| `asset(path)` | The URL of a static file, with its fingerprint when fingerprinting is on. |
| `asset_integrity(path)` | The `sha384-...` value for an `integrity` attribute. |
| `get_page(path)` | A page by source path (`"about.md"`) or URL (`"/about/"`). |
| `get_section(name)` | A section by name. |
| `get_data(dotted)` | `get_data("team.roles")` is `site.data.team.roles`, but missing levels give nothing instead of an error. |
| `highlight_css(style)` | The stylesheet for a highlighting style, for inlining in a `<style>` tag. |

`url_for` matters more than it looks. `page.url` is `/about/`. If the site
is served from `https://example.com/blog/`, the link has to be
`/blog/about/`, and `url_for` is what adds the prefix:

```html
<a href="{{ url_for(page.url) }}">{{ page.title }}</a>
<a href="{{ url_for('/tags/') }}">All tags</a>
<link rel="stylesheet" href="{{ asset('css/main.css') }}">
<meta property="og:image" content="{{ absolute_url('/img/card.png') }}">
```

A template that writes `href="/about/"` by hand works until the day
someone hosts the site in a sub-directory. The default theme's tests fail
on any literal internal link for this reason.

## Filters

A filter transforms the value on its left: `{{ page.title | upper }}`.
Filters chain, and take arguments in parentheses.

inkstone adds these to the ones the template engine already has:

| Filter | Example | Result |
|--------|---------|--------|
| `date` | `{{ page.date \| date("long") }}` | `September 15, 2024` |
| `markdown` | `{{ config.params.intro \| markdown }}` | rendered HTML |
| `slugify` | `{{ "Site Generators" \| slugify }}` | `site-generators` |
| `absolute_url` | `{{ page.url \| absolute_url }}` | `https://example.com/about/` |
| `relative_url` | `{{ "/about/" \| relative_url }}` | same as `url_for` |
| `strip_html` | `{{ page.summary \| strip_html }}` | the text without tags |
| `truncate_html` | `{{ page.content \| truncate_html(300) }}` | shortened, with open tags closed properly |
| `reading_time` | `{{ page.raw \| reading_time }}` | minutes, as a number |
| `humanize_bytes` | `{{ 1536 \| humanize_bytes }}` | `1.5 KB` |

`date` takes either a `strftime` pattern or one of these names:

| Name | Output |
|------|--------|
| `iso` | `2024-09-15` |
| `short` | `Sep 15, 2024` |
| `long` | `September 15, 2024` |
| `full` | `Sunday, September 15, 2024` |
| `month` | `September 2024` |
| `year` | `2024` |
| `time` | `14:30` |
| `datetime` | `2024-09-15 14:30` |
| `rfc3339` | `2024-09-15T14:30:00+02:00` |
| `rfc2822` | `Sun, 15 Sep 2024 14:30:00 +0200` |

In `strftime` patterns, `%-d` (day without a leading zero) works on every
platform, Windows included: `{{ page.date | date("%-d %B %Y") }}` gives
`15 September 2024`.

The built-in filters, briefly:

| | |
|---|---|
| Text | `upper`, `lower`, `title`, `capitalize`, `trim`, `replace(old, new)`, `truncate(length)`, `wordcount`, `striptags`, `indent`, `urlencode`, `urlize`, `format` |
| Escaping | `escape` (or `e`), `safe`, `forceescape` |
| Missing values | `default(value)` (or `d`); `default(value, true)` also replaces empty and false values |
| Lists | `length`, `first`, `last`, `join(", ")`, `sort`, `reverse`, `unique`, `batch(n)`, `slice(n)`, `list`, `sum`, `min`, `max` |
| Lists of objects | `sort(attribute="weight")`, `map(attribute="title")`, `selectattr("draft")`, `rejectattr("draft")`, `groupby("section.name")`, `select`, `reject` |
| Numbers | `int`, `float`, `round`, `abs`, `filesizeformat` |
| Other | `tojson`, `items`, `dictsort`, `attr`, `xmlattr`, `pprint` |

A few examples of the ones worth knowing:

```html
{# the five newest posts tagged python, as a comma-separated line #}
{{ site.taxonomies.tags.terms.python.pages[:5] | map(attribute="title") | join(", ") }}

{# posts grouped by year #}
{% for year, posts in site.pages | groupby("date.year") | reverse %}
  <h2>{{ year }}</h2>
  {% for post in posts %}<a href="{{ url_for(post.url) }}">{{ post.title }}</a>{% endfor %}
{% endfor %}

{# pass data to a script without worrying about quoting #}
<script>const tags = {{ page.tags | tojson }};</script>
```

## Syntax reference

There are three kinds of tag:

```html
{{ expression }}      prints a value
{% statement %}       does something: if, for, block, include, ...
{# comment #}         is removed from the output
```

### Output and escaping

Everything printed with `{{ }}` is HTML-escaped, so a title containing
`<T>` cannot break the page. Values that are already markup, such as
`page.content`, the result of the `markdown` filter and anything a macro
returns, are not escaped again. To print a string you know to be safe
HTML (a config value, say), mark it: `{{ config.params.footer_text | safe }}`.

### Expressions

```html
{{ page.title }}                    attribute
{{ site.sections["posts"].title }}  item; the two forms are interchangeable
{{ pages | length }}                filter
{{ "Page " ~ paginator.page }}      ~ joins as text
{{ page.title or site.title }}      or / and / not
{{ "new" if post.date > cutoff else "old" }}
{{ [1, 2, 3] }} {{ {"a": 1} }}      list and dict literals
{{ pages[:5] }} {{ pages[-1] }}     slices and negative indexes
```

Comparisons are `==`, `!=`, `<`, `<=`, `>`, `>=`, `in` and `not in`.
Arithmetic is `+`, `-`, `*`, `/`, `//`, `%` and `**`.

Tests come after `is`:

```html
{% if page.related is defined %}
{% if loop.index is even %}
{% if page.url is startingwith("/docs/") %}
```

The useful ones are `defined`, `undefined`, `none`, `string`, `number`,
`mapping`, `sequence`, `even`, `odd`, `divisibleby(n)`, `in(list)`,
`startingwith(text)`, `endingwith(text)` and `containing(item)`.

### Missing values

A name or attribute that does not exist is *undefined*. Undefined prints as
nothing, counts as false, loops zero times, and you can keep asking it for
attributes: `{{ page.params.author.name }}` is simply empty on a page with
no author. Calling it or doing arithmetic or `<` / `>` comparisons with it
is an error, because that is nearly always a typo.

```html
{{ page.params.subtitle | default("No subtitle") }}
{% if paginator is defined and paginator.page > 1 %} ... {% endif %}
```

### if

```html
{% if page.draft %}
  <span>Draft</span>
{% elif page.date > now %}
  <span>Scheduled</span>
{% else %}
  <span>Published</span>
{% endif %}
```

### for

```html
{% for post in pages %}
  <li class="{{ 'first' if loop.first }}">{{ loop.index }}. {{ post.title }}</li>
{% else %}
  <li>No posts yet.</li>
{% endfor %}
```

The `else` branch runs when the list is empty. Inside the loop, `loop`
has `index` (from 1), `index0`, `first`, `last`, `length`, `revindex`,
`depth`, `previtem`, `nextitem`, `cycle("odd", "even")` and
`changed(value)`.

Loops can unpack (`{% for slug, term in taxonomy.terms | items %}`), filter
(`{% for post in pages if not post.draft %}`) and stop early with
`{% break %}` and `{% continue %}`.

### set and with

```html
{% set description = page.description or config.description %}

{% set card %}
  <div class="card">{{ page.title }}</div>
{% endset %}

{% with post = page.next %}
  ...post only exists in here...
{% endwith %}
```

A variable set inside a `for` loop is gone at the end of each round. To
count across a loop, use a namespace:

```html
{% set count = namespace(drafts=0) %}
{% for post in pages %}
  {% if post.draft %}{% set count.drafts = count.drafts + 1 %}{% endif %}
{% endfor %}
{{ count.drafts }} drafts
```

### Inheritance: extends, block, super

A base template defines the page skeleton with named holes:

```html
<!-- base.html -->
<title>{% block title %}{{ site.title }}{% endblock %}</title>
<main>{% block content %}{% endblock %}</main>
{% block scripts %}<script src="{{ asset('js/nav.js') }}" defer></script>{% endblock %}
```

A child fills the ones it cares about:

```html
{% extends "base.html" %}

{% block title %}{{ page.title }} · {{ super() }}{% endblock %}

{% block content %}
  <h1>{{ page.title }}</h1>
  {{ page.content }}
{% endblock %}
```

`{{ super() }}` prints what the parent had in that block, so you can add to
a block instead of replacing it. In a child template, only what is inside
blocks is printed; text outside them is ignored.

### include

```html
{% include "partials/footer.html" %}
{% include "partials/sidebar.html" ignore missing %}
```

The included template sees every variable that exists at that point,
including loop variables. That is how the post list works:

```html
{% for post in pages %}
  {% include "partials/post_card.html" %}   {# uses `post` #}
{% endfor %}
```

### Macros and import

A macro is a function that returns markup:

```html
{% macro time_tag(value, format="long") %}
  <time datetime="{{ value | date('iso') }}">{{ value | date(format) }}</time>
{% endmacro %}

{{ time_tag(page.date) }}
{{ time_tag(page.updated, format="short") }}
```

Keep macros in their own file and import them:

```html
{% import "partials/macros.html" as m %}
{{ m.icon("rss") }}

{% from "partials/macros.html" import icon, format_date %}
{{ icon("rss") }}
```

### Who sees what

This trips everyone up once, so it gets its own heading.

- An **included** template sees everything the including one does.
- An **imported** template does not see the page context. Macros get what
  you pass them as arguments, plus the global functions and filters. Pass
  `page` in if the macro needs it.
- A **block** sees the template's top-level variables but not variables set
  inside another block, or the loop variable of a loop it sits in. A `set`
  that a block needs goes inside that block (or mark the block
  `{% block item scoped %}`).

### Whitespace

A minus sign inside a tag eats the whitespace on that side:

```html
<ul>
  {%- for tag in page.tags %}
  <li>{{ tag }}</li>
  {%- endfor %}
</ul>
```

The default theme mostly does not bother. Blank lines in HTML are harmless
and `build.minify` removes them anyway.

### Literal braces

To show template syntax on a page (in documentation about templates, say),
wrap it in `{% raw %}` and `{% endraw %}`. Markdown content is never run
through the template engine, so posts do not need this, only templates.

## The default theme

The built-in theme lives in `inkstone/themes/default/`. Its templates:

| Template | Renders |
|----------|---------|
| `base.html` | the page skeleton everything else extends |
| `index.html` | the home page: intro text and recent posts |
| `page.html` | a plain page |
| `posts/page.html` | a blog post: meta line, table of contents, tags, previous/next, related posts, series box |
| `section.html` | a section list |
| `taxonomy.html`, `term.html` | the tag index and one tag's posts |
| `search.html` | the search results page (opt-in, see [Search](search.md)) |
| `404.html` | the not-found page |

The blocks of `base.html`, which are the hooks a child template has:

| Block | Contains |
|-------|----------|
| `title` | the text of `<title>` |
| `head` | meta tags, Open Graph, feed links (from `partials/head.html`) |
| `stylesheets` | the theme's `<link rel="stylesheet">` tags |
| `custom_css` | the stylesheets listed in `params.custom_css` |
| `head_extra` | empty; for anything else you want in `<head>` |
| `header` | the site header |
| `main` | the inside of `<main>`; wraps `content` in the page container |
| `content` | the page itself |
| `footer` | the site footer |
| `scripts` | the script tags at the end of `<body>` |

And the partials, each of which you can replace on its own:

| Partial | What it is |
|---------|-----------|
| `partials/head.html` | description, canonical link, Open Graph, feed links, accent colour override |
| `partials/header.html` | title, main menu, search box, theme switch |
| `partials/footer.html` | copyright line, footer menu, social links |
| `partials/post_card.html` | one entry in a list of posts; expects `post` |
| `partials/post_meta.html` | date, updated, reading time under a post title |
| `partials/post_nav.html` | previous and next post |
| `partials/pagination.html` | page numbers under a list |
| `partials/tag_list.html` | a row of tag links; expects `tags` |
| `partials/toc.html` | the table of contents box |
| `partials/breadcrumbs.html` | home, section, page |
| `partials/search_box.html` | the search field in the header |
| `partials/related.html`, `partials/series.html` | the boxes for those two plugins |
| `partials/macros.html` | `icon`, `format_date`, `reading_time`, `count`, `sr` |

### Theme settings

Set these under `[params]` in `inkstone.toml`:

| Param | Default | Meaning |
|-------|---------|---------|
| `accent`, `accent_dark` | empty | Accent colour for the light and dark scheme. Set both or neither. |
| `show_reading_time` | `true` | "4 min read" on posts and cards. |
| `show_toc` | `true` | Table of contents beside posts. Per page: `toc: false` in front matter. |
| `show_breadcrumbs` | `true` | The trail above page titles. |
| `show_theme_toggle` | `true` | The light/dark button. Without it the site follows the system setting. |
| `show_post_nav` | `true` | Previous/next links under posts. |
| `date_format` | `"%-d %B %Y"` | Anything the `date` filter accepts. |
| `footer_text` | empty | Replaces the copyright line. HTML allowed. |
| `search_url` | `"/search/"` | Where the search page lives. |
| `og_image` | empty | Fallback image for link previews. |
| `custom_css` | `[]` | Stylesheets from your `static/`, loaded after the theme's. |
| `social.github`, `social.mastodon` | empty | Profile URLs, linked in the footer with `rel="me"`. |
| `social.email` | empty | An address; becomes a `mailto:` link. |
| `social.rss` | `true` | Show the feed icon. |

A footer menu appears if you define `[[menus.footer]]` entries.

### Restyling without touching templates

The stylesheet is driven by custom properties, so a few lines in a
`custom_css` file go a long way:

```css
:root {
  --measure: 40rem;                 /* width of the text column */
  --font-sans: "Inter", system-ui, sans-serif;
  --radius: 2px;
}
```

The palette is `--bg`, `--bg-raised`, `--bg-sunken`, `--text`,
`--text-muted`, `--border`, `--border-strong`, `--accent` and the four
admonition colours `--note`, `--tip`, `--warning`, `--danger`. Dark values
are set under `@media (prefers-color-scheme: dark)` on
`:root:not([data-theme="light"])` and again under `:root[data-theme="dark"]`
for readers who used the switch; override both if you change dark colours.

## Writing a theme

A theme is a directory:

```
themes/mytheme/
  theme.toml
  templates/
  static/
```

`theme.toml` needs three keys:

```toml
name = "mytheme"
description = "What it looks like, in a sentence."
version = "0.1.0"

[params]
show_sidebar = true
```

`[params]` holds the theme's defaults. They are merged *under* the site's
own `[params]`, so `config.params.show_sidebar` is always defined, and a
site changes it by setting the same key.

A theme that stands alone has to provide the templates the builder asks
for by name: `index.html`, `page.html`, `section.html`, `taxonomy.html`,
`term.html` and `404.html`. In practice they all extend a `base.html`. The
smallest useful one:

```html
<!doctype html>
<html lang="{{ site.language }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}{{ page.title or site.title }}{% endblock %}</title>
  <link rel="stylesheet" href="{{ asset('css/style.css') }}">
  {% if config.markdown.highlight %}
  <link rel="stylesheet" href="{{ asset('css/highlight.css') }}">
  {% endif %}
</head>
<body>
  <header><a href="{{ url_for('/') }}">{{ site.title }}</a></header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

and `page.html`:

```html
{% extends "base.html" %}
{% block content %}
<article>
  <h1>{{ page.title }}</h1>
  {{ page.content }}
</article>
{% endblock %}
```

Files in the theme's `static/` are copied to the output root:
`static/css/style.css` is served as `/css/style.css`. Always reference
them through `asset()`, never by a literal path, or fingerprinting breaks.
Two files exist in the output without being in any `static/` directory:
`css/highlight.css` (when `markdown.highlight` is on) and
`js/inkstone-search.js` (when search is on).

Put the theme in `themes/mytheme/` in your site and set `theme = "mytheme"`.

## Theme inheritance

Most of the time you do not want a whole new theme. You want the default
one with a different skeleton, or different cards. A theme can name a
parent:

```toml
name = "paper"
description = "One narrow column in a serif face."
version = "0.2.0"
inherit = "default"

[params]
show_toc = false
date_format = "%Y-%m-%d"
```

Now every template and static file the child does not have is taken from
the parent. The built-in `paper` theme is the worked example. It consists of:

```
paper/
  theme.toml
  templates/
    base.html                 a different page skeleton
    partials/header.html      title and a row of links, nothing else
    partials/footer.html      one line
    partials/post_card.html   date and title instead of a card
    partials/post_meta.html   a plain line instead of the icon row
  static/css/paper.css
```

Five templates and a stylesheet. `index.html`, `page.html`,
`posts/page.html`, `search.html` and the rest are the default theme's, and
they work because paper's `base.html` keeps the same block names. When
`posts/page.html` says `{% extends "base.html" %}`, the lookup order finds
paper's `base.html` first. When it includes `partials/tag_list.html`,
paper has none, so the default one is used.

Params stack the same way: the default theme's values, then paper's on
top, then your site's.

Try it on the example site:

```
inkstone -C examples/blog serve --port 8001
```

with `theme = "paper"` in its `inkstone.toml`.

## When a template fails

Template errors name the template and the line, and try to guess what you
meant:

```
templates/projects/section.html:14: no filter named 'slugfy', did you mean 'slugify'?
```

With `inkstone serve` the same message appears in the browser. A missing
*template* lists the names that were tried. A missing *variable* is not an
error (see [Missing values](#missing-values)), which is convenient right up
to the moment you misspell `page.titel` and get an empty heading. When
output is unexpectedly blank, check the spelling first.
