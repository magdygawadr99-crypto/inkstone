"""Build-time full-text index and the pieces the browser client mirrors."""

from __future__ import annotations

from pathlib import Path

from .analyzer import Analyzer
from .errors import SearchError
from .index import FORMAT_VERSION, IndexBuilder, SearchIndex
from .query import Clause, Query, SearchHit, parse_query
from .snippets import highlight, snippet
from .stemmer import stem
from .stopwords import get_stopwords, register_stopwords
from .tokenizer import Token, fold, tokenize

CLIENT_SCRIPT = Path(__file__).parent / "client" / "search.js"

__all__ = [
    "CLIENT_SCRIPT",
    "FORMAT_VERSION",
    "Analyzer",
    "Clause",
    "IndexBuilder",
    "Query",
    "SearchError",
    "SearchHit",
    "SearchIndex",
    "Token",
    "client_script",
    "fold",
    "get_stopwords",
    "highlight",
    "parse_query",
    "register_stopwords",
    "snippet",
    "stem",
    "tokenize",
]


def client_script() -> str:
    """Source of the browser client, to be shipped next to the index."""
    return CLIENT_SCRIPT.read_text(encoding="utf-8")
