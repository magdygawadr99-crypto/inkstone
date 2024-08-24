---
title: "Small things: Path.as_posix()"
slug: small-things-as-posix
tags: [python, asides]
categories: [asides]
toc: false
---

A short one, because I have now typed this method name about sixty times.

`pathlib.Path` prints with the separator of the platform it runs on:

```python
>>> from pathlib import Path
>>> str(Path("posts") / "2024" / "hello.md")
'posts\\2024\\hello.md'        # on Windows
>>> (Path("posts") / "2024" / "hello.md").as_posix()
'posts/2024/hello.md'          # everywhere
```

If the string is going anywhere other than straight back into the
filesystem (a URL, a cache key, a log line you will grep, a JSON file
another machine reads), you want `as_posix()`. Every time.

The reverse trip needs nothing special. `Path("posts/2024/hello.md")` does
the right thing on Windows too, since forward slashes are accepted there.

That's it. That's the post. The long version, with the bug that taught me
this, is [The build that broke on a Tuesday](/2024/06/the-build-that-broke/).
