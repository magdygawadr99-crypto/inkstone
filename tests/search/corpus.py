from __future__ import annotations

from datetime import date

from inkstone.search import IndexBuilder, SearchIndex

FIELDS = {"title": 3.0, "tags": 2.0, "body": 1.0}
STORE = ("title", "url", "summary", "date")

DOCS = [
    (
        "static-sites",
        {
            "title": "Static site generators compared",
            "tags": ["python", "static-site"],
            "body": (
                "A static site generator turns Markdown files into plain HTML. "
                "No database, no WordPress plugins to update, just files. "
                "This post compares a few generators written in Python."
            ),
        },
        {"summary": "Which static site generator should you pick?"},
    ),
    (
        "markdown-tips",
        {
            "title": "Markdown tips and tricks",
            "tags": ["markdown", "writing"],
            "body": (
                "Writing in Markdown keeps your hands on the keyboard. Here is "
                "the exact phrase people search for: footnotes are underrated. "
                "Tables are harder than they look."
            ),
        },
        {"summary": "Footnotes, tables and other things worth knowing."},
    ),
    (
        "leaving-wordpress",
        {
            "title": "Leaving WordPress",
            "tags": ["wordpress", "migration"],
            "body": (
                "Moving a ten year old WordPress blog to a static site took a "
                "weekend. Exporting the posts was easy, the comments were not."
            ),
        },
        {"summary": "Ten years of posts, one weekend."},
    ),
    (
        "python-generators",
        {
            "title": "Python generators explained",
            "tags": ["python"],
            "body": (
                "Generators produce values lazily. A generator function uses "
                "yield instead of return, and the state-of-the-art way to chain "
                "them is itertools."
            ),
        },
        {"summary": "yield, send and friends."},
    ),
    (
        "search",
        {
            "title": "Full-text search without a server",
            "tags": ["search", "javascript"],
            "body": (
                "The index is built at build time and shipped as JSON. A small "
                "script tokenizes the query, stems each word and ranks the "
                "pages with BM25."
            ),
        },
        {"summary": "How the search box on this site works."},
    ),
    (
        "creme-brulee",
        {
            "title": "Crème brûlée at the café",
            "tags": ["cooking"],
            "body": (
                "Nothing to do with code. Caramelised sugar, vanilla and a "
                "blowtorch; naïve attempts end in scrambled eggs."
            ),
        },
        {"summary": "A dessert & a blowtorch."},
    ),
    (
        "deploying",
        {
            "title": "Deploying with rsync",
            "tags": ["deployment", "shell"],
            "body": (
                "The publish_site script calls rsync over SSH. Set deployHost "
                "in config.toml; HTMLMinifier is optional. Hosting costs about "
                "3.50 a month."
            ),
        },
        {"summary": "One script, one command."},
    ),
]


def build_index(**options) -> SearchIndex:
    builder = IndexBuilder(FIELDS, store=STORE, **options)
    for number, (doc_id, fields, stored) in enumerate(DOCS, 1):
        stored = {"url": f"/{doc_id}/", "date": date(2024, number, 1), **stored}
        builder.add(doc_id, fields, stored=stored)
    return builder.build()


def small_index(
    docs: dict[str, dict], fields=("title", "body"), **options
) -> SearchIndex:
    """A throwaway index with stemming and stopwords off unless asked for."""
    options.setdefault("stemming", False)
    options.setdefault("stopwords", False)
    builder = IndexBuilder(fields, **options)
    for doc_id, doc in docs.items():
        builder.add(doc_id, doc)
    return builder.build()


def ids(hits) -> list[str]:
    return [hit.doc_id for hit in hits]
