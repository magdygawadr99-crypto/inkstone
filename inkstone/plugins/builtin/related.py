"""Related pages: page.related, most similar first.

Two signals are added up. Shared tags count for more the rarer the tag is
(two posts tagged "sqlite" have more in common than two tagged "notes"),
and a TF-IDF comparison of titles and text catches the posts nobody tagged
properly.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from ...search import Analyzer
from ...utils import log
from ..base import Plugin
from ._common import date_key, front_matter, in_sections, setting
from ._text import plain, split_code

# a word in the title says more about a page than one somewhere in the text
_TITLE_BOOST = 3
# terms kept per page; the tail of a long post only adds noise and time
_MAX_TERMS = 64


class Related(Plugin):
    name = "related"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.limit = setting(self, "limit", 5, minimum=0)
        self.min_score = setting(self, "min_score", 0.1, minimum=0.0)
        self.tag_weight = setting(self, "tag_weight", 1.0, minimum=0.0)
        self.text_weight = setting(self, "text_weight", 0.5, minimum=0.0)
        self.taxonomies = setting(self, "taxonomies", ["tags"])
        # empty: every section, and pages outside of sections too
        self.sections = setting(self, "sections", [])
        self.same_section = setting(self, "same_section", False)
        # source path -> (text, title, term counts) as of the last build
        self._words: dict[str, tuple[str, str, Counter]] = {}

    def content_loaded(self, site) -> None:
        for page in site.pages:
            page.related = []
        pages = sorted(self._candidates(site), key=lambda page: page.url)
        if len(pages) < 2 or not self.limit:
            return
        scores = self.score(pages, getattr(site, "language", "en"))
        for index, page in enumerate(pages):
            wanted = front_matter(page, "related")
            if wanted is False:
                continue
            picked = self._by_hand(site, page, wanted)
            ranked = []
            for other, score in scores[index].items():
                if score >= self.min_score and score > 0:
                    # best first; newer wins a tie, then the title decides
                    there = pages[other]
                    key = (-round(score, 6), -date_key(there), there.title, other)
                    ranked.append(key)
            for _score, _date, _title, other in sorted(ranked):
                if pages[other] not in picked:
                    picked.append(pages[other])
            page.related = picked[: self.limit]

    def _candidates(self, site) -> list:
        if not self.sections:
            return list(site.pages)
        return [page for page in site.pages if in_sections(page, self.sections)]

    def _by_hand(self, site, page, wanted) -> list:
        """Pages named in the front matter (``related: [posts/other.md]``)."""
        if not isinstance(wanted, (list, tuple)):
            return []
        picked = []
        for path in wanted:
            other = site.get_page(str(path))
            if other is None:
                source = getattr(page, "source_path", None) or page.url
                log.warning("%s: related page %r not found", source, path)
            elif other is not page and other not in picked:
                picked.append(other)
        return picked

    def score(self, pages: list, language: str = "en") -> list[dict[int, float]]:
        """Similarity of every page to every other: one {index: score} per page."""
        scores: list[dict[int, float]] = [defaultdict(float) for _ in pages]
        signals = []
        if self.tag_weight:
            signals.append((self.tag_weight, self._tag_similarity(pages)))
        if self.text_weight:
            signals.append((self.text_weight, self._text_similarity(pages, language)))
        for weight, pairs in signals:
            for (a, b), value in sorted(pairs.items()):
                if self.same_section and pages[a].section is not pages[b].section:
                    continue
                scores[a][b] += weight * value
                scores[b][a] += weight * value
        return scores

    def _terms(self, page) -> set[str]:
        terms = set()
        taxonomies = getattr(page, "taxonomies", None) or {}
        for name in self.taxonomies:
            values = taxonomies.get(name)
            if values is None and name == "tags":
                values = getattr(page, "tags", None)
            for value in values or ():
                terms.add(f"{name}:{str(value).strip().lower()}")
        return terms

    def _tag_similarity(self, pages: list) -> dict[tuple[int, int], float]:
        """Weighted Jaccard over taxonomy terms, each term weighted by rarity."""
        terms = [self._terms(page) for page in pages]
        users: dict[str, list[int]] = defaultdict(list)
        for index, mine in enumerate(terms):
            for term in sorted(mine):
                users[term].append(index)
        count = len(pages)
        idf = {term: math.log(1 + count / len(found)) for term, found in users.items()}
        weight = [sum(idf[term] for term in sorted(mine)) for mine in terms]

        shared: dict[tuple[int, int], float] = defaultdict(float)
        for term in sorted(users):
            found = users[term]
            for position, a in enumerate(found):
                for b in found[position + 1 :]:
                    shared[(a, b)] += idf[term]
        return {
            (a, b): value / (weight[a] + weight[b] - value)
            for (a, b), value in shared.items()
        }

    def _text_similarity(self, pages: list, language: str) -> dict:
        """Cosine similarity of TF-IDF vectors built from title and body."""
        # the search index's idea of a word: folded, stemmed (English only),
        # stopwords dropped where there is a list for the language
        analyzer = Analyzer(language or "en")
        counts = []
        seen = {}
        for page in pages:
            key = getattr(page, "source_path", None) or page.url
            raw, title = page.raw or "", page.title or ""
            known = self._words.get(key)
            if known is None or known[:2] != (raw, title):
                words = Counter(analyzer.terms(plain(split_code(raw)[0])))
                for term in analyzer.terms(title):
                    words[term] += _TITLE_BOOST
                known = (raw, title, words)
            seen[key] = known
            counts.append(known[2])
        # Tokenising is most of the work here, and `inkstone serve` comes
        # back after every save with all pages but one unchanged.
        self._words = seen
        frequency: Counter = Counter()
        for words in counts:
            frequency.update(words.keys())
        count = len(pages)
        # On a site of some size, words that most pages use weigh next to
        # nothing and make for the longest lists to multiply out.
        common = count if count <= 20 else count // 2

        postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        idf = {term: math.log(1 + count / seen) for term, seen in frequency.items()}
        for index, words in enumerate(counts):
            weights = {
                term: (1 + math.log(words[term])) * idf[term] for term in sorted(words)
            }
            # the length is that of the whole vector, but only terms another
            # page uses as well can ever contribute to a product
            norm = math.sqrt(sum(value * value for value in weights.values()))
            shared = [term for term in weights if 1 < frequency[term] <= common]
            shared.sort(key=lambda term: (-weights[term], term))
            for term in shared[:_MAX_TERMS]:
                postings[term].append((index, weights[term] / norm))

        dots: dict[tuple[int, int], float] = defaultdict(float)
        for term in sorted(postings):
            found = postings[term]
            for position, (a, left) in enumerate(found):
                for b, right in found[position + 1 :]:
                    dots[(a, b)] += left * right
        return dict(dots)
