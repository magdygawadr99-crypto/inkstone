# Plugins

A plugin is a Python class with a few methods that inkstone calls at fixed
points of a build. The built-in ones cover the things I wanted but did not
think belonged in the core: shortcodes, related posts, redirects, archive
pages. Writing your own takes one file.

## Enabling plugins

Plugins are listed by name in the config. The default is:

```toml
plugins = ["shortcodes", "toc", "reading_time"]
```

Setting `plugins` replaces that list, so to add one, repeat the defaults:

```toml
plugins = ["shortcodes", "toc", "reading_time", "related", "redirects"]
```

The order matters. Hooks run in the order the plugins are listed, and for
hooks that transform text (Markdown in, Markdown out) each plugin sees the
output of the one before it. A plugin can also declare a `priority`; lower
numbers run earlier, and the list order breaks ties. You rarely need to
think about this. The one case that comes up: `shortcodes` should be early,
because other plugins expect to see the expanded text.

Settings for a plugin go in a table of its own:

```toml
[plugin.related]
limit = 5

[plugin.reading_time]
words_per_minute = 200
```

A plugin only ever sees its own table. A table for a plugin that is not
in the `plugins` list does nothing.

A name in the list is looked up in three places, in this order:

1. the built-in plugins, `inkstone/plugins/builtin/<name>.py`
2. your site, `plugins/<name>.py`
3. an importable module path, e.g. `mypackage.inkstone_plugin`

## Built-in plugins

Each of these is a single file in `inkstone/plugins/builtin/`, short enough
to read when you want to know exactly what one does.

| Name | On by default | What it does |
|------|:-------------:|--------------|
| [`shortcodes`](#shortcodes) | yes | `{{< figure ... >}}` and friends in Markdown |
| [`toc`](#toc) | yes | table of contents data for each page |
| [`reading_time`](#reading_time) | yes | word count and reading time |
| [`related`](#related) | | related posts by shared tags |
| [`series`](#series) | | multi-part posts |
| [`archives`](#archives) | | an archive page, by year and month |
| [`redirects`](#redirects) | | redirect pages for `aliases` |
| [`external_links`](#external_links) | | `rel` and `target` on links to other sites |
| [`image_dims`](#image_dims) | | `width` and `height` on images |
| [`footnote_previews`](#footnote_previews) | | footnote text as a tooltip |
| [`drafts_banner`](#drafts_banner) | | a banner on draft pages |
| [`git_dates`](#git_dates) | | `updated` from the git history |
| [`minify`](#minify) | | minify each HTML page |

### shortcodes

Shortcodes are small named snippets you call from Markdown when Markdown
itself has no syntax for what you want. They are expanded before the
Markdown is parsed.

There are two forms. One that stands alone:

```markdown
{{< youtube id="SxdOUGdseq4" >}}
```

and one that wraps content, closed with a slash:

```markdown
{{< note title="Careful" >}}
Back up the output directory before you point `output_dir` somewhere new.
{{< /note >}}
```

Whether a shortcode wraps something is decided by looking for its closing
tag, so the same shortcode can be used either way.

The details of the syntax:

| Written as | Meaning |
|------------|---------|
| `{{< name key="value" >}}` | named arguments; single quotes and backticks work as quotes too |
| `{{< name first "second one" >}}` | positional arguments, for shortcodes that take them |
| `{{< name />}}` | explicitly stands alone, even if a closing tag follows later |
| `{{% name %}}` ... `{{% /name %}}` | the percent form: a shortcode template gets the inner text already rendered as Markdown |
| `{{</* name */>}}` | not a shortcode; printed as `{{< name >}}`, for writing about them |

Anything inside a fenced code block, a code span or an HTML comment is left
alone, so code samples that happen to contain `{{<` are safe. A tag that is
malformed (an unterminated quote, a closing tag without an opening one) is
an error with the file and line, and so is a shortcode name that does not
exist, with a suggestion when it looks like a typo.

#### The shortcodes that ship with inkstone

Most arguments can be given by name or, in the order listed, by position:
`{{< youtube SxdOUGdseq4 >}}` is the same as `{{< youtube id="SxdOUGdseq4" >}}`.

| Shortcode | Arguments | Output |
|-----------|-----------|--------|
| `figure` | `src`, `alt`, `caption`; by name only: `link`, `width`, `height`, `class` | `<figure>` with the image and a `<figcaption>`. The caption may contain inline Markdown. Wrapped around text, the text is the caption. |
| `note` | `type` (`info`, `warning` or `tip`; default `info`); by name: `title` | a call-out box around the body, which is Markdown |
| `details` | `summary`; the bare word `open` to start expanded | a collapsible `<details>` block around the body, which is Markdown |
| `youtube` | `id` (or the whole URL of the video), `title`; by name: `start` in seconds | an embedded player in a responsive 16:9 box |
| `button` | `href`, `text`; by name: `style`, `class`, `new_tab` | a link styled as a button; wrapped around text, the text is the label |
| `kbd` | one or more keys, `Ctrl+Shift+P` | `<kbd>` elements joined with `+` |
| `ref` | `path` of another page below `content/` | that page's URL, for use inside a Markdown link |
| `include` | `file`; by name: `lines="5-12"`, `code="python"` | the content of another file, optionally as a code block |

```markdown
{{< figure src="harbour.jpg" alt="Fishing boats at dawn" caption="Six in the morning, before the fog lifted." >}}

{{< note warning title="Back up first" >}}
The next command deletes the output directory.
{{< /note >}}

{{< details summary="The full traceback" >}}
...long output that most readers will skip...
{{< /details >}}

See [the post about caching]({{< ref "posts/2024-07-14-incremental-builds.md" >}}).
Press {{< kbd Ctrl+S >}} to save.
```

In a page bundle, `src` can be the name of a file next to `index.md`.
Always give `alt`; the caption is for everyone, the alt text is for people
who cannot see the image, and they are rarely the same sentence.

`youtube` is the one feature in inkstone that makes a page load something
from another host. Nothing is requested at build time, and the embed uses
the `youtube-nocookie.com` address, which sets no cookies until the visitor
presses play, but it is still their browser talking to YouTube. For a site
that otherwise makes no third-party requests, a plain link to the video is
the alternative.

For the admonition syntax built into Markdown (`!!! note`), which does the
same job as `note` without a plugin, see
[Markdown](markdown.md#admonitions).

#### Your own shortcodes

A template named `templates/shortcodes/<name>.html` is a shortcode. It is
rendered with these variables:

| Variable | Value |
|----------|-------|
| `args` | positional arguments, a list of strings |
| `kwargs` | named arguments |
| `inner` | what is between the tags: HTML if the percent form was used, the text as written otherwise; empty when the shortcode stands alone |
| `name` | the shortcode's name |
| `page`, `site`, `config` | the usual |

```html
{# templates/shortcodes/aside.html #}
<aside class="aside aside--{{ kwargs.side | default('right') }}">
  {{ inner }}
</aside>
```

```markdown
{{% aside side="left" %}}
A remark that is *not* part of the main argument.
{{% /aside %}}
```

A template with the name of a built-in shortcode replaces it, so
`templates/shortcodes/figure.html` is how you change the markup of every
figure on the site.

| Setting | Default | Meaning |
|---------|---------|---------|
| `strict` | `true` | Treat an unknown shortcode as an error. With `false` it is left in the text as written, with a warning. |
| `templates` | `"shortcodes"` | The directory under `templates/` that holds shortcode templates. |

### toc

Provides `page.toc` (a tree of headings) and `page.toc_html` (the same as
nested lists) for templates, which is what the default theme's "On this
page" box is made of. The Markdown parser collects every heading; this
plugin cuts the list down to the levels you want, and also sees headings
that came out of shortcodes.

| Setting | Default | Meaning |
|---------|---------|---------|
| `min_level` | `2` | Highest heading level to include. `2` leaves out the `<h1>`. |
| `max_level` | `3` | Deepest heading level to include. |
| `min_items` | `1` | A page with fewer headings than this gets no table of contents. |
| `insert` | `""` | Put the list into the text of every page: `"top"` or `"before-first-heading"`. Empty leaves that to the theme. |
| `anchors` | `false` | Add a link to itself to every heading, for copying the address of a section. |
| `anchor_text` | `"¶"` | What that link shows. |
| `anchor_class` | `"heading-anchor"` | Its CSS class. The default theme styles this one. |
| `anchor_position` | `"after"` | `"after"` or `"before"` the heading text. |

Per page, `toc: false` in the front matter switches the list off, and a
table changes the range for that page only:

```yaml
toc:
  max_level: 4
```

To put a table of contents *inside* the text of one page, write `[TOC]`
on a line of its own. That is a Markdown extension and works without this
plugin; with it, the marker gets the same trimmed list.

### reading_time

Sets `page.word_count` and `page.reading_time` (whole minutes, never less
than one). The numbers are worked out from the Markdown source, before
anything is rendered.

| Setting | Default | Meaning |
|---------|---------|---------|
| `words_per_minute` | `220` | Reading speed to assume for prose. |
| `code_blocks` | `"include"` | What to do with code blocks: `"include"` counts them like prose, `"exclude"` skips them, `"separate"` reads them at their own speed. |
| `code_words_per_minute` | `100` | That speed, for `"separate"`. |
| `cjk_chars_per_minute` | `450` | Speed for Chinese, Japanese and Korean text, which is counted by character. |

When you know better than the estimate, say so in the front matter:
`reading_time: 12`.

### related

Adds `page.related`: a list of other pages, most similar first. Two signals
are added up. Shared tags count, and count for more the rarer the tag is:
two posts tagged `sqlite` have more in common than two tagged `notes`. A
comparison of the words in titles and text catches the posts nobody tagged
properly. The default theme shows the result under each post as "Related
posts".

| Setting | Default | Meaning |
|---------|---------|---------|
| `limit` | `5` | How many related pages to keep. `0` turns the plugin off. |
| `min_score` | `0.1` | Pages less similar than this are not listed at all. |
| `tag_weight` | `1.0` | How much shared tags count. |
| `text_weight` | `0.5` | How much similar wording counts. `0` makes it tags only. |
| `taxonomies` | `["tags"]` | Which taxonomies are compared. |
| `sections` | `[]` | Only relate pages of these sections. Empty means all pages. |
| `same_section` | `false` | Only suggest pages from the page's own section. |

A page that has nothing in common with any other gets an empty list, and
the box does not appear. `related: false` in a page's front matter leaves
that page without suggestions.

### series

For posts that belong together in a fixed order. Name the series in each
post's front matter:

```yaml
series: Building inkstone
```

Every post in the series then gets `page.series`:

| Attribute | Value |
|-----------|-------|
| `name`, `title` | the name of the series |
| `pages` | all parts in reading order |
| `index`, `total` | which part this page is (from 1), and how many there are |
| `prev`, `next` | the neighbouring parts, or nothing at either end |
| `url` | the series' own page |

Parts are ordered by date, oldest first. To override that, give the posts a
`series_order` number in their front matter. Names are compared loosely, so
"Building Inkstone" and "building inkstone" are one series.

The default theme shows a box at the top of each part, "Part 2 of 7", with
all parts listed and the current one marked.

The plugin also writes an overview of all series at `/series/` and a page
per series at `/series/<name>/`.

| Setting | Default | Meaning |
|---------|---------|---------|
| `index` | `true` | Write the overview and the per-series pages. |
| `url` | `"/series/"` | Where they go. |
| `title` | `"Series"` | Title of the overview. |
| `template` | `"series.html"` | Template for those pages. If the theme has none, they are shown through `page.html`. It gets `all_series`, `series` and `pages`. |

### archives

Generates archive pages for everything that has a date: `/archive/` with
all years, `/archive/2024/` for a year and `/archive/2024/05/` for a month.

| Setting | Default | Meaning |
|---------|---------|---------|
| `url` | `"/archive/"` | Where the archive starts. |
| `title` | `"Archive"` | Its title. Year and month pages add theirs: "Archive: May 2024". |
| `yearly` | `true` | Write a page per year. |
| `monthly` | `true` | Write a page per month. |
| `sections` | `[]` | Only include pages of these sections. Empty means every dated page. |
| `template` | `"archive.html"` | Template for these pages. If the theme has none, the lists are shown through `page.html`. It gets `years`, `year`, `month` and `pages`. |

The example site links the archive from its footer menu.

### redirects

Writes a small HTML page at every address listed in a page's `aliases`,
which sends the visitor on to the page's current URL:

```yaml
aliases:
  - /blog/old-title/
  - /2019/old-title/
```

A static host cannot answer with a real HTTP redirect, so the page uses a
`<meta http-equiv="refresh">`, which browsers follow at once and search
engines treat as a move, plus a canonical link and one line of script that
carries a `#fragment` across.

For old addresses that have no page to put an alias on, there is a table
in the config. The target is a path on the site, a full URL, or the source
path of a page:

```toml
[plugin.redirects.map]
"/feed/" = "/rss.xml"
"/talks/" = "https://example.org/talks/"
"/old-about/" = "about.md"
```

| Setting | Default | Meaning |
|---------|---------|---------|
| `map` | `{}` | Old address to new address, as above. |
| `html` | `true` | Write the redirect pages. |
| `netlify` | `false` | Also write a `_redirects` file, for hosts that turn it into real redirects. |
| `status` | `301` | The status code used in that file: 301, 302, 307 or 308. |

An alias that is also the address of a real page is skipped with a warning;
the page wins.

### external_links

Adds attributes to links that leave your site, so you do not have to write
raw HTML to get them.

| Setting | Default | Meaning |
|---------|---------|---------|
| `rel` | `"noopener noreferrer"` | Values to add to the `rel` attribute. Add `nofollow` if you want it. |
| `target_blank` | `false` | Open outside links in a new tab. Adds `noopener` if `rel` lacks it. |
| `class` | `""` | A class to add, for marking outside links in CSS. |
| `scope` | `"content"` | `"content"` touches links in the text of pages. `"page"` also covers the ones the theme writes: menus, footer. |
| `internal` | `[]` | Other hosts to treat as your own, e.g. a second domain. |

A link counts as external when its host differs from the one in `base_url`;
`www.` is ignored in the comparison. `mailto:` and relative links are never
touched.

### image_dims

Reads the pixel size of local images and adds `width` and `height` to
their `<img>` tags, so the browser can reserve the space and the text does
not jump when the image arrives.

| Setting | Default | Meaning |
|---------|---------|---------|
| `lazy` | `true` | Add `loading="lazy"`. |
| `async` | `true` | Add `decoding="async"`. |
| `eager` | `0` | Leave the first this-many images of a page alone; they are probably on screen straight away, and loading those lazily only delays them. |

PNG, JPEG, GIF, WebP, AVIF, BMP and SVG are understood; the size is read
from the file header, nothing is decoded. Images on other hosts are left
alone, since looking at them would mean network requests during a build.

### footnote_previews

Attaches the text of each footnote to the number that refers to it: as a
`title`, so hovering shows the note even without JavaScript, and as a
`data-footnote-preview` attribute for scripts. The default theme's own
script shows a proper pop-up instead and takes the title away while it
does, so the two do not appear on top of each other.

| Setting | Default | Meaning |
|---------|---------|---------|
| `max_length` | `280` | Longer notes are cut at a word boundary. `0` keeps everything. |
| `title` | `true` | Set the `title` attribute. |
| `attribute` | `"data-footnote-preview"` | Name of the data attribute. |

### drafts_banner

When you build or serve with `--drafts`, puts a conspicuous banner at the
top of every draft page. It does nothing in a normal build, because there
are no draft pages in one.

| Setting | Default | Meaning |
|---------|---------|---------|
| `text` | `"Draft: not published"` | What the banner says. |
| `class` | `"draft-banner"` | Its CSS class. |
| `style` | a red bar | Inline style of the banner, so it shows whatever the theme does. Set to `""` when your own CSS styles the class. |

### git_dates

Fills in `updated` from the date of the last commit that touched the
page's source file, for pages that do not set `updated` themselves. It has
no settings. Without `git`, or outside a repository, it does nothing.

In CI, check out with full history (`fetch-depth: 0` in GitHub Actions).
With a shallow clone every file appears to have been changed by the latest
commit.

### minify

Minifies each HTML page as it is written. `build.minify = true` does the
same and also covers CSS and JS, so this plugin is for the case where you
want small HTML but untouched assets; with the build option on, it steps
aside.

| Setting | Default | Meaning |
|---------|---------|---------|
| `remove_comments` | `true` | Drop HTML comments. |
| `collapse_whitespace` | `true` | Squeeze runs of whitespace between tags. |
| `remove_attribute_quotes` | `false` | Write `class=post` where that is valid. Saves a little, reads worse. |
| `inline_css`, `inline_js` | `true` | Also minify `<style>` and `<script>` blocks. |

## Writing a plugin

A plugin is a subclass of `inkstone.plugins.Plugin` in a module that
inkstone can find. For a site-local plugin that means `plugins/<name>.py`.

```python
# plugins/hello.py
from inkstone.plugins import Plugin


class Hello(Plugin):
    name = "hello"

    def build_finished(self, site, report):
        print(f"hello: built {len(site.pages)} pages")
```

```toml
plugins = ["shortcodes", "toc", "reading_time", "hello"]
```

That is a complete plugin. The module has to contain exactly one `Plugin`
subclass, or name the one to use in a module-level variable called
`plugin`.

The base class gives you two attributes:

| Attribute | What it is |
|-----------|-----------|
| `self.config` | the site configuration |
| `self.settings` | your `[plugin.<name>]` table as a dict; empty if there is none |

Read settings with a default, so the plugin works without configuration:
`self.settings.get("limit", 5)`.

### Hooks

Every hook is optional. Implement the ones you need.

| Hook | Called | Return |
|------|--------|--------|
| `setup(self, builder)` | once, when the template environment exists | nothing. Register filters and globals here: `builder.env.filters["name"] = func`, `builder.env.globals["name"] = value` |
| `content_loaded(self, site)` | after all sources are parsed, before anything is rendered | nothing. Add, remove or change pages; attach data to them |
| `page_markdown(self, page, text)` | for each page, before Markdown is parsed | the Markdown text, changed or not |
| `page_html(self, page, html)` | for each page, after Markdown is rendered | the content HTML |
| `generate_pages(self, site)` | once, after all content is rendered | an iterable of extra pages (`Page.virtual(...)`) |
| `template_context(self, page, context)` | for each page, before its template renders | nothing. Mutate the `context` dict |
| `page_output(self, page, html)` | for each page, on the complete HTML document | the document |
| `extra_files(self, site)` | once, near the end | an iterable of `(output_path, text_or_bytes)` |
| `build_finished(self, site, report)` | last | nothing |

The three text hooks (`page_markdown`, `page_html`, `page_output`) are
pipelines: each plugin gets what the previous one returned. You *must*
return the text, even when you did not change it. Forgetting the `return`
is the most common plugin bug. inkstone notices the `None`, keeps the text
as it was and logs a warning that names your plugin, so the page survives
but your change is quietly missing.

Which hook to use:

| You want to | Use |
|-------------|-----|
| add your own syntax to Markdown | `page_markdown` |
| post-process rendered content (links, images) | `page_html` |
| compute something from all pages (related posts, a tag cloud) | `content_loaded` |
| add pages that have no source file | `generate_pages` |
| give templates a new variable, function or filter | `template_context`, `setup` |
| change the final document (inject a tag, minify) | `page_output` |
| write a file that is not a page (`_redirects`, a JSON dump) | `extra_files` |
| run something afterwards (ping a service, print a summary) | `build_finished` |

`setup` receives the `Builder`, which gives access to everything:
`builder.config`, `builder.site`, `builder.env` (the template environment)
and `builder.render_markdown(text)` for turning a piece of Markdown into
HTML with the site's settings.

### Making pages

`generate_pages` returns pages built with `Page.virtual`:

```python
Page.virtual(
    "/archive/",            # the URL; decides the output path
    title="Archive",
    template="archive.html",
    posts=site.pages,       # extra keyword arguments become template variables
)
```

With `template=None` the page's `content` is written to the file as it is,
without going through a template. That is how a redirect page or a
hand-built XML file is made.

### Errors

If a hook raises, the build stops with a `PluginError` that names the
plugin and the hook, with your exception as its cause. Run with `--debug`
to see the full traceback. To fail on purpose with a readable message,
raise `inkstone.errors.PluginError("what went wrong")` yourself.

To warn without failing, append to `report.warnings` in `build_finished`,
or simply print; plugin output shows up in the build log.

### A worked example

A plugin that keeps writing statistics: how many words the site has, per
year. It adds a `stats` variable for templates, a `thousands` filter,
writes `stats.json`, and prints a line at the end. Five hooks, about forty
lines.

```python
# plugins/wordstats.py
import json
from collections import Counter

from inkstone.plugins import Plugin


class WordStats(Plugin):
    name = "wordstats"

    def setup(self, builder):
        # {{ stats.total | thousands }} -> "48,210"
        builder.env.filters["thousands"] = lambda number: f"{number:,}"

    def content_loaded(self, site):
        skip = set(self.settings.get("skip_sections", []))
        self.by_year = Counter()
        for page in site.pages:
            if page.date is None or page.draft:
                continue
            if page.section is not None and page.section.name in skip:
                continue
            self.by_year[page.date.year] += page.word_count
        self.total = sum(self.by_year.values())

    def template_context(self, page, context):
        context["stats"] = {
            "total": self.total,
            "by_year": sorted(self.by_year.items(), reverse=True),
        }

    def extra_files(self, site):
        payload = {"total": self.total, "by_year": dict(self.by_year)}
        yield "stats.json", json.dumps(payload, indent=2, sort_keys=True)

    def build_finished(self, site, report):
        print(f"wordstats: {self.total:,} words in {len(site.pages)} pages")
```

Enable and configure it:

```toml
plugins = ["shortcodes", "toc", "reading_time", "wordstats"]

[plugin.wordstats]
skip_sections = ["projects"]
```

And use it in a template, say an override of `partials/footer.html`:

```html
<p>
  {{ stats.total | thousands }} words so far.
  {% for year, words in stats.by_year %}
    {{ year }}: {{ words | thousands }}{% if not loop.last %}, {% endif %}
  {% endfor %}
</p>
```

Things this example does on purpose:

- It is listed *after* `reading_time`, since it reads `page.word_count`.
  Order in the `plugins` list is how plugins depend on each other.
- It computes once, in `content_loaded`, and only hands out the result in
  `template_context`. That hook runs for every page; keep it cheap.
- `extra_files` yields a path relative to the output directory and a
  string. inkstone does the writing, and removes the file again if a later
  build stops producing it.
- Settings are read with `.get` and a default.

One caveat about incremental builds: the cache does not know that your
plugin's output depends on other pages. If `stats` appears in the footer
of every page, a page that was skipped as unchanged keeps the old number
until something else causes it to re-render. For values like this, that is
usually fine. When it is not, build with `--no-incremental` for the deploy.

### Testing a plugin

A plugin is plain Python, so test it like any other:

```python
from datetime import date
from types import SimpleNamespace

from plugins.wordstats import WordStats


def test_counts_words_per_year():
    plugin = WordStats(config=None, settings={})
    page = SimpleNamespace(date=date(2024, 5, 3), draft=False, section=None, word_count=120)
    plugin.content_loaded(SimpleNamespace(pages=[page, page]))
    assert plugin.total == 240
```

For anything that needs a real build, point `load_config` at a small
fixture site, run `Builder(config).build()`, and look at the files.

### Sharing a plugin

A plugin that is useful beyond one site can live in a package of its own.
List it by module path:

```toml
plugins = ["shortcodes", "toc", "reading_time", "inkstone_wordstats.plugin"]
```

The settings table is still named after the plugin's `name` attribute:
`[plugin.wordstats]`.
