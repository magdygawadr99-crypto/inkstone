---
title: The build that broke on a Tuesday
date: 2024-06-25
description: A friend ran inkstone on Windows. Every link on the site came out with a backslash in it.
tags: [inkstone, python, windows, debugging]
categories: [inkstone]
---

On Tuesday evening a friend sent me a screenshot. She had cloned inkstone to
try it on her own notes, on Windows, and the front page looked fine. Then she
clicked a post.

```text
Not Found: /2024%5C05%5Chello-world/
```

`%5C` is a backslash. I develop on Linux. You can see where this is going.

<!-- more -->

## One string doing three jobs

A page in inkstone has a source path, a URL and an output path. In April,
when there were forty lines of builder, all three came from the same place:

```python
rel = os.path.relpath(source, content_dir)          # posts/hello-world.md
page.url = "/" + os.path.splitext(rel)[0] + "/"     # /posts/hello-world/
page.output = os.path.join(page.url[1:], "index.html")
```

On Linux `os.path.relpath` gives you `posts/hello-world.md` and everything
downstream is accidentally correct. On Windows it gives you
`posts\hello-world.md`, the URL becomes `/posts\hello-world/`, and that
string then goes into every `href` on the site, the sitemap and the feed.

{{< figure src="path-flow.svg" alt="Diagram: the source path feeds both the URL and the output path. The URL must always use forward slashes; the output path uses the platform separator only at the moment a file is written." caption="What I had drawn on paper by Wednesday. The mistake was the arrow that is not there: the URL was derived from an OS path with nothing in between." >}}

## The fix, and the actual fix

The fix took five minutes:

```diff
- rel = os.path.relpath(source, content_dir)
+ rel = Path(source).relative_to(content_dir).as_posix()
```

The actual fix took the rest of the week, because once I went looking, OS
paths and URL paths were mixed up all over the place. The rule I ended up
with, and which is now written at the top of `utils/paths.py`:

> Inside inkstone, every relative path is a POSIX string. Forward slashes,
> no drive letters. It is converted to a real filesystem path in exactly
> two places: when a file is read and when a file is written.

That means `page.source_path`, `page.output_path`, template names, asset
names and cache keys all look the same on every platform, and a cache
written on one machine means the same thing on another.

## While I was in there

Windows found two more things in the same evening.

**Line endings.** The front matter splitter looked for a line that is exactly
`---`. Her editor saves with CRLF, so the line was `---\r` and every file
was "missing front matter". Files are now read with universal newlines and
the splitter never sees a `\r`.

**The file watcher.** Saving a file on Windows often produces two or three
change events within a few milliseconds, and the dev server rebuilt once
for each. It now waits a quarter of a second for things to go quiet before
it starts.

{{< note title="CI would have caught all of this" >}}
I did not have Windows in the test matrix because "it is pure Python, it
will just work". It is now there, and the first run failed nine tests that
compare paths as strings.
{{< /note >}}

## What I took from it

Not much that is new. A path is not a string, a URL is not a path, and the
platform you do not test on is the platform you do not support. But I had to
be shown, by someone kind enough to send a screenshot instead of quietly
giving up.

She now has a site built with inkstone. It has more posts than mine.
