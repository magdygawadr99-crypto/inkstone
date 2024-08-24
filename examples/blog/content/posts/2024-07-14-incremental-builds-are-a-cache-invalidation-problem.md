+++
title = "Incremental builds are a cache invalidation problem"
description = "Rebuilding one page is easy. Knowing which page to rebuild is the whole job."
tags = ["inkstone", "python", "caching", "performance"]
categories = ["inkstone"]
series = "Building inkstone"
updated = 2024-07-20
+++

A full build of this site takes a little under two seconds. That is fine
for publishing and annoying for writing: save, wait, look, save, wait, look.
I wanted a save to cost about as long as a blink.

<!-- more -->

(Yes, this post has TOML front matter. I added support last week and
something has to exercise it.)

## The easy version, and why it is wrong

Compare modification times: if `hello.md` is newer than
`hello/index.html`, rebuild it. `make` has done this since 1976.

It is wrong for a site because a page's output depends on far more than its
source file:

- [x] the Markdown source and its front matter
- [x] the template it uses, and whatever *that* extends or includes
- [x] the site config (change `title` and every page's `<title>` changes)
- [x] the version of inkstone itself
- [x] for list pages: the title, date, summary and tags of every member
- [ ] data files, only if the template reads them (not tracked yet, see below)

Change `base.html` and every output is stale while no Markdown file has been
touched. Timestamps cannot see that.

## A key per output file

So the cache does not store *when* something was built. It stores *what went
into it*: for every output file, a hash over all its inputs.

```python
def page_key(page: Page, template: Template, env_hash: str) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(env_hash.encode())               # config + inkstone version
    h.update(page.raw.encode())
    h.update(repr(sorted(page.meta.items())).encode())
    for name in sorted(template.all_dependencies() | {template.name}):
        h.update(name.encode())
        h.update(template_digest(name))
    return h.hexdigest()
```

On the next build, compute the key again. Same key and the file still
exists: skip it. Anything else: render.

`template.all_dependencies()` is the reason I am glad I wrote the template
engine myself. It walks `extends`, `include` and `import` and tells me every
template file a page can possibly touch, before rendering.

## List pages are the hard part

The front page shows the six newest posts. Its inputs are those six posts,
but only parts of them: title, URL, date, summary, tags. If I fix a typo
in the *body* of a post, below the `<!-- more -->` marker, the front page
has not changed and should not be rebuilt.

So each page has two digests: one of everything, and one of just the
metadata a list could show. A list page's key is built from the second kind.

| What changed                    | Pages rendered | Time    |
|---------------------------------|---------------:|--------:|
| Nothing                         |              0 | 0.11 s  |
| Body of one post                |              1 | 0.14 s  |
| Title of one post               |              9 | 0.21 s  |
| `partials/footer.html`          |            all | 1.74 s  |
| `inkstone.toml`                 |            all | 1.78 s  |
| Clean build, cold cache         |            all | 1.90 s  |

(87 output files, on a five-year-old laptop. The 0.11 s for "nothing" is
almost all reading and hashing the sources; parsing is skipped.)

## Deleting things

The bug that took longest to notice: rename a post, and the old URL keeps
working forever, because nothing ever removes
`public/2024/07/old-name/index.html`. The cache now remembers every file a
build wrote, and anything in the previous list that is not in the new one
gets deleted, along with directories that end up empty.

It only deletes files it wrote itself. I learned to be careful about that
after pointing `output_dir` at the wrong folder once. Once.

## What is still not tracked

!!! warning
    Data files. If a template reads `site.data.projects` and I edit
    `data/projects.json`, the cache does not know which pages used it, so
    for now *any* change under `data/` rebuilds everything. Correct, just
    not clever.

Same for templates whose name is computed at render time,
`{% include page.params.sidebar %}` and the like. The static dependency list
cannot see those. The honest fix is to record what a render actually loaded.
It is on the list.

**Update, 20 July:** `inkstone build --no-incremental` now exists, for the
day I stop trusting any of the above.
