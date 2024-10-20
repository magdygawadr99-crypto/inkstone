# Markdown reference

inkstone has its own Markdown parser. It follows
[CommonMark](https://commonmark.org/) for the core syntax and adds the
extensions most blogs end up wanting. This page shows what you can write.
Each example is the source followed by a note on what comes out.

If you know Markdown, skip to [Extensions](#extensions) and
[Code blocks](#code-blocks).

## Paragraphs and line breaks

A paragraph is one or more lines of text. A blank line ends it.

```markdown
This is one paragraph. A single line break
inside it is just a space in the output.

This is another.
```

For an actual line break, end the line with a backslash or two spaces:

```markdown
Roses are red\
Violets are blue
```

If you would rather every line break counted, set `markdown.hard_wraps =
true`. I find that it makes prose harder to edit, but it suits poetry and
changelogs.

## Headings

```markdown
# Page title
## Section
### Sub-section
#### And so on, down to six
```

The page title already comes from the front matter and is printed by the
template as the only `<h1>`. Start the headings in your text at `##`.

Every heading gets an `id` made from its text, so it can be linked to:
`## What it does` becomes `<h2 id="what-it-does">`, and
`[see above](#what-it-does)` jumps there. If the same text occurs twice the
second one is `what-it-does-1`. To choose the id yourself:

```markdown
## Frequently asked questions {#faq}
```

Heading ids can be turned off with `markdown.heading_ids = false`. The table
of contents needs them.

## Emphasis

```markdown
*italic* or _italic_
**bold** or __bold__
***both***
~~struck through~~
`code`
```

## Links and images

```markdown
[link text](https://example.com)
[with a title](https://example.com "shown on hover")
[another page of this site](/about/)
[a heading on this page](#headings)

![alt text for the image](photo.jpg)
![alt text](photo.jpg "a title")
```

Reference style keeps long URLs out of the sentence:

```markdown
The [CommonMark spec][spec] has 652 examples.

[spec]: https://spec.commonmark.org/
```

The definitions can go anywhere in the file, including the very end.

Write links to other pages of your site as site-relative paths starting
with `/`. `inkstone check` verifies that they point at something. Bare
URLs and e-mail addresses in text become links on their own:

```markdown
See https://example.com/docs or write to me@example.com.
```

Always write alt text. If an image is purely decorative, `![](border.png)`
gives it an empty one, which is what screen readers want in that case.

## Lists

```markdown
- one
- two
  - nested, indented by two spaces
  - also nested
- three

1. first
2. second
3. third
```

A list item can hold several paragraphs, code blocks and other lists.
Indent them to line up with the item's text:

```markdown
1. Install it.

   This paragraph belongs to step one.

       so does this indented code block

2. Run it.
```

If the items of a list are separated by blank lines, each one is wrapped
in a `<p>` and the list comes out with more space between items.

## Block quotes

```markdown
> A quote can span several lines
> and contain *other* Markdown.
>
> > Including quotes.
```

## Horizontal rule

Three or more dashes, asterisks or underscores on their own line: `---`.
At the very top of a file `---` starts the front matter instead, which is
not usually a problem since nobody opens a page with a rule.

## Code blocks

Fence code with three backticks and name the language:

````markdown
```python
def greet(name: str) -> str:
    return f"Hello, {name}"
```
````

The block is highlighted at build time. No JavaScript runs in the reader's
browser for this; the colours come from `css/highlight.css`, which the
builder writes from the style named in `markdown.highlight_style`.

Languages the highlighter knows, with the aliases it accepts:

| Language | Also written as |
|----------|-----------------|
| `bash` | `sh`, `shell`, `zsh` |
| `c`, `cpp` | `h`, `c++`, `cc`, `hpp` |
| `css` | |
| `diff` | `patch` |
| `dockerfile` | `docker` |
| `go` | `golang` |
| `html`, `xml` | `htm`, `svg`, `rss`, `atom` |
| `ini` | `cfg`, `properties`, `editorconfig` |
| `java` | |
| `javascript`, `typescript` | `js`, `jsx`, `ts`, `tsx` |
| `json` | `jsonc`, `jsonl` |
| `makefile` | `make` |
| `markdown` | `md` |
| `python` | `py` |
| `rust` | `rs` |
| `sql` | `postgres`, `mysql`, `sqlite` |
| `toml` | |
| `yaml` | `yml` |

A block with no language, or with one that is not on the list, is shown as
plain text; a typo on a fence never breaks a build. Use `text` when you
want to say so explicitly, for program output and the like.

Five colour schemes come with inkstone: `dusk` (the default) and `midnight`
are dark, `paper`, `mono` and `parchment` are light. Pick one with
`markdown.highlight_style`. To have a light scheme by day and a dark one at
night, name the second in `params.highlight_style_dark`:

```toml
[markdown]
highlight_style = "paper"

[params]
highlight_style_dark = "dusk"
```

`inkstone highlight-css --style mono` prints a scheme's stylesheet, if you
want to adapt one by hand.

### Marked lines and line numbers

Options go in braces after the language:

````markdown
```python {hl_lines="2 4-5"}
def reading_time(words):
    minutes = words / 220
    if minutes < 1:
        # never claim a post takes zero minutes
        return 1
    return round(minutes)
```
````

| Option | Meaning |
|--------|---------|
| `hl_lines="2 4-5"` | Mark these lines. Single numbers and ranges, separated by spaces or commas, counted from the top of the block. |
| `linenos` | Number the lines. |
| `linenostart=10` | Start numbering at 10 instead of 1; for excerpts. |

Line numbers sit in a gutter that cannot be selected, so copying the code
does not copy the numbers.

In the HTML, a marked line is wrapped in `<span class="hll">` and inline
line numbers are `<span class="lineno">`, all inside
`<div class="highlight">`. That is what a theme styles.

### Showing a fence inside a fence

Use more backticks on the outside than on the inside. The examples on this
page are fenced with four.

### Indented code

Four spaces of indentation also make a code block, as in original Markdown.
It cannot name a language, so it is never highlighted. I only use fences.

## Raw HTML

HTML in a Markdown file is passed through untouched:

```markdown
<details>
<summary>Spoiler</summary>

The butler did it.

</details>
```

Leave a blank line after an opening tag if you want the content inside to
be treated as Markdown. For anything you need more than once, a
[shortcode](plugins.md#shortcodes) is nicer than pasted HTML.

## Extensions

These are on unless you say otherwise.

### Tables

```markdown
| Language | Lines | Tests |
|----------|------:|:-----:|
| Python   | 9,791 |  yes  |
| Go       | 4,070 |  yes  |
```

The second line decides the alignment of each column: `:--` left, `--:`
right, `:-:` centred. The pipes at the two ends are optional, and the
columns do not have to line up in the source. To put a literal pipe in a
cell, write `\|`.

Cells hold inline Markdown only: emphasis, code, links. No lists or
paragraphs. If a table needs those, it wants to be something else.

### Footnotes

```markdown
The parser took two weekends.[^weekends]

[^weekends]: Five, in fact. Footnotes can run over several lines and
    paragraphs, as long as the continuation is indented by four spaces.
```

The label (`weekends`) is only for matching the two halves. Notes are
numbered in the order they are first referenced and collected at the end
of the page, each with a link back to where it was used. A definition that
nothing refers to is dropped.

The default theme shows the note in a small pop-up when you hover over or
focus the number.

### Task lists

```markdown
- [x] write the parser
- [x] write the tests
- [ ] write the documentation
```

These render as disabled checkboxes. They are a way to show a checklist,
not an interactive form.

### Definition lists

```markdown
Lexer
:   Splits the source into tokens.

Parser
:   Turns tokens into a tree.
:   A term can have more than one definition.
```

The term is a line of its own. Each definition starts with a colon and
at least one space.

### Admonitions

Call-out boxes for notes and warnings:

```markdown
!!! note
    The body is indented by four spaces and can contain any Markdown:
    lists, code blocks, other admonitions.

!!! warning "Back up first"
    The text in quotes replaces the default title.

!!! tip ""
    An empty title gives a box with no title line.
```

The word after `!!!` is the kind. It becomes a CSS class, and the default
title if you give none. The default theme has colours for `note` (also the
fallback for kinds it does not know), `tip`, `hint`, `success`, `warning`,
`caution`, `important`, `danger`, `error` and `bug`. Any other word works
and can be styled in your own CSS as `.admonition.<kind>`.

Three question marks make it collapsible, a `<details>` element that
starts closed. `???+` starts open:

```markdown
??? note "Long derivation, click to open"
    ...
```

### Strikethrough

`~~like this~~`.

### Bare links

URLs starting with `http://`, `https://` or `www.` and e-mail addresses are
linked without needing angle brackets. Trailing punctuation is left out of
the link, so a URL at the end of a sentence does the right thing.

### Attribute lists on headings

```markdown
## Installing on Windows {#windows .platform-note}
```

sets the `id` and adds a class. Only headings take attributes.

### Table of contents marker

A paragraph consisting of `[TOC]` is replaced by a nested list of the
page's headings. The default theme already shows a table of contents next
to posts, so you only need the marker on pages where you want one in the
text itself.

### Summary marker

`<!-- more -->` on a line of its own ends the summary. It is an HTML
comment, so it is invisible wherever the Markdown is rendered, and inkstone
removes it from the page. See [Content](content.md#summaries).

## Optional extensions

These change what ordinary characters mean in prose, so they are off until
asked for.

| Name | Syntax | Result |
|------|--------|--------|
| `smart` | `"quotes"`, `--`, `---`, `...` | curly quotes, en dash, em dash, ellipsis |
| `abbr` | `*[HTML]: Hypertext Markup Language` | every later "HTML" gets an `<abbr>` with that title |
| `mark` | `==important==` | `<mark>important</mark>` |
| `sub` | `H~2~O` | subscript |
| `sup` | `x^2^` | superscript |

`smart` has its own switch and is on by default: `markdown.smart = true`.

For the others, list the extensions you want. The list replaces the default
set, so name those too:

```toml
[markdown]
extensions = [
  "tables", "strikethrough", "tasklists", "autolink", "footnotes",
  "deflists", "admonitions", "attrs", "toc",
  "abbr", "mark",
]
```

Leaving one out of the list turns it off, which is also how you disable a
default extension you do not want.

With `sub` enabled, a single tilde means subscript and you need two for
strikethrough.

## Escaping

A backslash in front of a punctuation character makes it literal:

```markdown
\*not italic\*
1\. not a list item
\[not a link\](either)
```

Inside code spans and code blocks nothing needs escaping.

## Where inkstone differs from CommonMark

The parser passes the great majority of the specification's examples, and
I run them as part of the test suite. The known differences are in corners
I have never hit in real writing:

- some combinations of deeply nested lists with indented code,
- a few of the HTML block start and end conditions,
- link destinations containing unbalanced parentheses.

If a page renders differently here than in another CommonMark
implementation and it is not one of those, that is a bug and I would like
to hear about it.

## Using the parser on its own

The Markdown package does not depend on the rest of inkstone:

```python
from inkstone.markdown import Markdown, render

print(render("# hi\n\nsome *text*"))

md = Markdown(smart=True, extensions=None)   # None: the default set
html = md.convert(open("post.md", encoding="utf-8").read())
for entry in md.toc:
    print(entry.level, entry.id, entry.title)
```

`Markdown(highlight=func)` takes a callback `func(code, lang)` that returns
finished HTML for a code block, or `None` to fall back to a plain
`<pre><code>`. That is how the builder plugs in the highlighter.
