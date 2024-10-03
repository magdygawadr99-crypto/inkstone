from __future__ import annotations

import json
import math
from bisect import bisect_left
from collections import Counter
from datetime import date
from typing import Any, Iterable, Mapping

from .analyzer import Analyzer
from .errors import SearchError
from .query import Query, SearchHit, evaluate, parse_query
from .stemmer import stem
from .tokenizer import Token, tokenize

FORMAT_VERSION = 1

# Extra positions inserted between the items of a list-valued field, so that a
# phrase cannot match across two tags, stopword holes included.
_LIST_GAP = 16

MAX_PREFIX_TERMS = 200

# Endings tried when a prefix runs past the stem, see expand_prefix().
_COMPLETIONS = ("", *"s e d g n es ed ng on ly ss al ing ion ess".split())

Postings = dict[int, dict[int, list[int]]]


def _as_texts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None]
    if isinstance(value, (set, frozenset)):
        return sorted(str(item) for item in value if item is not None)
    return [str(value)]


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
        return [_jsonable(item) for item in items]
    return str(value)


def _encode_postings(by_field: Postings) -> list[int]:
    """Flatten to [field, ndocs, (doc delta, npos, pos deltas...)...] per field.

    One flat list of small integers per term is about as compact as JSON gets
    without resorting to a string encoding.
    """
    flat: list[int] = []
    for f in sorted(by_field):
        docs = by_field[f]
        flat += (f, len(docs))
        last_doc = 0
        for doc in sorted(docs):
            positions = docs[doc]
            flat += (doc - last_doc, len(positions))
            last_doc = doc
            last = 0
            for position in positions:
                flat.append(position - last)
                last = position
    return flat


def _decode_postings(flat: list[int]) -> Postings:
    by_field: Postings = {}
    i = 0
    while i < len(flat):
        f, ndocs = flat[i], flat[i + 1]
        i += 2
        docs = by_field.setdefault(f, {})
        doc = 0
        for _ in range(ndocs):
            doc += flat[i]
            count = flat[i + 1]
            i += 2
            position = 0
            positions = []
            for delta in flat[i : i + count]:
                position += delta
                positions.append(position)
            if len(positions) != count:
                raise IndexError("truncated position list")
            i += count
            docs[doc] = positions
    return by_field


class IndexBuilder:
    def __init__(
        self,
        fields: Mapping[str, float] | Iterable[str],
        *,
        language: str = "en",
        stopwords: bool | Iterable[str] = True,
        stemming: bool = True,
        min_token_length: int = 2,
        store: Iterable[str] = (),
        k1: float = 1.2,
        b: float = 0.75,
    ):
        if not isinstance(fields, Mapping):
            fields = dict.fromkeys(fields, 1.0)
        if not fields:
            raise SearchError("a search index needs at least one field")
        self.fields: dict[str, float] = {}
        for name, boost in fields.items():
            if isinstance(boost, bool) or not isinstance(boost, (int, float)):
                raise SearchError(f"boost for search field {name!r} is not a number")
            if boost <= 0:
                raise SearchError(f"boost for search field {name!r} must be positive")
            self.fields[str(name)] = float(boost)
        if not 0 <= b <= 1 or k1 < 0:
            raise SearchError("BM25 parameters out of range (k1 >= 0, 0 <= b <= 1)")
        self.store = tuple(dict.fromkeys(store))
        self.analyzer = Analyzer(
            language,
            stopwords=stopwords,
            stemming=stemming,
            min_token_length=min_token_length,
        )
        self.k1 = float(k1)
        self.b = float(b)

        self._field_index = {name: i for i, name in enumerate(self.fields)}
        self._ids: set[str] = set()
        self._docs: list[list[Any]] = []
        self._postings: dict[str, Postings] = {}
        self._forms: dict[str, Counter[str]] = {}

    def __len__(self) -> int:
        return len(self._docs)

    def add(
        self,
        doc_id: str,
        fields: Mapping[str, Any],
        stored: Mapping[str, Any] | None = None,
    ) -> None:
        """Index one document.

        `fields` may hold more than the indexed fields; the rest is ignored.
        Values are plain text or lists of strings (tags). Only the names
        listed in `store` are kept for display, taken from `stored` first and
        from `fields` otherwise.
        """
        doc_id = str(doc_id)
        if doc_id in self._ids:
            raise SearchError(f"duplicate search document id {doc_id!r}")
        self._ids.add(doc_id)
        doc = len(self._docs)

        lengths = [0] * len(self.fields)
        for name, f in self._field_index.items():
            base = 0
            for text in _as_texts(fields.get(name)):
                tokens = tokenize(text)
                if tokens:
                    lengths[f] += self._index_tokens(doc, f, text, tokens, base)
                    base += tokens[-1].position + 1 + _LIST_GAP

        stored = stored or {}
        values = []
        for name in self.store:
            value = stored[name] if name in stored else fields.get(name)
            values.append(_jsonable(value))
        self._docs.append([doc_id, lengths, values])

    def _index_tokens(
        self, doc: int, f: int, text: str, tokens: list[Token], base: int
    ) -> int:
        length = 0
        for token in tokens:
            term = self.analyzer.term(token.text)
            if term is None:
                continue
            if token.joined:
                surface = text[token.start : token.end].lower()
            else:
                surface = token.text
                length += 1
            forms = self._forms.get(term)
            if forms is None:
                forms = self._forms[term] = Counter()
            forms[surface] += 1
            docs = self._postings.setdefault(term, {}).setdefault(f, {})
            positions = docs.setdefault(doc, [])
            position = base + token.position
            # "run-s" gives both "run" and the joined "runs" -> "run" here
            if not positions or positions[-1] != position:
                positions.append(position)
        return length

    def build(self) -> SearchIndex:
        vocab = sorted(self._postings)
        forms = {}
        for i, term in enumerate(vocab):
            counts = self._forms[term]
            best = min(counts, key=lambda form: (-counts[form], len(form), form))
            if best != term:
                forms[i] = best
        return SearchIndex(
            fields=self.fields,
            store=self.store,
            docs=[list(doc) for doc in self._docs],
            vocab=vocab,
            postings=[_encode_postings(self._postings[term]) for term in vocab],
            analyzer=self.analyzer,
            forms=forms,
            k1=self.k1,
            b=self.b,
        )


class SearchIndex:
    """A built, read-only index. Get one from IndexBuilder.build() or from_json()."""

    def __init__(
        self,
        *,
        fields: Mapping[str, float],
        store: Iterable[str],
        docs: list[list[Any]],
        vocab: list[str],
        postings: list[list[int]],
        analyzer: Analyzer,
        forms: Mapping[int, str] | None = None,
        k1: float = 1.2,
        b: float = 0.75,
    ):
        self.fields = dict(fields)
        self.store = tuple(store)
        self.analyzer = analyzer
        self.k1 = k1
        self.b = b
        self._boosts = list(self.fields.values())
        self._docs = docs
        self._vocab = vocab
        self._terms = {term: i for i, term in enumerate(vocab)}
        # Postings stay in their encoded form and are decoded per term on
        # first use; a query only ever touches a handful of them.
        self._postings = postings
        self._decoded: dict[int, Postings] = {}
        self._forms = dict(forms or {})
        count = len(docs) or 1
        self._average_lengths = [
            sum(doc[1][f] for doc in docs) / count for f in range(len(self.fields))
        ]

    def __len__(self) -> int:
        return len(self._docs)

    def __repr__(self) -> str:
        return f"<SearchIndex {len(self)} docs, {len(self._vocab)} terms>"

    @property
    def vocabulary(self) -> list[str]:
        return self._vocab

    @property
    def doc_ids(self) -> list[str]:
        return [doc[0] for doc in self._docs]

    def doc_id(self, doc: int) -> str:
        return self._docs[doc][0]

    def stored(self, doc: int) -> dict[str, Any]:
        values = self._docs[doc][2]
        return {name: v for name, v in zip(self.store, values) if v is not None}

    def postings(self, term: str) -> Postings:
        """field index -> doc number -> positions, empty for unknown terms."""
        i = self._terms.get(term)
        if i is None:
            return {}
        decoded = self._decoded.get(i)
        if decoded is None:
            try:
                decoded = _decode_postings(self._postings[i])
            except (IndexError, TypeError):
                raise SearchError(
                    f"search index is corrupt (postings of {term!r})"
                ) from None
            self._decoded[i] = decoded
        return decoded

    def doc_frequency(self, term: str) -> int:
        return len(set().union(*self.postings(term).values()))

    def display_form(self, term: str) -> str:
        """The usual spelling behind an index term ("generation" for "generat")."""
        return self._forms.get(self._terms.get(term, -1), term)

    def expand_prefix(
        self, prefix: str, limit: int | None = MAX_PREFIX_TERMS
    ) -> list[str]:
        """Vocabulary terms a word starting with `prefix` could be indexed as."""
        terms = []
        i = bisect_left(self._vocab, prefix)
        while i < len(self._vocab) and self._vocab[i].startswith(prefix):
            if limit is not None and len(terms) >= limit:
                break
            terms.append(self._vocab[i])
            i += 1
        if self.analyzer.stemmer:
            # The vocabulary holds stems, so "generati" is a prefix of nothing
            # even though "generation" was indexed (as "generat"), and results
            # would come and go while someone types. Guess how the word might
            # end and see whether that stems to something we have.
            for ending in _COMPLETIONS:
                term = stem(prefix + ending)
                if term in self._terms and term not in terms:
                    terms.append(term)
        return terms

    def bm25f(self, tfs: Mapping[int, Mapping[int, float]]) -> dict[int, float]:
        """Score one query term from its per-field term frequencies.

        BM25F: lengths are normalised per field, the boosted frequencies are
        added up, and only then saturated, so a title hit is not just another
        body hit with a bigger number. Prefix, fuzzy and phrase clauses come
        through here as a single made-up term, which keeps a rare inflection
        from getting a huge idf of its own.
        """
        weighted: dict[int, float] = {}
        for f, docs in tfs.items():
            boost = self._boosts[f]
            average = self._average_lengths[f] or 1.0
            for doc, tf in docs.items():
                norm = 1 - self.b + self.b * self._docs[doc][1][f] / average
                weighted[doc] = weighted.get(doc, 0.0) + boost * tf / norm
        df = len(weighted)
        idf = math.log(1 + (len(self._docs) - df + 0.5) / (df + 0.5))
        return {doc: idf * w / (self.k1 + w) for doc, w in weighted.items()}

    def search(self, query: str | Query, limit: int | None = 10) -> list[SearchHit]:
        if isinstance(query, str):
            query = parse_query(query, self.fields)
        return evaluate(self, query, limit)

    def suggest(self, prefix: str, limit: int = 5) -> list[str]:
        """Complete a partial word, most widely used words first."""
        prefix = "".join(t.text for t in tokenize(prefix) if not t.joined)
        if not prefix or limit <= 0:
            return []
        terms = self.expand_prefix(prefix, limit=None)
        terms.sort(key=lambda term: (-self.doc_frequency(term), term))
        words: list[str] = []
        for term in terms:
            # stems make poor suggestions ("generat"), show a real word
            word = self.display_form(term)
            if word not in words:
                words.append(word)
                if len(words) == limit:
                    break
        return words

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": FORMAT_VERSION,
            "config": {
                "language": self.analyzer.language,
                "stemmer": self.analyzer.stemmer,
                "min_token_length": self.analyzer.min_token_length,
                "k1": self.k1,
                "b": self.b,
            },
            "stopwords": sorted(self.analyzer.stopwords),
            "fields": list(self.fields),
            "boosts": self._boosts,
            "store": list(self.store),
            "docs": self._docs,
            "vocab": self._vocab,
            "postings": self._postings,
            "forms": {str(i): form for i, form in sorted(self._forms.items())},
        }

    def to_json(self, compact: bool = True) -> str:
        data = self.to_dict()
        if compact:
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return json.dumps(data, ensure_ascii=False, indent=1)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SearchIndex:
        if not isinstance(data, Mapping):
            raise SearchError("search index data is not a JSON object")
        version = data.get("version")
        if version != FORMAT_VERSION:
            raise SearchError(
                f"unsupported search index format {version!r} "
                f"(this build reads version {FORMAT_VERSION})"
            )
        try:
            config = data["config"]
            stemmer = config.get("stemmer")
            if stemmer not in (None, "english"):
                raise SearchError(f"search index uses unknown stemmer {stemmer!r}")
            analyzer = Analyzer(
                config.get("language") or "",
                stopwords=data.get("stopwords") or False,
                stemming=False,
                min_token_length=config.get("min_token_length", 2),
            )
            # set directly: the index says what it was built with, whatever
            # the language tag would imply
            analyzer.stemmer = stemmer
            names, boosts = data["fields"], data["boosts"]
            vocab, postings = data["vocab"], data["postings"]
            if len(names) != len(boosts) or len(vocab) != len(postings):
                raise SearchError("search index is corrupt (table sizes disagree)")
            store = data.get("store", [])
            docs = [[doc[0], list(doc[1]), list(doc[2])] for doc in data["docs"]]
            for doc in docs:
                if len(doc[1]) != len(names) or len(doc[2]) != len(store):
                    raise SearchError(f"search index is corrupt (document {doc[0]!r})")
            return cls(
                fields=dict(zip(names, boosts)),
                store=store,
                docs=docs,
                vocab=list(vocab),
                postings=list(postings),
                analyzer=analyzer,
                forms={int(i): form for i, form in data.get("forms", {}).items()},
                k1=config.get("k1", 1.2),
                b=config.get("b", 0.75),
            )
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
            raise SearchError(f"search index is malformed: {exc!r}") from None

    @classmethod
    def from_json(cls, text: str | bytes) -> SearchIndex:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise SearchError(f"search index is not valid JSON: {exc}") from None
        return cls.from_dict(data)
