---
title: The template engine I said I would not write
description: string.Template lasted one afternoon. Then I wrote a lexer.
tags: [inkstone, python, templates]
categories: [inkstone]
series: Building inkstone
---

The plan was `string.Template`: a base page with `$title` and `$content` in
it, done before dinner. That plan survived until I wanted a list of posts on
the front page, which is to say about four hours.

<!-- more -->

You cannot loop in `string.Template`. You can build the list in Python and
substitute the finished HTML, and for an afternoon I did exactly that. Then I
looked at what I had: HTML in Python strings, escaped by hand, with the
page's markup spread over three functions. That is the thing template
engines were invented to stop.

So I wrote one. It reads like Jinja because Jinja is what my fingers know.

```html
{% extends "base.html" %}

{% block content %}
  <h1>{{ page.title }}</h1>
  <ul>
  {% for post in pages %}
    <li>
      <a href="{{ url_for(post.url) }}">{{ post.title }}</a>
      <time>{{ post.date | date("%-d %B %Y") }}</time>
    </li>
  {% endfor %}
  </ul>
{% endblock %}
```

## Three small programs

The lexer
:   Splits the source into text, `{{ ... }}`, `{% ... %}` and `{# ... #}`,
    then tokenizes the insides: names, strings, numbers, operators.

The parser
:   Turns tokens into a tree. Statements (`if`, `for`, `block`, `macro`)
    are a table of small functions; expressions are precedence climbing,
    the same twenty lines everybody writes.

The interpreter
:   Walks the tree with a stack of scopes and appends strings to a list.

I did not compile templates to Python source, which is what the real Jinja
does. Walking the tree is slower, and for a site with a few hundred pages
it is still nowhere near being the slow part. The Markdown parser is.

## The part I got wrong twice: inheritance

`{% extends %}` looks like it should be easy: render the parent, and when
you hit a block, use the child's version instead. The trouble is
`{{ super() }}`, and three levels of templates, and blocks inside blocks.

What finally worked was to stop thinking of it as "child overrides parent".
Before rendering anything, collect for every block name the *chain* of
definitions, most derived first:

```python
for template in lineage:            # child, parent, grandparent
    for name, block in template.blocks.items():
        chains.setdefault(name, []).append(block)
```

Rendering a block means running `chains[name][0]`. `super()` inside it
runs `chains[name][1]`, and so on down the chain. No special cases for depth.

## What happens when a name is missing

!!! note "A decision, not a bug"
    A missing variable renders as nothing, is false in an `if`, and you can
    keep asking it for attributes. `{{ page.author.name }}` on a page without
    an author prints an empty string instead of blowing up the build.

I went back and forth on this. Strict is safer; lenient is what you want at
eleven at night when one page out of ninety lacks a field. The compromise:
*using* an undefined value is fine, but *calling* it or doing arithmetic with
it is an error, because that is nearly always a typo in the template rather
than a gap in the data.

```python
class Undefined:
    def __str__(self):
        return ""

    def __bool__(self):
        return False

    def __getattr__(self, name):
        return self                 # page.author.name keeps working

    def __call__(self, *args, **kwargs):
        raise UndefinedError(self._message)
```

## Escaping

Everything printed with `{{ }}` is HTML-escaped unless it is marked as
markup already. The rendered Markdown of a page is marked; a title from
front matter is not. I have a post whose title contains `<T>` and it was the
first thing I tested.

## Was it worth it

The engine is about 1,800 lines with the filters. It took three weeks of
evenings. `pip install jinja2` takes four seconds.

But I now have error messages that say *which template* and *which line*,
in my own words, and a `Template.dependencies` list that the incremental
build is going to need. More on that when it exists.
