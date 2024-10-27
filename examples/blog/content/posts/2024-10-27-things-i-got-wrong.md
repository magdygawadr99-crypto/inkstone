---
title: Six months in, things I got wrong
description: A list, in rough order of how long each one took to notice.
tags: [inkstone, retrospective]
categories: [inkstone]
---

inkstone is six months old this month. It builds this site, a friend's
site, and a small documentation site at work that I am not supposed to
mention. Before I write the victory-lap post, here is the other list.

<!-- more -->

## 1. I guessed where the time went

For the first two months I was sure the template engine was the slow part,
because it is a tree-walking interpreter and those are "slow". I spent a
weekend caching compiled expressions. Build time did not move.

Then I wrote `--profile`, which should have come first:

```text
$ inkstone build --profile --no-incremental
  load content      0.21 s   11%
  render markdown   1.12 s   59%
  render templates  0.19 s   10%
  assets            0.08 s    4%
  feeds + search    0.24 s   13%
  write             0.06 s    3%
  total             1.90 s
```

Markdown, by a mile. And inside Markdown, the inline parser, and inside
that, one regex that was being compiled on every call. Fixing that was a
one-line change worth more than the whole caching weekend.

## 2. Pages were dictionaries

In April a page was a `dict`: `page["title"]`, `page["url"]`. By June half
the bugs were misspelled keys, `page["sumary"]` quietly returning nothing
through a `.get()`. Pages are a class now, with the attributes written down
in one place. The front matter keys I do not know about live in
`page.params`, so a template typo is at least a typo against a short list.

## 3. One giant `build()` function

It was 400 lines at its worst. It now runs as a list of named phases, each
of which can be timed (see above), skipped, and hooked by a plugin. Plugins
were not the reason I split it. Being able to *read* it was.

## 4. I treated the dev server as an afterthought

The server is where I spend my time. Every minute I write, `inkstone serve`
is running; `inkstone build` runs once at the end. For months the server was
the neglected one: no live reload, errors only in the terminal, a full
rebuild on every save. Everything in the last three posts was, in effect,
me fixing my priorities.

## 5. Config errors that blamed the user

!!! danger "Actual error message, May 2024"
    `KeyError: 'base_url'`

That is what you got for a typo in `inkstone.toml`. Now an unknown key
says *did you mean `base_url`?*, a wrong type names the key and what it
expected, and none of it prints a traceback unless you pass `--debug`.
This took one evening. I should have done it in week one, because the user
I was being rude to was me.

## 6. No tests for the output, only for the parts

Every package had unit tests and I was pleased with myself. Then a change to
the paginator produced a site where page 2 of the post list linked to
itself as "next". All tests green. There is now a small fixture site that
gets built in the test suite, with assertions about the HTML that comes out.

## Still wrong, as of today

- [x] `--profile` exists
- [x] helpful config errors
- [x] end-to-end test with a fixture site
- [ ] image handling: no resizing, no `srcset`, only width and height
- [ ] the incremental cache does not track data files per page
- [ ] no way to preview a draft on a phone without building with `--drafts`
      and uploading it somewhere
- [ ] documentation for writing a theme is three paragraphs long

The last one bothers me the most. Code that only its author can use is a
diary.
