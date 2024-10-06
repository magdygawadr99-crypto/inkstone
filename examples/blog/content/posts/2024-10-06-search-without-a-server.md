---
title: Search without a server
description: An inverted index in a JSON file, a stemmer written twice, and BM25 in the browser.
tags: [inkstone, python, javascript, search]
categories: [inkstone]
series: Building inkstone
---

A static site has nothing to answer a search query with. The usual
answers are "send people to a search engine with `site:` in the query",
which is giving up, or a hosted service, which is a dependency with a
monthly invoice. The third answer is to ship the index to the reader and
search it in their browser. For a blog of this size that is entirely
reasonable, and it is the last big piece inkstone was missing.

<!-- more -->

## What is in the index

An inverted index maps each word to the documents that contain it. Built
once, at the end of `inkstone build`, written to `search-index.json`:

```json
{
  "version": 1,
  "fields": ["title", "tags", "body"],
  "boosts": [3.0, 2.0, 1.0],
  "docs": [
    ["/2024/05/the-template-engine-i-said-i-would-not-write/", [9, 3, 1104]],
    ["/2024/06/yak-shaving-a-yaml-subset/", [12, 4, 987]]
  ],
  "vocab": ["cach", "engin", "lexer", "pars", "templat", "yaml"],
  "postings": [[0, 2, 1, 14], [0, 0, 1, 1, 2, 9], [0, 2, 6]]
}
```

`docs` holds the URL and the length of each field. `vocab` is the sorted
list of terms. `postings` runs parallel to it: one flat array of small
integers per term, saying which documents it occurs in, in which field and
at which word positions. Everything is delta-encoded so the numbers stay
small and gzip has something to chew on. (The sample above is abridged; the
real arrays are longer and less readable.)

The words in `vocab` look mangled because they are stems. Which brings me
to the part that hurt.

## The stemmer, twice

"Parsing", "parser" and "parsed" should all find the same posts. A stemmer
chops words down to a common root: `pars`. I used the Porter2 algorithm
because its description is a list of rules precise enough to implement
without understanding linguistics.

The catch: the index is built in Python, and the query is typed into a
browser. The query has to be stemmed by *exactly the same rules* or it will
look up terms that are not in the vocabulary. So there are two
implementations, 250 lines of Python and 250 of JavaScript, and they must
agree on every word in English.

They did not, at first. The test that found the differences takes a word
list, runs both, and compares:

```python
@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_stemmers_agree(tmp_path):
    words = WORDS.read_text(encoding="utf-8").split()
    expected = [stem(word) for word in words]
    script = f"const s = require({str(CLIENT)!r}); " \
             "const ws = require('fs').readFileSync(0, 'utf8').split('\\n'); " \
             "console.log(JSON.stringify(ws.map(s.stem)));"
    out = subprocess.run(["node", "-e", script], input="\n".join(words),
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == expected
```

Twenty-nine thousand words. The first run had 212 mismatches, all of them
my fault, most of them one typo in the JavaScript version of step 1b.

## Ranking

Finding the documents is the easy half. Ordering them is what makes search
feel right or wrong. I use BM25, the formula every search engine starts
from, with a per-field weight so a match in the title counts for more than
one in the body:

| Field | Weight | Why                                              |
|-------|-------:|--------------------------------------------------|
| title |    3.0 | If the word is in the title, the post is about it |
| tags  |    2.0 | I chose those words on purpose                    |
| body  |    1.0 | Everything else                                   |

The weights are in `inkstone.toml` under `[search]`. I have not tuned them.
They are the first numbers I typed and the results looked sensible.

## Size

The whole point of doing this client-side is that the index is small enough
to download. For this site, at the time of writing:

| What                          | Raw    | Gzipped |
|-------------------------------|-------:|--------:|
| `search-index.json`           | 148 kB |   41 kB |
| `inkstone-search.js`          |  36 kB |   11 kB |
| For comparison: one hero image on a typical news site | 400 kB | 380 kB |

Neither file is loaded until you focus the search box. Most visitors never
do, and they should not pay for it.

## Using it from a theme

The client is one script with three calls that matter:

```javascript
InkstoneSearch.load("/search-index.json").then(() => {
  const hits = InkstoneSearch.search("template inheritance", { limit: 10 });
  // [{ id, score, stored: { url, title, summary }, matches: { body: [...] } }]
});

// or let it wire up an input and a results list by itself
InkstoneSearch.attach(inputElement, resultsElement);
```

The default theme does the second, and adds a `/` shortcut to focus the
box. Try it: it is the thing in the header.

## What it cannot do

No typo tolerance beyond one edit on longer words, no synonyms, English
stemming only. A post in another language is indexed, just unstemmed. For a
site with thousands of pages the index would get too big and you would want
to split it. I do not have that problem and I am not going to pretend I do.
