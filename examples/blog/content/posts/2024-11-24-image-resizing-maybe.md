---
title: Image resizing, maybe
draft: true
tags: [inkstone, images]
categories: [inkstone]
summary: Notes towards a post about the one feature that would break rule one.
---

Not published yet. Notes to self.

The one thing inkstone cannot do that I actually miss: take a 4000 pixel
photo and write three smaller ones plus a `srcset`. Doing that needs an
image decoder and a resampler. The standard library has neither.

Options, none of them good:

1. Write a JPEG decoder. No. I have read about the DCT. I have limits.
2. Shell out to ImageMagick if it happens to be installed. Works on my
   machine, which is the problem with it.
3. An *optional* dependency: if Pillow is importable, resize; if not, copy
   the original and warn. Bends rule one without quite breaking it?
4. Keep resizing out of the generator entirely. A separate script, run by
   hand, commits the resized files. This is what I do today.

Leaning towards 4, i.e. towards doing nothing, which is suspicious.

TODO before publishing:

- [ ] measure how much the unresized images on the projects page cost
- [ ] try option 3 on a branch and see how ugly the fallback path is
- [ ] decide whether "zero dependencies" is a rule or a brag
