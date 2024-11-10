# Internals

This is for reading the code, writing a plugin that does something unusual,
or satisfying curiosity. You do not need any of it to use inkstone.

The short version: a build loads everything into memory as plain Python
objects, renders Markdown, renders templates, and writes files. There is no
database, no daemon and no global state; a `Builder` object holds a build
and goes away afterwards.

## Package map

```
inkstone/
  config.py        load, merge and validate the configuration
  errors.py        InkstoneError and its subclasses
  frontmatter.py   split and parse YAML / TOML / JSON front matter
  datafiles.py     load the data/ directory
  tomlw.py         write TOML (the standard library can only read it)

  markdown/        block parser, inline parser, HTML and plain-text renderers
  tmpl/            template lexer, parser, interpreter, filters, loaders
  highlight/       regex lexers, the HTML formatter, styles
  yamlite/         the subset of YAML that front matter and data files need

  content/         Page, Section, Site, taxonomies, pagination; load_site()
  build/           the Builder, the incremental cache, the link checker
  assets/          CSS/JS/HTML minifiers, fingerprinting, image sizes
  feeds/           RSS, Atom, JSON Feed, sitemap, robots.txt
  search/          index builder, query parser, and the browser client
  server/          dev server: HTTP, WebSocket, file watcher, error overlay
  plugins/         the plugin manager and the built-in plugins
  cli/             the `inkstone` command
  scaffold/        files that `inkstone new site` writes
  themes/          the built-in themes: default and paper
  utils/           text, dates, paths, file system, glob, terminal, timing
```

The layering is strict in one direction. The packages in the second group
(`markdown`, `tmpl`, `highlight`, `yamlite`) know nothing about sites or
pages and import nothing from the third group. Each of them is usable on
its own:

```python
from inkstone.markdown import render
from inkstone.tmpl import Environment, DictLoader
from inkstone.highlight import highlight

html = render("# Title\n\nSome *text*.")
env = Environment(loader=DictLoader({"t.html": "Hello {{ name }}"}))
print(env.get_template("t.html").render(name="world"))
```

`content`, `build` and `plugins` are the site layer and tie the rest
together. `cli` and `server` sit on top and only talk to the builder.

## The objects

Config
:   What `load_config(root)` returns. Behaves like nested dictionaries with
    attribute access (`cfg.build.minify`, `cfg.get("build.minify")`) and
    knows the absolute paths of the site's directories.

Page
:   One output document: a Markdown file, or something generated (a list
    page, a tag page, a redirect). The attributes are listed in
    [Templates](templates.md#page). A page made without a source file is
    created with `Page.virtual(url, title=..., template=..., content=...)`.

Section
:   A directory of pages, with its own sort order and optional pagination.

Site
:   Everything: `pages`, `sections`, `taxonomies`, `data`, `menus`.
    `load_site(config)` builds one by parsing all sources. It renders
    nothing; after it returns, `page.raw` holds Markdown and `page.content`
    is still empty.

Builder
:   Owns one build. It has the config, the site, the template environment
    (`builder.env`), the plugin manager (`builder.plugins`) and the asset
    pipeline (`builder.assets`). `builder.build()` returns a `BuildReport`.

## How a build runs

`inkstone build` creates a `Builder` and calls `build()`. The phases, in
order:

| # | Phase | What happens | Plugin hooks |
|--:|-------|--------------|--------------|
| 1 | setup | Load the cache, create the template environment with the search path (site, theme, parent themes), register globals and filters. | `setup` |
| 2 | load | `load_site`: walk `content/`, parse front matter, build pages, sections and taxonomies, load `data/`. Drafts and future pages are dropped here. | `content_loaded` |
| 3 | markdown | For every page: Markdown to HTML, summary, table of contents, word count. | `page_markdown`, `page_html` |
| 4 | generate | Plugins contribute extra pages (archives, redirects). | `generate_pages` |
| 5 | lists | Create the taxonomy, term, section and home pages, split into paginated pages. | |
| 6 | assets | Copy `static/` of the theme chain and of the site through the asset pipeline: minify, fingerprint. The generated `css/highlight.css` and `js/inkstone-search.js` go the same way. This has to happen before rendering because `asset()` needs the final file names. | |
| 7 | templates | Pick a template for each page, build its context, render. | `template_context`, `page_output` |
| 8 | write | Write the HTML files. A file whose bytes would not change is left alone, so modification times stay meaningful for rsync and friends. | |
| 9 | extras | Feeds, `sitemap.xml`, `robots.txt`, `search-index.json`, `404.html`. | `extra_files` |
| 10 | cleanup | Delete output files that the previous build wrote and this one did not. Save the cache. | `build_finished` |

`inkstone build --profile` prints how long each phase took. On my sites
the Markdown phase dominates a clean build by a wide margin; templates and
everything else are small change.

The `BuildReport` that comes back has `pages_written`, `pages_skipped`,
`assets_copied`, `files_removed`, `warnings`, `duration`, the per-phase
times in `phases`, and `output_paths`. `report.summary()` is the line the
CLI prints.

### Why Markdown is rendered before lists exist

List pages show summaries, and summaries are rendered Markdown. So all
content is rendered first (phase 3), and only then do the pages that list
other pages get created (phase 5). The same ordering lets a plugin compute
things from finished HTML, such as related posts or reading time, before
any template runs.

### Template selection

For each page the builder makes a list of candidate template names from
the page's kind and section (the table in
[Templates](templates.md#which-template-renders-a-page)) and asks the
template environment for the first one that exists. The environment's
loader searches the site's `templates/`, then the theme, then the theme's
parents. That one mechanism is all there is to "overriding" and to theme
inheritance.

## The incremental cache

A clean build renders everything. Every build after that tries to render
as little as possible, and the hard part is knowing what "as little as
possible" is.

The cache lives in `.inkstone-cache/`. For every output file it stores a
**key**: a hash of everything that went into that file.

For a regular page the key covers:

- the Markdown source and the front matter,
- the template that renders it and every template that one extends,
  includes or imports, transitively (`Template.all_dependencies()`),
- a hash of the configuration,
- the inkstone version.

On the next build the key is computed again from the current inputs. If it
matches and the output file still exists, the page is skipped: no
Markdown parsing, no template rendering, no write. Otherwise it is
rendered.

Consequences worth knowing:

| You change | What is rebuilt |
|------------|-----------------|
| the body of one post | that post |
| the title, date, tags or summary of a post | that post, and every list page it appears on |
| a partial template | every page whose template pulls it in |
| `base.html` | everything |
| `inkstone.toml` | everything |
| a file in `static/` | that file goes through the asset pipeline again |
| inkstone itself (an upgrade) | everything |

List pages (home, sections, tags) have a key built from the *metadata* of
their members: title, URL, date, summary, tags. That is why fixing a typo
deep in a post does not re-render the front page, while changing its title
does.

Two honest limitations:

- Template names that are computed at render time
  (`{% include page.params.sidebar %}`) are invisible to the static
  dependency scan. A change to such a template is not noticed. Avoid
  computed includes, or build with `--no-incremental` when you change one.
- Data files are not tracked per page. A change anywhere under `data/`
  invalidates everything, which is correct but not clever.

Outputs are tracked too. The cache remembers which files the last build
wrote, and anything in that list that the current build did not produce is
deleted, along with directories left empty. Only files inkstone wrote
itself are ever removed; a file you dropped into `public/` by hand stays.

When in doubt:

```
inkstone build --no-incremental     # ignore the cache for this run
inkstone build --clean              # delete output and cache first
inkstone clean                      # just delete them
```

If a `--clean` build gives a different result than an incremental one,
that is a bug in the cache, and I want to know about it.

## The dev server

`inkstone serve` is the builder plus three threads:

- an HTTP server for `public/`, which injects a small script before
  `</body>` in the HTML it sends (the files on disk are never modified),
- a file watcher that polls the source directories, waits for changes to
  settle for a moment, and hands the list of changed paths to
  `builder.build(changed=...)`,
- a WebSocket endpoint that tells open browser tabs what happened.

After a successful rebuild the browser gets one of two messages: *reload*,
or, when only stylesheets changed, *css* with the affected paths, in which
case the script swaps the `<link>` tags and the page keeps its scroll
position. After a failed rebuild it gets the error, and shows it as an
overlay until the next good build.

The WebSocket implementation is in `server/websocket.py`. It exists
because the standard library has none, and it implements just enough of
RFC 6455 for this job.

## Errors

Everything inkstone raises on purpose derives from `InkstoneError`:

| Exception | Raised for |
|-----------|-----------|
| `ConfigError` | unreadable or invalid configuration |
| `ContentError` | bad front matter, unparseable dates, duplicate URLs, broken data files |
| `BuildError` | problems while rendering or writing |
| `PluginError` | an exception inside a plugin hook; names the plugin and the hook |

The CLI prints these as one line and exits with status 1. Anything else is
a bug in inkstone and prints a traceback. `--debug` prints the traceback
for the first kind as well.

## Tests

```
pip install -e ".[dev]"
python -m pytest
```

The tests mirror the package layout: `tests/markdown/`, `tests/tmpl/`,
`tests/build/` and so on, one directory per package. Two of them do
something less obvious:

- `tests/search/` feeds the same documents to the Python index and, when
  `node` is installed, to the JavaScript client, and compares results. The
  two implementations have to agree or search silently finds nothing.
- `tests/themes/` checks the built-in themes, the example site and these
  docs without building anything: balanced template tags, includes that
  resolve, `asset()` paths that exist, links between the documentation
  pages, and a render of every page template against stand-in data shaped
  like the content model.

Everything is meant to pass on Linux, macOS and Windows. Paths are the usual reason
something fails on only one of them; inside inkstone every relative path
is a POSIX-style string, and it is converted to a real path only at the
point where a file is read or written.

## Conventions

If you send a patch: standard library only at runtime, `black` formatting,
type hints on public functions, and a test. Comments say why, not what.
The code is meant to be read from top to bottom by one person, so prefer a
slightly longer function to a clever abstraction.
