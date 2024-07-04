from __future__ import annotations

import copy
import pickle

import pytest

from inkstone.highlight import Token
from inkstone.highlight.token import (
    Comment,
    Keyword,
    Literal,
    Name,
    Number,
    String,
    Text,
    Whitespace,
    css_class,
    parse_token,
    styled_types,
)


def test_attribute_access_returns_the_same_object_every_time():
    assert Token.Name.Function is Token.Name.Function
    assert Token.Name.Function is Name.Function


def test_subtypes_are_created_on_demand():
    made_up = Token.Name.Function.SomethingNobodyDeclared
    assert made_up.parent is Name.Function
    assert made_up in Name.Function.subtypes
    assert made_up is Token.Name.Function.SomethingNobodyDeclared


def test_parent_chain_ends_at_the_root():
    assert Keyword.Declaration.parent is Keyword
    assert Keyword.parent is Token
    assert Token.parent is None
    assert list(String.Escape.ancestors()) == [String.Escape, String, Literal, Token]


def test_string_and_number_are_reachable_directly_and_under_literal():
    assert Token.String is Token.Literal.String
    assert Token.String.Escape is Literal.String.Escape
    assert Token.Number.Float is Literal.Number.Float
    assert Number.Float.parent is Number


def test_in_tests_ancestry():
    assert Keyword.Type in Keyword
    assert Keyword in Keyword
    assert String.Escape in Literal
    assert Keyword not in Keyword.Type
    assert Name.Function not in Keyword
    assert Whitespace in Text
    assert "Keyword" not in Keyword


def test_everything_is_in_the_root():
    assert Comment.Single in Token
    assert Token in Token


def test_repr_spells_out_the_path():
    assert repr(Token) == "Token"
    assert repr(Name.Function.Magic) == "Token.Name.Function.Magic"
    assert repr(String.Escape) == "Token.Literal.String.Escape"


def test_lowercase_attributes_are_not_token_types():
    with pytest.raises(AttributeError):
        Token.keyword
    with pytest.raises(AttributeError):
        Name._private


@pytest.mark.parametrize(
    "ttype, expected",
    [
        (Keyword, "k"),
        (Keyword.Declaration, "kd"),
        (Name.Function, "nf"),
        (Name.Function.Magic, "fm"),
        (String, "s"),
        (String.Escape, "se"),
        (Number.Float, "mf"),
        (Comment.Single, "c1"),
        (Token.Error, "err"),
        (Token.Generic.Inserted, "gi"),
        (Text, ""),
        (Whitespace, ""),
        (Token, ""),
    ],
)
def test_css_class(ttype, expected):
    assert css_class(ttype) == expected


def test_css_class_of_unknown_subtype_falls_back_to_nearest_ancestor():
    assert css_class(Token.Keyword.Declaration.Weird) == "kd"
    assert css_class(Token.Comment.Odd.Deeper) == "c"
    assert css_class(Token.Unheard.Of) == ""


def test_css_classes_are_unique():
    names = [css_class(ttype) for ttype in styled_types()]
    assert len(names) == len(set(names))
    assert "" not in names


def test_styled_types_ignores_fallback_lookups():
    before = styled_types()
    css_class(Token.Name.Tag.JustForThisTest)
    assert styled_types() == before


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Name.Function", Name.Function),
        ("Token.Name.Function", Name.Function),
        ("Literal.String.Escape", String.Escape),
        ("String.Escape", String.Escape),
        ("Token", Token),
        ("", Token),
    ],
)
def test_parse_token(name, expected):
    assert parse_token(name) is expected


@pytest.mark.parametrize("name", ["name.function", "Name.9", "Name Function", "Name.-"])
def test_parse_token_rejects_junk(name):
    with pytest.raises(ValueError):
        parse_token(name)


def test_copies_and_pickles_keep_identity():
    ttype = Name.Function.Magic
    assert copy.copy(ttype) is ttype
    assert copy.deepcopy({"t": [ttype]})["t"][0] is ttype
    assert pickle.loads(pickle.dumps(ttype)) is ttype
    assert pickle.loads(pickle.dumps(Token)) is Token


def test_token_types_work_as_dict_keys():
    colours = {Keyword: "red", Keyword.Type: "blue"}
    assert colours[Token.Keyword.Type] == "blue"
    assert Keyword.Constant not in colours
