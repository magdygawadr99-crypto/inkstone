from __future__ import annotations

import pytest

from inkstone.highlight.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)

from .helpers import type_of, types_of, visible


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("FROM python:3.12", "FROM", Keyword),
        ("FROM python:3.12", "python:3.12", String),
        ("from python:3.12 as base", "from", Keyword),
        ("FROM python:3.12 AS base", "AS", Keyword),
        ("FROM python:3.12 AS base", "base", Name.Label),
        ("FROM --platform=linux/amd64 alpine", "--platform", Name.Attribute),
        ("# note\nFROM x", "# note", Comment.Single),
        ("# syntax=x/y:1\nFROM x", "# syntax=x/y:1", Comment.Preproc),
        ("ENV A=1", "ENV", Keyword),
        ("ENV A=1", "A", Name.Variable),
        ("ENV A=1", "1", String),
        ("ENV KEY some value", "KEY", Name.Variable),
        ("ARG VERSION", "VERSION", Name.Variable),
        ("ARG VERSION=1.2", "=", Operator),
        ('LABEL a.b="c"', "a.b", Name.Variable),
        ("WORKDIR /app", "/app", Text),
        ("WORKDIR $HOME/app", "$HOME", Name.Variable),
        ("COPY --from=build /a /b", "--from", Name.Attribute),
        ("COPY cmd/ /app/cmd", "cmd/", Text),
        ("EXPOSE 8080/udp", "8080", Number),
        ("EXPOSE 8080/udp", "udp", Keyword),
        ("USER app", "USER", Keyword),
        ("ONBUILD RUN make", "ONBUILD", Keyword),
        ("ONBUILD RUN make", "RUN", Keyword),
        ("RUN echo hi", "echo", Name.Builtin),
        ("RUN x=1 && echo $x", "&&", Operator),
        ("RUN x=1 && echo $x", "$x", Name.Variable),
        ('CMD ["a", "b"]', '"a"', String),
        ('CMD ["a", "b"]', "[", Punctuation),
    ],
)
def test_dockerfile_tokens(code, text, expected):
    assert type_of("dockerfile", code, text) is expected


def test_dockerfile_run_continues_over_backslashes_and_comments():
    code = "RUN apt-get update && \\\n    # tools\n    apt-get install -y curl\nCMD x\n"
    tokens = visible("dockerfile", code)
    assert types_of("dockerfile", code, "RUN") == [Keyword]
    assert (Comment.Single, "# tools") in tokens
    assert (Text, "curl") in tokens
    assert tokens[-2:] == [(Keyword, "CMD"), (Text, "x")]


def test_dockerfile_env_string_interpolates_variables():
    tokens = visible("dockerfile", 'ENV PATH="/app/bin:${PATH}"')
    assert (String, '"/app/bin:') in tokens
    assert (Name.Variable, "${PATH}") in tokens


def test_dockerfile_healthcheck_command_is_shell():
    code = "HEALTHCHECK --interval=5s CMD curl -f http://x/ || exit 1"
    assert type_of("dockerfile", code, "HEALTHCHECK") is Keyword
    assert type_of("dockerfile", code, "--interval") is Name.Attribute
    assert type_of("dockerfile", code, "CMD") is Keyword
    assert type_of("dockerfile", code, "||") is Operator
    assert type_of("dockerfile", code, "exit") is Name.Builtin


def test_dockerfile_instructions_only_count_at_the_start_of_a_line():
    code = "RUN echo FROM here\nCOPY run.sh /run\n"
    assert types_of("dockerfile", code, "FROM") == [Text]
    assert type_of("dockerfile", code, "run.sh") is Text


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("# note", "# note", Comment.Single),
        ("CC = gcc", "CC", Name.Variable),
        ("CC = gcc", "=", Operator),
        ("CC = gcc", "gcc", Text),
        ("CC := gcc", ":=", Operator),
        ("CC ?= gcc", "?=", Operator),
        ("CFLAGS += -O2", "+=", Operator),
        ("X ::= y", "::=", Operator),
        ("X = a # why", "# why", Comment.Single),
        ("all: a b", "all", Name.Function),
        ("all: a b", ":", Punctuation),
        ("all: a b", "a", Text),
        ("%.o: %.c", "%.o", Name.Function),
        ("a b: c", "b", Name.Function),
        (".PHONY: all", ".PHONY", Name.Builtin),
        ("all:: x", "::", Punctuation),
        ("a: b | c", "|", Operator),
        ("X = $(Y)", "Y", Name.Variable),
        ("X = ${Y}", "${", Keyword),
        ("X = $(wildcard *.c)", "wildcard", Name.Builtin),
        ("X = $(wildcard *.c)", "*.c", Text),
        ("X = $(SRC:.c=.o)", "$(", Keyword),
        ("include other.mk", "include", Keyword),
        ("-include local.mk", "-include", Keyword),
        ("ifeq ($(A),b)", "ifeq", Keyword),
        ("endif", "endif", Keyword),
        ("export PATH := x", "export", Keyword),
        ("export PATH := x", "PATH", Name.Variable),
        ("x:\n\texit $$?", "$$?", Name.Variable),
    ],
)
def test_makefile_tokens(code, text, expected):
    assert type_of("makefile", code, text) is expected


def test_makefile_recipe_lines():
    code = 'out: in\n\t@$(CC) -o $@ $< "$(X) y"  # link\n\t-rm $$tmp\nnext = 1\n'
    tokens = visible("makefile", code)
    assert (Operator, "@") in tokens
    assert (Name.Variable, "CC") in tokens
    assert (Name.Variable.Magic, "$@") in tokens
    assert (Name.Variable.Magic, "$<") in tokens
    assert (String, '"') in tokens and (Name.Variable, "X") in tokens
    assert (Comment.Single, "# link") in tokens
    assert (Operator, "-") in tokens
    assert (Name.Variable, "$$tmp") in tokens
    assert tokens[-3:] == [(Name.Variable, "next"), (Operator, "="), (Text, "1")]


def test_makefile_recipe_continuation():
    code = "x:\n\techo a && \\\n\t  echo b\ny: z\n"
    tokens = visible("makefile", code)
    assert (String.Escape, "\\\n") in tokens
    assert [text for ttype, text in tokens if ttype is Name.Function] == ["x", "y"]


def test_makefile_inline_recipe_after_semicolon():
    tokens = visible("makefile", "x: y ; $(CC) $^\n")
    assert (Punctuation, ";") in tokens
    assert (Name.Variable.Magic, "$^") in tokens


def test_makefile_nested_function_calls():
    tokens = visible("makefile", "O = $(patsubst %.c,%.o,$(wildcard src/*.c)) end\n")
    assert (Name.Builtin, "patsubst") in tokens
    assert (Name.Builtin, "wildcard") in tokens
    assert tokens.count((Punctuation, ",")) == 2
    assert tokens[-1] == (Text, "end")


def test_makefile_assignment_is_not_a_target():
    assert Name.Function not in [t for t, _ in visible("makefile", "a := b\nc ::= d\n")]


def test_makefile_define_body_is_opaque():
    code = "define HELP\nUsage: make [target]\nendef\nall: x\n"
    tokens = visible("makefile", code)
    assert tokens[:2] == [(Keyword, "define"), (Name.Variable, "HELP")]
    assert (String, "Usage: make [target]\n") in tokens
    assert (Keyword, "endef") in tokens
    assert [text for ttype, text in tokens if ttype is Name.Function] == ["all"]
