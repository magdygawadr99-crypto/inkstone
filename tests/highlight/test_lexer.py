from __future__ import annotations

import re

import pytest

from inkstone.highlight import HighlightError, RegexLexer
from inkstone.highlight.lexer import (
    TextLexer,
    bygroups,
    default,
    include,
    inherit,
    this,
    using,
    words,
)
from inkstone.highlight.token import (
    Comment,
    Error,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
    Whitespace,
)


def tokens(lexer_class, code):
    return list(lexer_class().tokenize(code))


def joined(lexer_class, code):
    return "".join(text for _, text in tokens(lexer_class, code))


class Calc(RegexLexer):
    tokens = {
        "root": [
            include("space"),
            (r"\d+", Number),
            (r"[-+*/]", Operator),
            (r"\(", Punctuation, "parens"),
            (r'"', String, "string"),
            (r"(let)(\s+)([a-z]+)", bygroups(Keyword, Whitespace, Name.Variable)),
            (r"[a-z]+", Name),
        ],
        "space": [
            (r"\s+", Whitespace),
            (r"#.*$", Comment),
        ],
        "parens": [
            (r"\)", Punctuation, "#pop"),
            include("root"),
        ],
        "string": [
            (r'"', String, "#pop"),
            (r"\\.", String.Escape),
            (r'[^"\\\n]+', String),
        ],
    }


def test_simple_rules_produce_typed_tokens():
    assert tokens(Calc, "1 + x") == [
        (Number, "1"),
        (Whitespace, " "),
        (Operator, "+"),
        (Whitespace, " "),
        (Name, "x"),
    ]


def test_empty_input_gives_no_tokens():
    assert tokens(Calc, "") == []


def test_state_is_pushed_and_popped():
    result = tokens(Calc, '"a\\"b" c')
    assert result[:5] == [
        (String, '"'),
        (String, "a"),
        (String.Escape, '\\"'),
        (String, "b"),
        (String, '"'),
    ]
    assert result[-1] == (Name, "c")


def test_included_rules_apply_inside_other_states():
    assert (Comment, "# note") in tokens(Calc, "(1 # note\n)")


def test_bygroups_assigns_one_type_per_group():
    assert tokens(Calc, "let  abc") == [
        (Keyword, "let"),
        (Whitespace, "  "),
        (Name.Variable, "abc"),
    ]


def test_unmatched_characters_become_error_tokens_one_at_a_time():
    assert tokens(Calc, "1 ?! 2") == [
        (Number, "1"),
        (Whitespace, " "),
        (Error, "?"),
        (Error, "!"),
        (Whitespace, " "),
        (Number, "2"),
    ]


def test_unmatched_newline_resets_to_root():
    # the string is never closed; the next line must lex normally again
    result = tokens(Calc, '"abc\n1 + 2')
    assert result[:3] == [(String, '"'), (String, "abc"), (Whitespace, "\n")]
    assert result[3] == (Number, "1")


def test_unbalanced_closers_never_pop_root():
    assert joined(Calc, "1))))") == "1))))"
    assert tokens(Calc, "(1))")[-1] == (Error, ")")


@pytest.mark.parametrize(
    "code",
    [
        "",
        "1",
        "((1 + (2 * x)) # c\n",
        '"unterminated',
        "\\\\ ??? \x00 \xe9 \U0001f600",
        "\n\n\n",
    ],
)
def test_token_texts_concatenate_to_the_input(code):
    assert joined(Calc, code) == code


class Nested(RegexLexer):
    tokens = {
        "root": [
            (r"<<", Punctuation, ("outer", "inner")),
            (r"<", Punctuation, "outer"),
            (r"\[", Punctuation, "bracket"),
            (r"\w+", Name),
            (r"\s+", Whitespace),
        ],
        "outer": [
            (r">", Punctuation, "#pop"),
            (r"\w+", Keyword),
        ],
        "inner": [
            (r">>", Punctuation, "#pop:2"),
            (r">", Punctuation, "#pop"),
            (r"\w+", String),
        ],
        "bracket": [
            (r"\[", Punctuation, "#push"),
            (r"\]", Punctuation, "#pop"),
            (r"\w+", Number),
            default("#pop"),
        ],
    }


def test_tuple_transition_pushes_several_states():
    assert tokens(Nested, "<<a>b>c") == [
        (Punctuation, "<<"),
        (String, "a"),
        (Punctuation, ">"),
        (Keyword, "b"),
        (Punctuation, ">"),
        (Name, "c"),
    ]


def test_pop_with_count_leaves_several_states_at_once():
    assert tokens(Nested, "<<a>>c")[-1] == (Name, "c")


def test_push_reenters_the_current_state():
    result = [pair for pair in tokens(Nested, "[a[b]c]d") if pair[0] is not Punctuation]
    assert result == [(Number, "a"), (Number, "b"), (Number, "c"), (Name, "d")]


def test_default_leaves_a_state_without_consuming():
    # the space isn't matched in "bracket", so default pops and root takes it
    assert tokens(Nested, "[a b") == [
        (Punctuation, "["),
        (Number, "a"),
        (Whitespace, " "),
        (Name, "b"),
    ]


class Embedding(RegexLexer):
    tokens = {
        "root": [
            (r"(\{)([^}]*)(\})", bygroups(Punctuation, using(Calc), Punctuation)),
            (
                r"(\[)([^\]]*)(\])",
                bygroups(Punctuation, using(this, state="shout"), Punctuation),
            ),
            (r"[a-z]+", Name),
            (r"\s+", Whitespace),
        ],
        "shout": [
            (r"[a-z]+", Keyword),
            (r"\s+", Whitespace),
        ],
    }


def test_using_hands_a_group_to_another_lexer():
    assert tokens(Embedding, "{1+x} y") == [
        (Punctuation, "{"),
        (Number, "1"),
        (Operator, "+"),
        (Name, "x"),
        (Punctuation, "}"),
        (Whitespace, " "),
        (Name, "y"),
    ]


def test_using_this_can_start_in_another_state():
    assert tokens(Embedding, "[ab cd] ef") == [
        (Punctuation, "["),
        (Keyword, "ab"),
        (Whitespace, " "),
        (Keyword, "cd"),
        (Punctuation, "]"),
        (Whitespace, " "),
        (Name, "ef"),
    ]


def test_using_reports_positions_relative_to_the_whole_text():
    positions = [pos for pos, _, _ in Embedding().scan("ab {1+2}")]
    assert positions == [0, 2, 3, 4, 5, 6, 7]


def test_using_a_registered_language_by_name():
    class Wrapper(RegexLexer):
        tokens = {"root": [(r"(py:)(.*)", bygroups(Keyword, using("python")))]}

    assert (Keyword.Declaration, "def") in tokens(Wrapper, "py:def f(): pass")


def test_bygroups_never_drops_text_outside_its_groups():
    class Sloppy(RegexLexer):
        tokens = {"root": [(r"(a)-(b)?-(c)!", bygroups(Name, Keyword, None))]}

    assert tokens(Sloppy, "a--c!") == [
        (Name, "a"),
        (Text, "--"),
        (Text, "c"),
        (Text, "!"),
    ]


def test_bygroups_skips_groups_nested_in_an_earlier_one():
    class NestedGroups(RegexLexer):
        tokens = {"root": [(r"((a)(b))(c)", bygroups(Name, Error, Error, Keyword))]}

    assert tokens(NestedGroups, "abc") == [(Name, "ab"), (Keyword, "c")]


class Base(RegexLexer):
    tokens = {
        "root": [
            (r"[a-z]+", Name),
            (r"\s+", Whitespace),
            include("numbers"),
        ],
        "numbers": [(r"\d+", Number)],
    }


class Extended(Base):
    tokens = {
        "root": [
            (r"if\b", Keyword),
            inherit,
            (r"[A-Z]+", Name.Constant),
        ],
    }


class Replaced(Base):
    tokens = {"numbers": [(r"\d+", Number.Integer)]}


def test_inherit_splices_the_parent_rules_in_place():
    assert tokens(Extended, "if x 1 Y") == [
        (Keyword, "if"),
        (Whitespace, " "),
        (Name, "x"),
        (Whitespace, " "),
        (Number, "1"),
        (Whitespace, " "),
        (Name.Constant, "Y"),
    ]


def test_subclass_can_replace_a_single_state():
    assert tokens(Replaced, "a 1")[-1] == (Number.Integer, "1")


def test_subclassing_leaves_the_parent_untouched():
    tokens(Extended, "if")
    tokens(Replaced, "1")
    assert tokens(Base, "if 1") == [(Name, "if"), (Whitespace, " "), (Number, "1")]


def test_flags_apply_to_every_pattern():
    class Shouty(RegexLexer):
        flags = re.IGNORECASE
        tokens = {"root": [(r"select", Keyword), (r"\s+", Whitespace)]}

    assert tokens(Shouty, "SELECT Select") == [
        (Keyword, "SELECT"),
        (Whitespace, " "),
        (Keyword, "Select"),
    ]


def test_empty_match_without_a_state_change_is_skipped():
    class Lazy(RegexLexer):
        tokens = {"root": [(r"x*", Name), (r"\d", Number)]}

    assert tokens(Lazy, "x1y") == [(Name, "x"), (Number, "1"), (Error, "y")]


def test_states_that_bounce_forever_still_terminate():
    class Bouncy(RegexLexer):
        tokens = {
            "root": [(r"a", Name), default("other")],
            "other": [default("#pop")],
        }

    assert tokens(Bouncy, "ab!a") == [
        (Name, "a"),
        (Error, "b"),
        (Error, "!"),
        (Name, "a"),
    ]


@pytest.mark.parametrize(
    "definition, message",
    [
        ({"start": [(r"a", Name)]}, "no root state"),
        ({"root": [(r"a", Name, "nowhere")]}, "unknown state 'nowhere'"),
        ({"root": [include("missing")]}, "unknown state 'missing'"),
        ({"root": [include("a")], "a": [include("root")]}, "circular include"),
        ({"root": [(r"(unclosed", Name)]}, "bad pattern"),
        ({"root": [default("gone")]}, "unknown state 'gone'"),
    ],
)
def test_broken_definitions_are_reported_on_first_use(definition, message):
    class Broken(RegexLexer):
        tokens = definition

    with pytest.raises(HighlightError, match=re.escape(message)):
        tokens(Broken, "a")


def test_words_matches_whole_alternatives_longest_first():
    pattern = re.compile(words(["in", "int", "interface"], suffix=r"\b"))
    assert pattern.match("interface x").group() == "interface"
    assert pattern.match("int x").group() == "int"
    assert pattern.match("in x").group() == "in"
    assert pattern.match("inx") is None


def test_words_escapes_regex_characters():
    pattern = re.compile(words(["a.b", "c++", "-include"]))
    assert pattern.fullmatch("c++")
    assert pattern.fullmatch("-include")
    assert not pattern.fullmatch("axb")


def test_text_lexer_returns_the_input_as_one_token():
    assert tokens(TextLexer, "if (x) { <b> }\n") == [(Text, "if (x) { <b> }\n")]
    assert tokens(TextLexer, "") == []
