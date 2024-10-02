from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Collection, Mapping

from .tokenizer import Token, tokenize

if TYPE_CHECKING:
    from .index import SearchIndex

TERM = "term"
PHRASE = "phrase"
PREFIX = "prefix"
FUZZY = "fuzzy"

SHOULD = "should"
MUST = "must"
MUST_NOT = "must_not"

# How much a one-edit-away term counts compared to the term as typed.
FUZZY_WEIGHT = 0.5
MAX_FUZZY_TERMS = 50

_FIELD = re.compile(r"([^\W\d][\w.-]*):(?=[^\s/])")
_FUZZY_SUFFIX = re.compile(r"~[0-9]?$")
# Phones and word processors like to "help" with quotes.
_QUOTES = str.maketrans(dict.fromkeys("“”„«»", '"'))


@dataclass(frozen=True)
class Clause:
    kind: str
    text: str
    field: str | None = None
    occur: str = SHOULD

    def __str__(self) -> str:
        sign = {MUST: "+", MUST_NOT: "-"}.get(self.occur, "")
        scope = f"{self.field}:" if self.field else ""
        if self.kind == PHRASE:
            return f'{sign}{scope}"{self.text}"'
        suffix = {PREFIX: "*", FUZZY: "~"}.get(self.kind, "")
        return f"{sign}{scope}{self.text}{suffix}"


@dataclass(frozen=True)
class Query:
    clauses: tuple[Clause, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.clauses)

    def __str__(self) -> str:
        return " ".join(str(clause) for clause in self.clauses)


@dataclass
class SearchHit:
    doc_id: str
    score: float
    stored: dict[str, Any]
    # field name -> index terms that matched there, handy for highlighting
    matches: dict[str, list[str]]

    @property
    def terms(self) -> set[str]:
        return {term for terms in self.matches.values() for term in terms}


def _classify(word: str) -> tuple[str, str]:
    if len(word) > 1 and word.endswith("*"):
        return word.rstrip("*"), PREFIX
    match = _FUZZY_SUFFIX.search(word)
    if match and match.start() > 0:
        # Only distance 1 is implemented; ~2 and up quietly mean the same.
        kind = TERM if match.group() == "~0" else FUZZY
        return word[: match.start()], kind
    return word, TERM


def parse_query(text: str, fields: Collection[str] | None = None) -> Query:
    """Parse a search box query.

    Supports bare terms, "quoted phrases", +required and -excluded clauses,
    field:term, a trailing * for prefixes and a trailing ~ for fuzzy matches.
    Never raises on odd input: this is what users type, so anything that does
    not parse as syntax is treated as text.

    With `fields` given, only those names count as a field prefix, so
    "note: something" stays plain text.
    """
    text = text.translate(_QUOTES)
    clauses = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        occur = SHOULD
        if text[i] in "+-" and i + 1 < n and not text[i + 1].isspace():
            occur = MUST if text[i] == "+" else MUST_NOT
            i += 1
        field = None
        match = _FIELD.match(text, i)
        if match and (fields is None or match.group(1) in fields):
            field = match.group(1)
            i = match.end()
        if text[i] == '"':
            end = text.find('"', i + 1)
            if end < 0:
                # no closing quote: the rest of the input is the phrase
                end = n
            body, kind = text[i + 1 : end].strip(), PHRASE
            i = end + 1
        else:
            end = i
            while end < n and not text[end].isspace() and text[end] != '"':
                end += 1
            body, kind = _classify(text[i:end])
            i = end
        if any(ch.isalnum() for ch in body):
            clauses.append(Clause(kind, body, field, occur))
    return Query(tuple(clauses))


class _Match:
    """What a single clause found."""

    def __init__(self) -> None:
        # field index -> doc -> (weighted) term frequency
        self.tfs: dict[int, dict[int, float]] = {}
        # (field index, term, docs it occurs in), for SearchHit.matches
        self.terms: list[tuple[int, str, Collection[int]]] = []

    def docs(self) -> set[int]:
        return set().union(*self.tfs.values())


def _term_match(
    index: SearchIndex, fields: list[int], weights: Mapping[str, float]
) -> _Match:
    match = _Match()
    for term, weight in weights.items():
        postings = index.postings(term)
        for f in fields:
            docs = postings.get(f)
            if not docs:
                continue
            tfs = match.tfs.setdefault(f, {})
            for doc, positions in docs.items():
                tfs[doc] = tfs.get(doc, 0.0) + weight * len(positions)
            match.terms.append((f, term, docs))
    return match


def _phrase_match(index: SearchIndex, fields: list[int], tokens: list[Token]) -> _Match:
    terms = [token.text for token in tokens]
    # Offsets rather than "next position": stopwords were dropped from both
    # the index and the query but still count as a step.
    offsets = [token.position - tokens[0].position for token in tokens]
    postings = [index.postings(term) for term in terms]
    match = _Match()
    for f in fields:
        lists = [by_field.get(f) for by_field in postings]
        if not all(lists):
            continue
        found = {}
        for doc in set(lists[0]).intersection(*lists[1:]):
            rest = [set(docs[doc]) for docs in lists[1:]]
            count = sum(
                all(start + offset in seen for offset, seen in zip(offsets[1:], rest))
                for start in lists[0][doc]
            )
            if count:
                found[doc] = float(count)
        if found:
            match.tfs[f] = found
            for term in dict.fromkeys(terms):
                match.terms.append((f, term, found))
    return match


def _merge_max(match: _Match, other: _Match) -> _Match:
    for f, docs in other.tfs.items():
        tfs = match.tfs.setdefault(f, {})
        for doc, tf in docs.items():
            if tf > tfs.get(doc, 0.0):
                tfs[doc] = tf
    match.terms.extend(other.terms)
    return match


def _within_one_edit(a: str, b: str) -> bool:
    """True if one insertion, deletion, substitution or swap turns a into b."""
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) != len(b):
        return a[i:] == b[i + 1 :]
    if a[i + 1 :] == b[i + 1 :]:
        return True
    return a[i : i + 2] == b[i : i + 2][::-1] and a[i + 2 :] == b[i + 2 :]


def _fuzzy_terms(index: SearchIndex, word: str, term: str) -> dict[str, float]:
    weights = {term: 1.0}
    if len(word) < 3:
        # half the vocabulary is one edit away from a two-letter word
        return weights
    # A misspelt word rarely stems the way the real one does ("wordpres"
    # comes out as "wordpr"), so comparing stem to stem misses most typos.
    # Try the word as typed as well, against both the stems and the spelling
    # kept for each of them.
    # XXX only one spelling is kept per stem, so "generaton" finds
    # "generation" only if that happens to be the common form on the site.
    typed = {word, term}
    for candidate in index.vocabulary:
        if candidate == term:
            continue
        spellings = {candidate, index.display_form(candidate)}
        if any(
            abs(len(a) - len(b)) <= 1 and _within_one_edit(a, b)
            for a in typed
            for b in spellings
        ):
            weights[candidate] = FUZZY_WEIGHT
            if len(weights) > MAX_FUZZY_TERMS:
                break
    return weights


def _match_clause(index: SearchIndex, clause: Clause) -> _Match | None:
    """None means there is nothing searchable in the clause (all stopwords)."""
    if clause.field is None:
        fields = list(range(len(index.fields)))
    elif clause.field in index.fields:
        fields = [list(index.fields).index(clause.field)]
    else:
        return _Match()

    analyzer = index.analyzer
    if clause.kind in (PREFIX, FUZZY):
        word = "".join(t.text for t in tokenize(clause.text) if not t.joined)
        if not word:
            return None
        if clause.kind == PREFIX:
            weights = dict.fromkeys(index.expand_prefix(word), 1.0)
            return _term_match(index, fields, weights)
        term = analyzer.term(word)
        if term is None:
            return None
        return _term_match(index, fields, _fuzzy_terms(index, word, term))

    tokens = analyzer.analyze(clause.text)
    if not tokens:
        return None
    parts = [token for token in tokens if not token.joined]
    wholes = [token for token in tokens if token.joined]
    if not parts:
        return _term_match(index, fields, {wholes[0].text: 1.0})
    if len(parts) == 1:
        match = _term_match(index, fields, {parts[0].text: 1.0})
    else:
        match = _phrase_match(index, fields, parts)
    if clause.kind == TERM and len(wholes) == 1:
        # A bare well-known should find "well known" and "wellknown" too.
        # max() instead of a sum so "well-known" itself is not counted twice.
        whole = wholes[0]
        if whole.start <= parts[0].start and whole.end >= parts[-1].end:
            match = _merge_max(match, _term_match(index, fields, {whole.text: 1.0}))
    return match


def evaluate(
    index: SearchIndex, query: Query, limit: int | None = 10
) -> list[SearchHit]:
    """Run a parsed query; best hits first.

    Plain clauses are OR-ed and only add to the score. Once there is a +clause
    every hit has to match all of the +clauses. A query made only of
    -exclusions matches nothing.
    """
    required: list[_Match] = []
    optional: list[_Match] = []
    excluded: set[int] = set()
    for clause in query.clauses:
        match = _match_clause(index, clause)
        if match is None:
            continue
        if clause.occur == MUST_NOT:
            excluded |= match.docs()
        elif clause.occur == MUST:
            required.append(match)
        else:
            optional.append(match)

    matched = required + optional
    scored = [index.bm25f(match.tfs) for match in matched]
    if not scored:
        return []
    if required:
        candidates = set(scored[0]).intersection(*scored[1 : len(required)])
    else:
        candidates = set().union(*scored)
    totals = {
        doc: sum(scores.get(doc, 0.0) for scores in scored)
        for doc in candidates - excluded
    }
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        ranked = ranked[: max(limit, 0)]

    names = list(index.fields)
    hits = []
    for doc, score in ranked:
        found: dict[str, set[str]] = {}
        for match in matched:
            for f, term, docs in match.terms:
                if doc in docs:
                    found.setdefault(names[f], set()).add(term)
        matches = {name: sorted(found[name]) for name in names if name in found}
        hits.append(SearchHit(index.doc_id(doc), score, index.stored(doc), matches))
    return hits
