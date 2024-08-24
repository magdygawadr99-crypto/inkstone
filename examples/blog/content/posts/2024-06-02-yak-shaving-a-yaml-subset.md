---
title: "Yak shaving: a YAML subset, because of four lines of front matter"
slug: yak-shaving-a-yaml-subset
description: The front matter of a post is four lines of YAML. The YAML spec is 23,000 words.
tags: [inkstone, python, parsing, yaml]
categories: [inkstone]
---

Every post on this site starts with something like this:

```yaml
---
title: Hello world
date: 2024-05-03
tags: [meta, python]
---
```

Four lines. To read them I need a YAML parser, the standard library does not
have one, and rule one says no dependencies.[^toml] So this is a post about
writing a parser for a format I mostly wish I were not using.

<!-- more -->

## How much YAML is in front matter

I grepped the front matter of every post I have ever written, on this blog
and the two before it. Here is all the YAML I have used in eleven years:

| Feature                         | Used | In `yamlite` |
|---------------------------------|:----:|:------------:|
| `key: value`                    | yes  | yes          |
| Nested mappings by indentation  | yes  | yes          |
| Block lists (`- item`)          | yes  | yes          |
| Flow lists (`[a, b]`)           | yes  | yes          |
| Quoted strings, both kinds      | yes  | yes          |
| Multi-line block scalars        | twice | yes         |
| Comments                        | yes  | yes          |
| Anchors and aliases             | once, by accident | yes |
| Tags (`!!python/object`)        | no   | **error**    |
| Complex keys (`? [a, b]`)       | no   | **error**    |
| Directives (`%YAML 1.2`)        | no   | **error**    |

The last three rows are the point. A subset is fine as long as it *fails
loudly* outside the subset. The worst thing a small parser can do is read
something it does not understand and hand back a plausible value.

## Norway

Everyone's favourite YAML fact: in YAML 1.1, the country code for Norway
is a boolean.

```yaml
countries: [se, dk, no]     # -> ["se", "dk", False]
```

`no`, `yes`, `on`, `off` and their capitalised friends all turn into
booleans. I do not want that, ever, so `yamlite` follows the 1.2 core schema
here: only `true` and `false` are booleans. A post with `draft: yes` gets
the string `"yes"`, and the content loader complains that `draft` should be
a boolean, which is the right place for that complaint.

Version numbers get the same treatment from the other side:

```yaml
python: 3.10      # a float, 3.1, in every YAML parser
python: "3.10"    # what you meant
```

That one I cannot fix in the parser. `3.10` *is* a float. The config loader
knows which keys are meant to be strings and says so when one is not.

## The scanner is where the work is

Like the Markdown parser this is two layers, and like the Markdown parser
the bottom one is where the time went. Indentation is significant, but
only sometimes: inside `[...]` and `{...}` it is not. A `#` starts a
comment, but only after whitespace. A `:` ends a key, but only when it is
followed by a space or the end of the line, which is why this works:

```yaml
url: https://example.com/a:b
time: 12:30
```

and why I now have a dozen tests with names like
`test_colon_in_plain_scalar_is_not_a_key`.

## Dates

`date: 2024-05-03` comes out as a `datetime.date`, and
`date: 2024-05-03 14:00` as a `datetime`. Anything else that merely looks
date-ish stays a string. I parse dates again, more generously, one level up,
where I know the key is called `date` and can afford to guess.

## Was this a yak

Yes. An entire yak. I could have required TOML front matter, which Python
can read out of the box since 3.11, and inkstone does accept that too:
start the block with `+++` instead of `---`. But every post I have is in
YAML, and so is every Markdown file anyone has ever sent me.

About 1,100 lines, for four lines of front matter. The data files in `data/`
use it as well, so maybe call it eight.

[^toml]: `tomllib` is in the standard library, `json` obviously is, and both
    work as front matter. YAML is the one everybody actually uses and the
    one that is missing.
