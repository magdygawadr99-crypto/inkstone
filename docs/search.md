# Search

A static site has no server to send a query to, so inkstone does search the
other way round: it builds an index at build time, ships it as a JSON file,
and a small script searches it in the reader's browser. Nothing leaves their
machine, and there is nothing to host or pay for.

This works well up to a few thousand pages. For this documentation's
purposes, "a blog" is comfortably inside that.

## Turning it on

It is on by default:

```toml
[search]
enabled = true
fields = { title = 3.0, tags = 2.0, body = 1.0 }
```

With that, every build writes two extra files:

| File | What it is |
|------|-----------|
| `search-index.json` | the index: vocabulary, postings, and a title, URL and summary per page |
| `js/inkstone-search.js` | the search client, a copy of `inkstone/search/client/search.js` |

The default theme puts a search box in the header and wires it up. To get
a results page as well (where pressing Enter in the box takes you), add a
page that uses the search template:

```markdown
---
title: Search
template: search.html
---

Optional help text, shown under the results.
```

Save it as `content/search.md`. If you want it somewhere other than
`/search/`, tell the theme with `params.search_url`.

You probably do not want search engines indexing your search page:

```toml
[robots]
disallow = ["/search/"]
```

Set `enabled = false` and both files, the box and the script tag go away.
The two settings are described with the rest of the configuration, under
[the `search` table](configuration.md#search).

## What gets indexed

The pages made from your Markdown files, as far as they are part of the
build: a draft is only in the index when you build with `--drafts`. List
pages (sections, tags, the home page) are not indexed. They would only
repeat what the pages themselves say.

The `fields` table says which parts of a page are indexed and how much
each one matters for ranking:

| Field | Content | Default weight |
|-------|---------|---------------:|
| `title` | the page title | 3.0 |
| `tags` | the page's tags | 2.0 |
| `body` | the text of the page, without markup | 1.0 |

A match in the title counts three times as much as one in the body.
Remove a field from the table to leave it out; change a number to shift
the balance. The defaults are the first values I tried, and I have not
found a reason to change them.

Before indexing, text is split into words, lower-cased, stripped of
accents, filtered for very common words (*the*, *and*, *of*) and
**stemmed**, so that *parsing*, *parsed* and *parser* all end up as the same
index term. Identifiers are split too: `FileSystemLoader` can be found as
*file*, *system* or *loader*.

Stemming and the stop word list are for English. Text in other languages
is indexed as it is, which works, minus the niceties.

## Query syntax

What a reader can type:

| Query | Finds |
|-------|-------|
| `template inheritance` | pages with either word; pages with both rank higher |
| `+template inheritance` | pages that must contain *template* |
| `template -jinja` | pages with *template* but without *jinja* |
| `"cache invalidation"` | the exact phrase |
| `title:markdown` | *markdown* in the title only; works with any indexed field |
| `pars*` | words starting with *pars* |
| `incremental~` | also words one typo away |

In the header box the last word is treated as a prefix while you are still
typing it, so results show up before you finish the word.

Ranking is BM25F, the standard formula with per-field weights. In practice
that means: rare words matter more than common ones, a match in a short
field counts for more than one buried in a long one, and repeating a word
twenty times does not make a page twenty times as relevant.

## The theme side

The default theme never loads the index on page load. The pieces:

- `partials/search_box.html` is a plain `<form method="get">` pointing at
  the search page. Without JavaScript it still works as a form, and the
  results page tells the reader that search needs scripting.
- `js/search-ui.js` (about 10 kB before minifying, loaded with `defer`)
  waits. On the first
  focus, keystroke or pointer hover over the box it fetches
  `js/inkstone-search.js` and `search-index.json`, then calls
  `InkstoneSearch.attach(input, results)`.
- `/` focuses the box from anywhere on the page. Arrow keys move through
  the results, Enter opens one, Escape closes the list.
- On the search page the script reads `?q=` from the address, shows the
  full result list with the matching words marked, and keeps the address in
  step as you type so results can be bookmarked.

The paper theme has no box in the header, only a link to the search page.

Both partials can be replaced like any other template; see
[Templates](templates.md#where-templates-come-from).

## Using the client in your own theme

Load the script and the index, then either search yourself or let the
client drive an input:

```html
<input type="search" id="q" placeholder="Search">
<ul id="hits" hidden></ul>

<script src="{{ asset('js/inkstone-search.js') }}"></script>
<script>
  InkstoneSearch.attach(
    document.getElementById("q"),
    document.getElementById("hits"),
    { url: "{{ url_for('/search-index.json') }}", limit: 8 }
  );
</script>
```

With `url` set, `attach` fetches the index itself the first time the input
gets focus. It handles the keyboard, the ARIA attributes for a combobox,
and hiding the list on Escape or a click elsewhere.

The API:

| Call | Does |
|------|------|
| `InkstoneSearch.load(url)` | Fetches and parses the index. Returns a promise for it. |
| `InkstoneSearch.search(query, {limit})` | Returns an array of hits, best first. Needs `load` to have finished. |
| `InkstoneSearch.suggest(prefix, {limit})` | Completes a partial word from the vocabulary. |
| `InkstoneSearch.attach(input, results, options)` | Turns an input and a container into a search-as-you-type box. Returns `{update, close, destroy}`. |

A hit looks like this:

```javascript
{
  id: "/2024/05/the-template-engine-i-said-i-would-not-write/",
  score: 7.31,
  stored: { url: "...", title: "...", summary: "..." },
  matches: { title: ["templat"], body: ["templat", "inherit"] }
}
```

`matches` holds index terms (stems), per field. Pass them to
`index.highlight(text, terms)` to get the text back as
`[string, isMatch]` pairs for marking up.

Options of `attach`, with defaults:

| Option | Default | Meaning |
|--------|---------|---------|
| `limit` | `8` | Hits to show. |
| `debounce` | `120` | Milliseconds to wait after a keystroke. |
| `minLength` | `2` | Shorter input shows nothing. |
| `prefix` | `true` | Treat the word being typed as a prefix. |
| `url` | none | Fetch the index from here on first focus. |
| `emptyText` | `"No results"` | Shown when nothing matches. |
| `activeClass` | `"is-active"` | Class on the hit selected with the arrow keys. |
| `renderItem` | none | `function (hit, index)` returning a DOM node, to draw hits yourself. |

The markup `attach` produces uses the classes `inkstone-search-result`,
`inkstone-search-title`, `inkstone-search-summary` and
`inkstone-search-empty`, with matches wrapped in `<mark>`. Style those and
you are done.

## Size

The index grows with the amount of text, not the number of pages. It is
mostly small integers and compresses well, so make sure your server gzips
`.json` files; that alone usually cuts it to a third or less. If yours
still gets too big to download casually, take `body` out of `fields`: an
index of titles and tags only is tiny and finds most of what people look
for on a blog.

## Searching from Python

The same index can be queried at build time or in a script, with the same
results as the browser:

```python
from pathlib import Path
from inkstone.search import SearchIndex

index = SearchIndex.from_json(Path("public/search-index.json").read_bytes())
for hit in index.search('title:markdown "two passes"', limit=5):
    print(round(hit.score, 2), hit.stored["title"])
```

The Python and JavaScript implementations share a test that feeds both the
same documents and queries and compares the output. If you ever see them
disagree, that is a bug.
