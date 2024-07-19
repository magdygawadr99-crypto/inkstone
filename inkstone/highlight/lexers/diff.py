from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups
from ..registry import register
from ..token import Comment, Generic, Punctuation, Text, Whitespace


@register
class DiffLexer(RegexLexer):
    name = "diff"
    aliases = ("patch", "udiff")
    extensions = (".diff", ".patch")

    tokens = {
        "root": [
            (r"\n", Whitespace),
            # "--- a/x" directly above "+++ b/x" is a file header. On its own
            # a line starting with "--- " is just a removed line (a deleted
            # SQL comment, say).
            (
                r"^(--- .*)(\n)(\+\+\+ .*)$",
                bygroups(Generic.Heading, Whitespace, Generic.Heading),
            ),
            # context diffs: line ranges, then the "*** old / --- new" header
            (
                r"^(?:\*\*\* \d+(?:,\d+)? \*\*\*\*|--- \d+(?:,\d+)? ----)$",
                Generic.Subheading,
            ),
            (r"^\*{15}.*$", Generic.Subheading),
            (
                r"^(\*\*\* .*)(\n)(--- .*)$",
                bygroups(Generic.Heading, Whitespace, Generic.Heading),
            ),
            (
                r"^(?:diff |index |Index: |Only in |Binary files |={10,}"
                r"|(?:new|deleted) file mode |(?:old|new) mode "
                r"|(?:similarity|dissimilarity) index |(?:rename|copy) (?:from|to) "
                r"|commit [0-9a-f]{7,40}\b).*$",
                Generic.Heading,
            ),
            (
                r"^(@@@? .*? @@@?)(.*)$",
                bygroups(Generic.Subheading, Text),
            ),
            # plain diffs: 3c3, 5a6,7, 2,4d1, with --- between the two sides
            (r"^\d+(?:,\d+)?[acd]\d+(?:,\d+)?$", Generic.Subheading),
            (r"^---$", Punctuation),
            (r"^\+.*$", Generic.Inserted),
            (r"^-.*$", Generic.Deleted),
            (r"^>(?: .*)?$", Generic.Inserted),
            (r"^<(?: .*)?$", Generic.Deleted),
            (r"^!.*$", Generic.Strong),
            (r"^\\ .*$", Comment),
            (r".+$", Text),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        if re.search(r"^diff --git a/", code, re.M):
            return 0.95
        if re.search(r"^--- .*\n\+\+\+ ", code, re.M):
            return 0.9
        if re.search(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", code, re.M):
            return 0.8
        return 0.0
