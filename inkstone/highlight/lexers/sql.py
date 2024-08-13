from __future__ import annotations

import re

from ..lexer import RegexLexer, words
from ..registry import register
from ..token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Whitespace,
)

# A blend of standard SQL with the PostgreSQL, MySQL and SQLite words that
# come up most. Dialect-specific lexers would be nicer but nobody writes
# ```postgresql on a fence anyway.
_KEYWORDS = """
    abort action add after all alter always analyze and any as asc attach
    autoincrement before begin between by cascade case cast check collate
    column commit conflict constraint create cross current current_date
    current_time current_timestamp database default deferrable deferred delete
    desc detach distinct do drop each else end escape except exclude exists
    explain extension fetch filter first following for foreign from full
    function generated grant group having if ignore ilike immediate in index
    initially inner insert instead intersect into is isnull join key language
    last lateral left like limit materialized natural no not nothing notnull
    nulls of offset on only or order outer over partition plan pragma
    preceding primary procedure range recursive references regexp reindex
    release rename replace restrict returning returns revoke right rollback
    row rows savepoint schema select sequence set similar some table temp
    temporary then ties to transaction trigger truncate unbounded union unique
    update using vacuum values view virtual when where window with within
    without
""".split()

_TYPES = """
    bigint bigserial binary bit blob bool boolean bytea char character clob
    date datetime decimal double enum float float4 float8 inet int int2 int4
    int8 integer interval json jsonb longtext mediumint mediumtext money nchar
    numeric nvarchar precision real serial smallint smallserial text time
    timestamp timestamptz tinyint tinytext tsvector uuid varbinary varchar
    varying xml zone
""".split()

# Only treated as functions when a parenthesis follows, so columns called
# "count" or "year" keep their plain colour.
_FUNCTIONS = """
    abs array_agg avg ceil ceiling char_length coalesce concat count
    cume_dist date_part date_trunc dense_rank extract first_value floor
    generate_series greatest group_concat ifnull json_agg json_build_object
    lag last_value lead least length lower ltrim max min mod now nth_value
    ntile nullif percent_rank position power random rank regexp_replace
    replace round row_number rtrim sqrt string_agg strftime substr substring
    sum to_char to_date to_timestamp trim unnest upper year month day
""".split()


@register
class SqlLexer(RegexLexer):
    name = "sql"
    aliases = ("postgresql", "postgres", "psql", "mysql", "sqlite", "sqlite3")
    extensions = (".sql",)

    flags = re.MULTILINE | re.IGNORECASE

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"--.*$", Comment.Single),
            (r"/\*", Comment.Multiline, "comment"),
            (r"[eEbBxXnN]?'", String, "string"),
            (r'"(?:""|[^"])*"', Name),
            (r"`(?:``|[^`])*`", Name),
            # PostgreSQL dollar quoting: $$ ... $$ or $tag$ ... $tag$
            (r"(\$\w*\$)(?:.|\n)*?\1", String),
            (r"\d+\.\d*(?:e[+-]?\d+)?|\.\d+(?:e[+-]?\d+)?|\d+e[+-]?\d+", Number.Float),
            (r"0x[0-9a-f]+", Number.Hex),
            (r"\d+", Number.Integer),
            # bind parameters: ?, $1, :name, @name, %s, %(name)s
            (r"\?|\$\d+|(?<!:):[a-z_]\w*|@@?[a-z_]\w*|%s|%\(\w+\)s", Name.Variable),
            (r"(?:true|false|null|unknown)\b", Keyword.Constant),
            (words(_FUNCTIONS, suffix=r"(?=\s*\()"), Name.Function),
            (words(_KEYWORDS, suffix=r"\b"), Keyword),
            (words(_TYPES, suffix=r"\b"), Keyword.Type),
            (r"[a-z_][\w$]*", Name),
            (r"::|<>|!=|<=|>=|\|\||->>?|#>>?|@>|<@|@@|[-+*/%=<>~!^&|]", Operator),
            (r"[()\[\];,.:]", Punctuation),
        ],
        # /* comments /* nest */ in PostgreSQL */
        "comment": [
            (r"[^*/]+", Comment.Multiline),
            (r"/\*", Comment.Multiline, "#push"),
            (r"\*/", Comment.Multiline, "#pop"),
            (r"[*/]", Comment.Multiline),
        ],
        "string": [
            (r"''", String.Escape),
            (r"'", String, "#pop"),
            (r"[^']+", String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        patterns = (
            r"\bselect\b[^;]*\bfrom\b",
            r"\bcreate\s+(?:temp\w*\s+)?(?:table|index|view)\b",
            r"\binsert\s+into\b[^;]*\bvalues\b",
            r"\bupdate\s+\w+\s+set\b",
            r"\bdelete\s+from\b",
        )
        hits = sum(bool(re.search(p, code, re.I)) for p in patterns)
        if not hits:
            return 0.0
        # shouting is a strong hint; lower case could be prose about SQL
        shouted = re.search(r"\b(?:SELECT|CREATE|INSERT|UPDATE|DELETE)\b", code)
        return min(0.4 + 0.15 * hits, 0.8) if shouted else 0.35
