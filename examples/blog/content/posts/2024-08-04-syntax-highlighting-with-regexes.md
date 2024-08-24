---
title: Syntax highlighting with regexes and a stack
description: Colouring code at build time, one small state machine per language.
tags: [inkstone, python, highlighting, parsing]
categories: [inkstone]
series: Building inkstone
---

Until last month the code blocks on this site were grey. I had been putting
off highlighting because the well-known way to do it is a JavaScript library
that re-parses every block in the reader's browser, on every visit, forever.
The code does not change after I publish it. It can be coloured once, at
build time.

<!-- more -->

[TOC]

## It is not parsing

A highlighter does not need to understand the program. It needs to know
that `def` is a keyword, that the thing after it is a function name, and
where strings and comments start and stop. That is a job for regular
expressions, tried in order at the current position:

```python
class PythonLexer(RegexLexer):
    name = "python"
    aliases = ["py"]

    states = {
        "root": [
            (r"#.*$", Comment),
            (r"\b(def)(\s+)([A-Za-z_]\w*)", bygroups(Keyword, Text, Name.Function)),
            (words(KEYWORDS, suffix=r"\b"), Keyword),
            (r'"""', String.Doc, "docstring"),      # push a state
            (r'"', String, "dqs"),
            (r"\d+(\.\d+)?", Number),
            (r"[A-Za-z_]\w*", Name),
            (r"\s+", Text),
        ],
        "dqs": [
            (r'\\.', String.Escape),
            (r'"', String, "#pop"),                 # and pop it again
            (r'[^"\\]+', String),
        ],
    }
```

The stack is what makes this more than a list of patterns. Inside a string
a `#` is not a comment, so the lexer pushes a `dqs` state where the only
rules are "escape", "closing quote" and "anything else". Yes, this is
the Pygments design. I read their docs, closed the tab, and wrote down what
I remembered.

## The output is boring on purpose

Every token becomes a `<span>` with a short class, and one stylesheet maps
classes to colours:

```html
<div class="highlight"><pre><code><span class="kd">def</span> <span class="nf">main</span><span class="p">():</span>
    <span class="k">return</span> <span class="mi">0</span>
</code></pre></div>
```

```css
.highlight .k  { color: #c678dd; }            /* Keyword */
.highlight .nf { color: #61afef; }            /* Name.Function */
.highlight .s  { color: #98c379; }            /* String */
.highlight .c  { color: #7f848e; font-style: italic; }
```

`inkstone highlight-css --style dusk` prints that stylesheet; the builder
writes it to `css/highlight.css` so the theme only has to link it. There
are five styles so far: `dusk` and `midnight` are dark, `paper`, `mono` and
`parchment` are light. This site uses `paper` by day and `dusk` at night.

## Languages so far

About twenty. Each one is between 80 and 300 lines of rules. A few samples,
mostly so I can look at this page and see whether they still work.

JavaScript, where the fun part is deciding whether `/` starts a regex or
is a division:

```javascript
const slug = (title) =>
  title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")   // regex literal
    .replace(/^-|-$/g, "");

console.log(slug("Hello, World!") / 2); // division, and NaN
```

Shell:

```bash
#!/usr/bin/env bash
set -euo pipefail

for f in content/posts/*.md; do
  echo "$(wc -w < "$f") ${f##*/}"
done | sort -rn | head -5
```

TOML, which is nearly free once strings and numbers are done:

```toml
[markdown]
highlight = true
highlight_style = "dusk"   # the build fails early if this is not a known style
```

JSON:

```json
{"version": 1, "fields": ["title", "tags", "body"], "docs": 37}
```

And a diff, which is five rules long and the one I look at most:

```diff
 def reading_time(words: int) -> int:
-    return words // 200
+    return max(1, round(words / 220))
```

## Things that went wrong

Catastrophic backtracking.
:   My first string rule was `("(\\.|[^"])*")`. On a 4 kB line of minified
    JSON with an unterminated quote it ran for eleven seconds. Rules now
    match small pieces and let the state machine do the looping.

Nested languages.
:   A `<script>` block in HTML is JavaScript, a `style` attribute is CSS.
    The HTML lexer hands those regions to the other lexer and splices the
    tokens back in. Fenced code inside Markdown works the same way.

Unknown languages.
:   A block marked with a language the highlighter does not know used to
    raise. It now falls back to plain text and the build prints a warning
    with the file and line, once.

!!! tip
    If a block comes out grey, read the build output before blaming the
    lexer. It is nearly always a typo in the language name: `pyhton`,
    `shel`, `yml` where I had only registered `yaml`.

## Line numbers and highlighted lines

Line numbers are optional and off by default. I find them noisy in a blog
post, and useful exactly when the text says "on line 7". The gutter is not
selectable, so copying the code does not copy the numbers.

Highlighting a line to draw the eye is the feature I use more, and it is a
single extra class on the line's wrapper. The theme decides what that looks
like.
