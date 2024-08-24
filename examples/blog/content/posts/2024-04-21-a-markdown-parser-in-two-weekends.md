---
title: A Markdown parser in two weekends (it took five)
description: Blocks first, inlines second, and a long detour through emphasis.
tags: [inkstone, python, parsing, markdown]
categories: [inkstone]
series: Building inkstone
---

I gave myself two weekends for the Markdown parser. It is now the fifth, and
I am calling it done in the sense that it renders every post on this site
and I have stopped finding new ways to break it every evening.

<!-- more -->

## Two passes

The one piece of advice I took from the CommonMark spec's appendix, and the
best decision in the whole thing: parse in two passes.

The first pass only looks at the *start of lines*. It decides what the
blocks are (paragraph, list item, quote, fenced code) and builds a tree.
It does not look inside the text at all.

The second pass walks that tree and parses the text of each paragraph and
heading into inlines: emphasis, links, code spans.

```python
def parse(text: str) -> Document:
    doc = BlockParser().parse(text.splitlines())
    for node in doc.walk():
        if node.wants_inlines:
            node.children = InlineParser(doc.refs).parse(node.raw)
    return doc
```

Why it matters: link reference definitions (`[foo]: /url`) can come *after*
the paragraph that uses them. With two passes the block parser has collected
all of them before a single inline is parsed. I tried one pass first. Do not
try one pass first.

## Blocks are a stack of open containers

Each line is matched against the containers that are still open, outermost
first. A `>` continues a quote, enough indentation continues a list item.
Whatever is left over after that either starts a new block or is text for
the innermost open paragraph.

```python
def feed(self, line: str) -> None:
    rest, matched = line, 0
    for container in self.open[1:]:
        consumed = container.continues(rest)
        if consumed is None:
            break
        rest, matched = rest[consumed:], matched + 1

    if matched < len(self.open) - 1 and self.is_lazy(rest):
        self.tip.add_line(rest)   # "laziness", see below
        return
    self.close_down_to(matched + 1)
    self.open_new_blocks(rest)
```

"Laziness" is the rule that makes this

```markdown
> a quote that I could not be
bothered to prefix on every line
```

one quote with one paragraph. It is three lines of spec and it cost me most
of a Sunday, because the lazy line must not be something that would start a
block of its own, and "would start a block of its own" depends on where you
are.

## Emphasis ate two weekends by itself

I assumed `*this*` was the easy part. It is the hardest part. Whether a run
of `*` or `_` can open or close emphasis depends on what is on either side
of it (whitespace, punctuation, or neither), and matching openers to closers
has a rule about lengths being multiples of three that I still cannot state
from memory.[^three]

The algorithm in the spec keeps a stack of delimiter runs and resolves them
after the fact. I resisted it for a week and wrote my own, which handled
`**bold**` and `*it*` and fell over on `***both***`. Then I implemented the
one from the spec, word for word, and all 130-odd emphasis examples passed
on the second run.

## Where it stands

I run the examples from the CommonMark spec as a test suite. Not all of them
pass, and I have decided which failures I can live with.

| Section            | Examples | Passing |
|--------------------|---------:|--------:|
| Tabs               |       11 |      11 |
| Block quotes       |       25 |      25 |
| List items         |       48 |      44 |
| Lists              |       26 |      23 |
| Emphasis           |      132 |     132 |
| Links              |       90 |      87 |
| Raw HTML           |       20 |      17 |
| HTML blocks        |       44 |      39 |
| **Whole spec**     |  **652** | **631** |

Those are the sections I was most worried about, plus the total. The
failures are things like a list item that starts with an indented code
block, or HTML comments containing `--`. I have never written either in a
blog post and I am not going to start.

## Extras

CommonMark has no tables, footnotes or task lists, and I use all three.[^gfm]
They are extensions in my parser too: each one registers a block rule or an
inline rule and a renderer for its node type. Tables took an evening.
Footnotes took three, mostly because a footnote definition is a container
(it can hold paragraphs and code blocks) and I had modelled it as a leaf.

- [x] tables, with column alignment
- [x] footnotes
- [x] task lists
- [x] definition lists
- [ ] attribute lists (`{#id .class}`) on anything but headings, maybe never

Next up is the thing that turns the HTML into a page. I was going to use
`string.Template` for that. I have a feeling about how that will go.

[^three]: "If one of the delimiters can both open and close emphasis, then
    the sum of the lengths of the delimiter runs containing the opening and
    closing delimiters must not be a multiple of 3 unless both lengths are
    multiples of 3." I had to copy that out of the spec just now.

[^gfm]: The table syntax is the GitHub one. The footnote syntax is the one
    everybody seems to have agreed on without anyone writing it down.
