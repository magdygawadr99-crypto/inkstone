from __future__ import annotations

from typing import Iterable

from .stemmer import stem
from .stopwords import get_stopwords, primary_language
from .tokenizer import Token, fold, tokenize


class Analyzer:
    """The tokenizer plus the filters that turn tokens into index terms.

    Indexing and querying have to agree on this, so an index carries its
    analyzer settings with it.
    """

    def __init__(
        self,
        language: str = "en",
        *,
        stopwords: bool | Iterable[str] = True,
        stemming: bool = True,
        min_token_length: int = 2,
    ):
        self.language = language
        if stopwords is True:
            self.stopwords = get_stopwords(language)
        elif not stopwords:
            self.stopwords = frozenset()
        else:
            self.stopwords = frozenset(fold(word) for word in stopwords)
        # English is the only stemmer there is. Other languages are indexed
        # unstemmed rather than refused, which still makes a usable search.
        english = primary_language(language) == "en"
        self.stemmer = "english" if stemming and english else None
        self.min_token_length = max(int(min_token_length), 1)

    def term(self, word: str) -> str | None:
        """Index term for an already tokenized word, None if it is dropped."""
        if len(word) < self.min_token_length or word in self.stopwords:
            return None
        return stem(word) if self.stemmer else word

    def analyze(self, text: str) -> list[Token]:
        """Tokens with their text replaced by index terms.

        Dropped words leave a hole in the position sequence, which is what
        lets a phrase query step over stopwords.
        """
        tokens = []
        for token in tokenize(text):
            term = self.term(token.text)
            if term is not None:
                tokens.append(token._replace(text=term))
        return tokens

    def terms(self, text: str) -> list[str]:
        return [token.text for token in self.analyze(text)]

    def __repr__(self) -> str:
        return (
            f"Analyzer({self.language!r}, stopwords={len(self.stopwords)}, "
            f"stemmer={self.stemmer!r}, min_token_length={self.min_token_length})"
        )
