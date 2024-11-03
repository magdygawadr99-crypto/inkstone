# Deploying

`inkstone build` leaves a directory of plain files in `public/`. Deploying
means putting that directory somewhere a web server can see it. There is no
inkstone-specific step on the server, no runtime, nothing to keep running.

## The build you publish

Locally you run `inkstone serve`. For publishing, build with the production
settings and the real address:

```
inkstone build --clean --minify --fingerprint --base-url https://example.com/
```

| Flag | Why |
|------|-----|
| `--clean` | Start from an empty output directory, so nothing stale from a local experiment ships. |
| `--minify` | Smaller HTML, CSS and JS. |
| `--fingerprint` | Hashed asset names, so you can cache them hard (see [Caching](#caching)). |
| `--base-url` | Canonical links, feeds and the sitemap need the public address. |

If `base_url`, `build.minify` and `build.fingerprint` are already set in
`inkstone.toml`, plain `inkstone build --clean` does the same. I keep
`base_url` in the config and pass the two build flags from the deploy
script, so that local builds stay readable.

Two things to check before the first deploy:

```
inkstone check --strict     # broken links, missing images, duplicate URLs
inkstone list --drafts      # what a careless --drafts would publish
```

Never put `--drafts` or `--future` in a deploy command. It sounds obvious.
I have done it.

## Any server, with rsync

The whole deploy script for my own site:

```bash
#!/usr/bin/env bash
set -euo pipefail

inkstone check --strict
inkstone build --clean --minify --fingerprint
rsync -az --delete --checksum public/ deploy@example.com:/var/www/example.com/
```

`--delete` removes files on the server that are no longer in the build,
which matters when you rename or unpublish a page. `--checksum` compares
content instead of timestamps, so the pages inkstone rewrote without
changing are not uploaded again.

The trailing slash on `public/` is significant: with it rsync copies the
*contents* of the directory, without it you get a `public` directory
inside your web root.

A minimal nginx site to go with it:

```nginx
server {
    listen 443 ssl;
    server_name example.com;
    root /var/www/example.com;

    index index.html;
    error_page 404 /404.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # fingerprinted files never change under the same name
    location ~* \.[0-9a-f]{8}\.(css|js|svg|png|jpg|woff2)$ {
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml
               application/xml application/rss+xml application/atom+xml;
}
```

The `error_page` line is what makes the generated `404.html` show up. A
static file server does not know about it unless told.

## GitHub Pages

Build in GitHub Actions and publish the output as a Pages artifact. In the
repository settings, under *Pages*, set the source to *GitHub Actions*,
then add `.github/workflows/pages.yml`:

```yaml
name: Deploy site

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install inkstone
        run: pip install git+https://github.com/magdygawadr99-crypto/inkstone
      - name: Build
        run: |
          inkstone check --strict
          inkstone build --clean --minify --fingerprint
        env:
          INKSTONE_BASE_URL: https://USER.github.io/REPO/
      - uses: actions/upload-pages-artifact@v3
        with:
          path: public

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Replace `USER` and `REPO`. A project site lives under `/REPO/`, which makes
it a site in a sub-directory; see [below](#sites-in-a-sub-directory). For
a user site (`USER.github.io`) or a custom domain the base URL has no path
and there is nothing special to do.

GitHub Pages serves `404.html` from the site root for missing pages on its
own.

inkstone has no dependencies, so the install step is the only setup. There
is nothing to cache between runs except `.inkstone-cache/`, and for a site
that builds in two seconds that is not worth the YAML.

## Netlify

Add a `netlify.toml` next to `inkstone.toml`:

```toml
[build]
command = "pip install git+https://github.com/magdygawadr99-crypto/inkstone && inkstone build --clean --minify --fingerprint"
publish = "public"

[build.environment]
PYTHON_VERSION = "3.12"

[context.production.environment]
INKSTONE_BASE_URL = "https://example.com/"

# Deploy previews get their own address; DEPLOY_PRIME_URL has no trailing
# slash, hence the one added here.
[context.deploy-preview]
command = "pip install git+https://github.com/magdygawadr99-crypto/inkstone && inkstone build --clean --drafts --base-url $DEPLOY_PRIME_URL/"

[[headers]]
for = "/css/*"
[headers.values]
Cache-Control = "public, max-age=31536000, immutable"

[[headers]]
for = "/js/*"
[headers.values]
Cache-Control = "public, max-age=31536000, immutable"
```

The preview context is the one place I think `--drafts` is useful in an
automated build: open a pull request with a draft post, and the preview
shows it with the draft marker, at an address you can send to someone.

Netlify picks up `404.html` automatically. Cloudflare Pages and similar
hosts work the same way: build command, output directory `public`,
`INKSTONE_BASE_URL` in the environment.

## Sites in a sub-directory

If the site is not at the root of its host (a GitHub project site, or
`https://example.com/blog/`), put the path in `base_url`:

```toml
base_url = "https://example.com/blog/"
```

That is the only setting. What it changes:

- `url_for("/about/")` gives `/blog/about/`, and so does every link the
  themes generate.
- `asset("css/main.css")` gives `/blog/css/main.css`.
- Permalinks, feeds and the sitemap use the full address.
- The search box asks for `/blog/search-index.json`.

What it does not change: the files in `public/`. `about/index.html` is
still at the top of the output directory. You upload the *contents* of
`public/` into the `blog/` directory on the server.

What can still go wrong is links you wrote by hand:

| Where | Problem | Fix |
|-------|---------|-----|
| Your own templates | `href="/about/"` | `href="{{ url_for('/about/') }}"` |
| Your own CSS | `url(/img/bg.png)` | a relative `url(../img/bg.png)` |
| Markdown | `[about](/about/)` | Content does not go through `url_for`; a link is written into the page as you typed it. On a sub-path site write such links relative to the page (`../about/`) or with the prefix. |
| `[[menus.main]]` | `url = "/posts/"` | nothing to do; the theme passes these through `url_for` |

The last-but-one row is the reason I would rather give a blog its own
(sub)domain than a sub-directory, when there is a choice.

`inkstone serve` replaces `base_url` with its own address and serves at
`/`, so a sub-path problem will not show up locally. To rehearse it:

```
inkstone build --base-url http://localhost:8000/blog/ --output /tmp/site/blog
python -m http.server 8000 --directory /tmp/site
```

and browse to `http://localhost:8000/blog/`.

## Caching

With `--fingerprint`, every static file gets a hash of its content in its
name, and the HTML refers to that name. A changed file is a new URL, so the
old one can be cached for a year. HTML pages keep their names and should
be revalidated:

| Files | Suggested `Cache-Control` |
|-------|---------------------------|
| `*.html`, feeds, `sitemap.xml`, `search-index.json` | `no-cache` (revalidate every time; cheap, since nothing changed) |
| fingerprinted CSS, JS, images | `public, max-age=31536000, immutable` |
| everything else | `public, max-age=3600` |

Without fingerprinting, do not cache CSS and JS for long, or readers will
see new HTML with old styles after an update.

## Redirects

Moved a page? Put its old address in the front matter and enable the
`redirects` plugin:

```yaml
aliases:
  - /blog/old-title/
```

The plugin writes a small HTML page at the old address that forwards to
the new one. That works on any host. If your host supports real redirects
(nginx `return 301`, a Netlify `_redirects` file), those are better for
search engines, and you can generate the file from a
[plugin of your own](plugins.md#writing-a-plugin) using `page.aliases`.

## Checklist for the first deploy

- [ ] `base_url` is the public address, with `https://` and a trailing slash
- [ ] `inkstone check --strict` passes
- [ ] no `--drafts` in the deploy command
- [ ] the server knows about `404.html`
- [ ] the server gzips HTML, CSS, JS, JSON and XML
- [ ] the feed URL (`/rss.xml`) loads and validates
- [ ] `robots.txt` and `sitemap.xml` are there and point at the right host
