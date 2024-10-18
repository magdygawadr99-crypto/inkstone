# Getting started

This walks through installing inkstone, making a site, writing a post and
publishing the result. It takes about ten minutes, most of which is you
deciding on a title.

## Install

You need Python 3.10 or newer. If your config file is going to be TOML (the
default, and what this guide uses) you need 3.11, because that is when
`tomllib` arrived in the standard library. On 3.10 use `inkstone.yaml` or
`inkstone.json` instead; everything else is the same.

```
git clone https://github.com/magdygawadr99-crypto/inkstone
cd inkstone
pip install -e .
```

There is nothing else to install. inkstone has no runtime dependencies, so a
virtualenv is optional; I use one anyway out of habit.

Check that it worked:

```
$ inkstone version
inkstone 0.6.2
```

## Make a site

```
inkstone new site myblog
cd myblog
```

That creates a small working site. The parts that matter:

```
myblog/
  inkstone.toml       the configuration
  content/
    _index.md         the home page
    posts/            a section; every Markdown file in it is a post
  static/             files copied to the output as they are
  templates/          your overrides of theme templates go here
```

Pass `--title "My blog"` to fill in the title, and `--theme paper` to start
with the plainer of the two built-in themes. `inkstone new site` refuses to
write into a directory that already has things in it unless you add `--force`.

A site can have three more directories: `data/`, `themes/` and `plugins/`.
Most sites never need them, and inkstone only looks at them if they exist.
What each one is for is covered in [Content](content.md),
[Templates](templates.md) and [Plugins](plugins.md).

## Look at it

```
inkstone serve
```

Open <http://127.0.0.1:8000/>. The server builds the site into `public/`,
serves it, and watches the source directories. When you save a file it
rebuilds what changed and the browser reloads on its own. If the only thing
that changed is a stylesheet, the page is not reloaded at all; the new CSS is
swapped in place.

When a build fails (a typo in a template, bad front matter) the error shows
up in the browser as an overlay with the file and line, and goes away again
once you fix it. The server keeps running either way.

Useful flags:

| Flag | What it does |
|------|--------------|
| `--port 8080` | listen somewhere else |
| `--host 0.0.0.0` | accept connections from other machines, e.g. your phone |
| `--drafts` | include pages marked `draft: true` |
| `--future` | include pages dated in the future |
| `--open` | open the browser for you |
| `--no-livereload` | serve and rebuild, but leave the browser alone |

While serving, `base_url` is replaced by the address of the dev server, so
absolute links in feeds and `<link rel="canonical">` point at localhost.
Nothing you do in `serve` changes what `build` produces later.

## Write a post

```
inkstone new post "Hello world"
```

This creates a file in `content/posts/`, named after today's date and the
title (`2024-05-03-hello-world.md`), and prints its path. It starts with a
few lines between `---` markers. That is the *front matter*: metadata about
the page. Everything after it is Markdown. Write something:

```markdown
---
title: Hello world
date: 2024-05-03
tags: [meta]
---

The first paragraph doubles as the summary on list pages.

<!-- more -->

Everything below the marker only shows on the page itself.
```

Save, and the browser shows the post at `/2024/05/hello-world/`. The front
page lists it, `/tags/meta/` exists, and the RSS feed has an entry.

Other things `new post` can do:

```
inkstone new post "Half an idea" --draft
inkstone new post "Trip report" --tags travel,photos --date 2024-06-01
inkstone new post "Changelog for 1.2" --section notes --slug changelog-1-2
```

For a page that is not a post, `inkstone new page projects/widget.md`
creates `content/projects/widget.md` with a title filled in.

All front matter keys, how dates and URLs are worked out, drafts, sections
and page bundles are described in [Content](content.md). What Markdown
syntax is understood is in the [Markdown reference](markdown.md).

## Configure it

Open `inkstone.toml`. The three things to set first:

```toml
title = "My blog"
base_url = "https://example.com/"

[author]
name = "Your Name"
```

`base_url` is where the site is going to live, with the trailing slash. It
does not matter while you work locally, because `inkstone serve` uses its
own address. Two more things most people want early are a menu and a
couple of theme settings:

```toml
[[menus.main]]
name = "Posts"
url = "/posts/"
weight = 10

[[menus.main]]
name = "About"
url = "/about/"
weight = 20

[params]
accent = "#0b6e4f"
accent_dark = "#7bd3b0"
```

To see what else there is:

```
inkstone config --defaults     # every option with its default
inkstone config                # what this site ends up with
inkstone config build.minify   # one value
```

[Configuration](configuration.md) explains each key.

## Check and build

Before publishing, let inkstone look for the mistakes that are easy to make
and hard to see:

```
inkstone check
```

It reports internal links that point nowhere, images that do not exist,
front matter problems and two pages that would be written to the same URL.
Add `--external` to also request every outside link (slow, and some sites
dislike it), and `--strict` to make warnings count as failures, which is
what you want in CI.

Then build:

```
inkstone build --minify --fingerprint --base-url https://example.com/
```

The result is in `public/`. It is a plain directory of files; any web server
can serve it. `--minify` strips whitespace from HTML, CSS and JS, and
`--fingerprint` puts a content hash into the names of static files
(`main.3f9a1c2e.css`) so they can be cached forever. If you set these in
`inkstone.toml` under `[build]` you can leave the flags off.

Builds are incremental: the second run only renders pages whose inputs
changed. If you ever suspect the cache, `inkstone build --clean` starts from
nothing.

[Deploying](deploying.md) has recipes for GitHub Pages, Netlify and a plain
server with rsync.

## The commands

```
inkstone new site PATH [--theme NAME] [--title T] [--force]
inkstone new post TITLE [--section S] [--draft] [--date D] [--slug S] [--tags a,b]
inkstone new page PATH
inkstone build [--drafts] [--future] [--output DIR] [--base-url URL] [--clean]
               [--no-incremental] [--minify] [--fingerprint] [--profile]
inkstone serve [--host H] [--port N] [--no-livereload] [--open] [--drafts] [--future]
inkstone check [--external] [--strict]
inkstone list [--section S] [--tag T] [--drafts] [--format table|json|paths] [--sort date|title]
inkstone config [--json] [--defaults] [KEY]
inkstone highlight-css [--style NAME] [--selector .highlight]
inkstone clean
inkstone version
```

Options that work with every command go before the command name:

| Option | Meaning |
|--------|---------|
| `-C DIR`, `--root DIR` | the site to work on; without it inkstone walks up from the current directory until it finds a config file |
| `-c FILE`, `--config FILE` | use this config file instead of `inkstone.toml` |
| `-q`, `--quiet` | only print warnings and errors |
| `-v`, `--verbose` | say what is being done, file by file |
| `--debug` | print a traceback when something fails, instead of the one-line message |
| `--no-color` | plain output; also the default when stdout is not a terminal |

So `inkstone -C examples/blog serve` serves the example site from the
repository root without changing directory.

## A complete example

The repository has a finished small blog in
[`examples/blog`](../examples/blog). It uses most features at least once:
a menu, tags, a section sorted by weight, a page bundle, data files, a
template override, shortcodes and several plugins. When this documentation
is unclear, that directory is the tie-breaker.

## Where next

- [Content](content.md): front matter, sections, bundles, drafts
- [Markdown](markdown.md): the syntax, with examples
- [Templates](templates.md): changing how pages look
- [Configuration](configuration.md): every setting
- [Plugins](plugins.md): the built-in ones and writing your own
- [Search](search.md): how the client-side search works
- [Deploying](deploying.md): getting `public/` onto the internet
- [Internals](internals.md): how a build runs, if you want to read the code
- [FAQ](faq.md)
