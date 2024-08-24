---
title: Why I am writing my own static site generator
description: The upgrade that broke my blog for the fourth time, and the bad idea it gave me.
tags: [meta, inkstone, python]
categories: [inkstone]
series: Building inkstone
---

Last Saturday I wanted to fix a typo in an old post. Two hours later I had
not fixed the typo, but I did know a great deal about why a Markdown plugin
I have never heard of no longer agrees with the version of the templating
library that my theme pins.

<!-- more -->

This is the fourth time. The pattern is always the same: I leave the blog
alone for a few months, come back, create a fresh virtualenv because the old
one belonged to a Python that no longer exists on this machine, run
`pip install -r requirements.txt`, and something in the pile has moved.

I counted. The lock file has 43 packages in it. I chose three of them.

## The bad idea

A blog is a folder of text files turned into a folder of HTML files. I know
roughly how every step of that works. I have never written any of the steps
myself. So:

1. A Markdown parser.
2. A template engine.
3. Something to read the front matter.
4. A loop around those three that walks a directory.

That is the whole plan. It is obviously more work than fixing the
virtualenv. It is also the first side project in years where I know exactly
what "done" looks like: this site, built by it.

## Rules

I wrote these on a sticky note so I can't quietly drop them later.

- **No runtime dependencies.** Standard library only. If I need a thing, I
  write the thing or I do without it.
- **It builds my site.** Not yours. No plugin marketplace, no theme gallery,
  no config option I don't use.
- **I can read all of it.** If I come back in a year and can't follow a
  module, that module was written wrong.
- **Boring output.** Plain HTML files. If the generator rots, the site
  still works.

!!! warning "This is not advice"
    Use Hugo. Use whatever you already have. Writing your own generator is
    the textbook example of a yak that does not need shaving, and I am doing
    it with my eyes open.

## What it is called

*inkstone*. An inkstone is the slab you grind an ink stick on before you can
write anything: a lot of preparation for the sake of a few characters. It
seemed honest.[^name]

## What I expect to go wrong

The Markdown parser. Everyone who has written one says the first 90% takes
a weekend and the second 90% takes the rest of your life. I have given myself
two weekends. We will see.

Next time: lists inside blockquotes inside lists, presumably.

[^name]: It also had no package of that name on my machine, which these days
    is about as much as you can ask of a name.
