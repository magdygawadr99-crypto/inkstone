---
title: Moving the blog over
description: The site you are reading is now built by inkstone. What the switch involved, in numbers.
tags: [inkstone, meta, migration]
categories: [inkstone]
aliases:
  - /blog/moving-the-blog-over/
  - /2024/11/switched/
updated: 2024-11-19
---

As of Friday night, this site is built by the thing I have been writing
about since April. If you are reading this in a feed reader and every post
just showed up as new: sorry. That was me, and it is on the list below.

<!-- more -->

## The move

The content was the easy part, since it was Markdown with YAML front matter
before and it is Markdown with YAML front matter now. A script did most
of it:

```python
for old in sorted(Path("old/content").glob("*.md")):
    meta, body = frontmatter.parse(old.read_text(encoding="utf-8"))
    meta.pop("Status", None)
    meta["tags"] = [t.strip().lower() for t in meta.pop("Tags", "").split(",") if t]
    day = parse_date(meta.pop("Date")).date()
    new = Path("content/posts") / f"{day.isoformat()}-{meta.pop('Slug')}.md"
    new.write_text(frontmatter.dumps(meta, body), encoding="utf-8")
```

Then the things a script cannot do:

1. Read every post in the browser, once, in both colour schemes.
2. Fix the eleven posts that used raw HTML tables because the old setup
   had no table syntax when I wrote them.
3. Decide which old posts were not coming along. (Most of 2016.)

## URLs

Cool URIs don't change, and mine did: the old site put posts at
`/blog/some-title/`, the new one at `/2024/11/some-title/`. Every moved
post has an `aliases` entry in its front matter, and the `redirects` plugin
writes a tiny HTML page at each old address that points to the new one.

```yaml
aliases:
  - /blog/moving-the-blog-over/
```

It is a `<meta http-equiv="refresh">`, not a real 301, because a static
host cannot send one. Search engines treat it as a redirect and that is all
I need from it.

`inkstone check` found 23 internal links still pointing at old URLs.
All of them were in posts where I link to my own earlier posts, which
apparently I do a lot.

## What I broke

The feed.
:   Entry IDs in the old feed were the old URLs. New URLs meant new IDs,
    and every feed reader on earth showed fifteen "new" posts. I should
    have kept the old IDs for old posts. Too late now; apologies again.

The 404 page.
:   Worked locally, not on the server, because the server needs to be told
    which file is the 404 page. One line of nginx config.

Draft leakage, nearly.
:   My deploy script ran `inkstone build --drafts` because I had copied the
    command from my shell history. I noticed the half-written post about
    images in the build log before the upload, by luck. The script now
    spells out every flag and runs `inkstone list --drafts` first, so the
    drafts are at least in front of me when I press enter.

## In numbers

|                                  | Before  | After   |
|----------------------------------|--------:|--------:|
| Packages installed to build      |      43 |       0 |
| Clean build                      |  6.8 s  |  1.9 s  |
| Rebuild after editing one post   |  6.8 s  | 0.14 s  |
| JavaScript shipped to a reader   | 212 kB  |  14 kB  |
| Lines of code I am responsible for | ~300  | ~45,000 |

That last row is the honest one. I did not make anything simpler. I moved
the complexity from other people's repositories into mine, where I can read
it. Whether that is a good trade depends entirely on whether you enjoy the
reading. I do, as it turns out.

## Thanks

To the friend with the Windows laptop, to the meetup speaker who made me
doubt the whole idea in August, and to whoever wrote the CommonMark spec
examples, which are the best test suite I have ever been handed for free.

**Update, 19 November:** the feed now carries a stable ID per post that does
not depend on the URL, so at least this cannot happen twice.
