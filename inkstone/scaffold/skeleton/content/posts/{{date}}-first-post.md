---
title: First post
date: {{date}}
tags: [meta]
---

The first post of {{title}}. This paragraph doubles as the summary that list
pages and the feed show.

<!-- more -->

Everything below the marker only appears on the post's own page.

## Where things are

The file you are reading is `content/posts/{{date}}-first-post.md`. The date
and the last part of the address come from its name, the rest from the front
matter at the top. A few things to try while `inkstone serve` is running:

- change the title above and watch the browser reload
- `inkstone new post "Hello world"` for an empty post dated today
- add `draft: true` to hide a post from the built site

## Markdown

The usual syntax works, plus tables, footnotes[^1], task lists and fenced code
with highlighting:

```python
def greet(name):
    return f"Hello, {name}!"
```

{{< note title="Shortcodes" >}}
Things Markdown has no syntax for are written as shortcodes, like this box.
`figure`, `youtube` and `details` come with inkstone as well.
{{< /note >}}

When this post has served its purpose, delete the file.

[^1]: Like this one. Footnotes are collected at the end of the page.
