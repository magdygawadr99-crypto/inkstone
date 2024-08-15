from __future__ import annotations

import pytest

from inkstone.errors import InkstoneError
from inkstone.highlight import (
    HighlightError,
    Lexer,
    get_lexer,
    guess_language,
    list_languages,
    registry,
)
from inkstone.highlight.lexer import TextLexer
from inkstone.highlight.registry import find_lexer, language_for_filename, register

from .samples import SAMPLES

EXPECTED_LANGUAGES = """
    bash c cpp css diff dockerfile go html ini java javascript json makefile
    markdown python rust sql text toml typescript xml yaml
""".split()


def test_all_languages_are_registered():
    assert [name for name, _, _ in list_languages()] == EXPECTED_LANGUAGES


def test_list_languages_shape():
    for name, aliases, extensions in list_languages():
        assert name == name.lower()
        assert isinstance(aliases, tuple) and isinstance(extensions, tuple)
        assert all(ext.startswith(".") and ext == ext.lower() for ext in extensions)
        assert all(alias == alias.lower() for alias in aliases)


@pytest.mark.parametrize(
    "alias, name",
    [
        ("python", "python"),
        ("py", "python"),
        ("python3", "python"),
        ("js", "javascript"),
        ("jsx", "javascript"),
        ("node", "javascript"),
        ("ts", "typescript"),
        ("tsx", "typescript"),
        ("htm", "html"),
        ("svg", "xml"),
        ("rss", "xml"),
        ("jsonc", "json"),
        ("yml", "yaml"),
        ("cfg", "ini"),
        ("sh", "bash"),
        ("shell", "bash"),
        ("zsh", "bash"),
        ("h", "c"),
        ("c++", "cpp"),
        ("cxx", "cpp"),
        ("golang", "go"),
        ("rs", "rust"),
        ("postgresql", "sql"),
        ("sqlite", "sql"),
        ("patch", "diff"),
        ("md", "markdown"),
        ("docker", "dockerfile"),
        ("make", "makefile"),
        ("mk", "makefile"),
        ("txt", "text"),
        ("plain", "text"),
    ],
)
def test_aliases(alias, name):
    assert get_lexer(alias).name == name


@pytest.mark.parametrize("name", ["Python", "PY", " js ", "C++", "Dockerfile"])
def test_lookup_ignores_case_and_surrounding_space(name):
    assert get_lexer(name) is get_lexer(name.strip().lower())


def test_names_and_aliases_are_unique_across_lexers():
    seen = {}
    for name, aliases, _ in list_languages():
        for key in {name, *aliases}:
            assert key not in seen, f"{key!r} claimed by {seen.get(key)} and {name}"
            seen[key] = name


def test_extensions_are_unique_across_lexers():
    seen = {}
    for name, _, extensions in list_languages():
        for ext in extensions:
            assert ext not in seen, f"{ext} claimed by {seen.get(ext)} and {name}"
            seen[ext] = name


@pytest.mark.parametrize("name", ["klingon", "", "py thon", None, 42])
def test_unknown_language_raises(name):
    with pytest.raises(HighlightError, match="no lexer for language"):
        get_lexer(name)


def test_highlight_error_is_an_inkstone_error():
    assert issubclass(HighlightError, InkstoneError)
    with pytest.raises(InkstoneError) as info:
        get_lexer("klingon")
    assert str(info.value) == "no lexer for language 'klingon'"
    assert info.value.message == str(info.value)


def test_find_lexer_falls_back_to_plain_text():
    assert find_lexer("py").name == "python"
    assert find_lexer("klingon").name == "text"
    assert find_lexer(None).name == "text"
    assert find_lexer("").name == "text"


def test_get_lexer_returns_a_shared_instance():
    assert get_lexer("python") is get_lexer("py")
    assert isinstance(get_lexer("python"), Lexer)
    assert repr(get_lexer("python")) == "<PythonLexer 'python'>"


def test_registering_a_clashing_name_is_refused(monkeypatch):
    monkeypatch.setattr(registry, "_by_name", dict(registry._by_name))
    monkeypatch.setattr(registry, "_classes", list(registry._classes))

    class Impostor(TextLexer):
        name = "fake"
        aliases = ("py",)

    with pytest.raises(HighlightError, match="'py' is used by both"):
        register(Impostor)


def test_registering_a_new_lexer(monkeypatch):
    monkeypatch.setattr(registry, "_by_name", dict(registry._by_name))
    monkeypatch.setattr(registry, "_classes", list(registry._classes))

    @register
    class Shout(TextLexer):
        name = "shout"
        aliases = ("loud",)
        extensions = (".shout",)

    assert get_lexer("LOUD").name == "shout"
    assert ("shout", ("loud",), (".shout",)) in list_languages()
    assert language_for_filename("a.shout") == "shout"


def test_lexer_without_a_name_cannot_be_registered():
    class Nameless(TextLexer):
        name = ""

    with pytest.raises(HighlightError, match="has no name"):
        register(Nameless)


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("app.py", "python"),
        ("types.pyi", "python"),
        ("index.js", "javascript"),
        ("lib.mjs", "javascript"),
        ("App.jsx", "javascript"),
        ("main.ts", "typescript"),
        ("types.d.ts", "typescript"),
        ("App.tsx", "typescript"),
        ("index.html", "html"),
        ("feed.xml", "xml"),
        ("logo.svg", "xml"),
        ("site.css", "css"),
        ("package.json", "json"),
        ("pyproject.toml", "toml"),
        ("config.yaml", "yaml"),
        (".github/workflows/ci.yml", "yaml"),
        ("setup.cfg", "ini"),
        ("tox.ini", "ini"),
        (".editorconfig", "ini"),
        ("build.sh", "bash"),
        (".bashrc", "bash"),
        ("main.c", "c"),
        ("util.h", "c"),
        ("main.cpp", "cpp"),
        ("util.hpp", "cpp"),
        ("main.go", "go"),
        ("lib.rs", "rust"),
        ("Main.java", "java"),
        ("schema.sql", "sql"),
        ("fix.patch", "diff"),
        ("README.md", "markdown"),
        ("notes.txt", "text"),
        ("Dockerfile", "dockerfile"),
        ("Dockerfile.dev", "dockerfile"),
        ("api.dockerfile", "dockerfile"),
        ("Containerfile", "dockerfile"),
        ("Makefile", "makefile"),
        ("GNUmakefile", "makefile"),
        ("rules.mk", "makefile"),
        ("Pipfile", "toml"),
        ("Cargo.lock", "toml"),
        ("INDEX.HTML", "html"),
        ("C:\\site\\static\\Main.CSS", "css"),
        ("/srv/www/a.b/script.min.js", "javascript"),
        ("unknown.xyz", None),
        ("noextension", None),
        ("", None),
        ("archive.tar.gz", None),
        ("python", None),
    ],
)
def test_language_for_filename(filename, expected):
    assert language_for_filename(filename) == expected
    assert guess_language("", filename=filename) == expected


def test_filename_beats_content():
    assert guess_language("#!/bin/sh\necho hi\n", filename="x.py") == "python"


def test_unknown_filename_falls_back_to_content():
    assert guess_language("#!/bin/sh\necho hi\n", filename="run") == "bash"


@pytest.mark.parametrize(
    "first_line, expected",
    [
        ("#!/usr/bin/env python3", "python"),
        ("#!/usr/bin/python", "python"),
        ("#!/usr/bin/python3.12", "python"),
        ("#! /bin/sh", "bash"),
        ("#!/bin/bash -e", "bash"),
        ("#!/usr/bin/env -S bash -x", "bash"),
        ("#!/usr/bin/zsh", "bash"),
        ("#!/usr/bin/env node", "javascript"),
        ("#!/usr/bin/env FOO=1 node", "javascript"),
        ("#!/usr/bin/env deno", "javascript"),
        ("#!/usr/bin/env ts-node", "typescript"),
        ("#!/usr/bin/perl", None),
        ("#!/usr/bin/env", None),
        ("#!", None),
    ],
)
def test_guess_from_shebang(first_line, expected):
    assert guess_language(first_line + "\nrun something\n") == expected


@pytest.mark.parametrize(
    "code, expected",
    [
        ("# -*- mode: python -*-\nx", "python"),
        ("# -*- coding: utf-8; mode: yaml -*-\nx", "yaml"),
        ("x\n// vim: set ft=javascript:\n", "javascript"),
        ("x\n# vim: ts=4 filetype=sh\n", "bash"),
        ("x\n# vim: ft=klingon\n", None),
    ],
)
def test_guess_from_editor_modeline(code, expected):
    assert guess_language(code) == expected


# the first snippet of each language is long enough to be recognisable
@pytest.mark.parametrize("lang", sorted(set(SAMPLES) - {"text"}))
def test_guess_from_content(lang):
    assert guess_language(SAMPLES[lang][0]) == lang


@pytest.mark.parametrize(
    "code",
    [
        "",
        "   \n\n",
        "Just a sentence of plain prose.",
        "x = 1\ny = 2\n",
        "hello: world",
        "1 2 3",
    ],
)
def test_guess_gives_up_on_ambiguous_text(code):
    assert guess_language(code) is None


@pytest.mark.parametrize(
    "code, expected",
    [
        ("<?xml version='1.0'?>\n<a/>", "xml"),
        ("<!doctype html>\n<p>hi", "html"),
        ("<div><p>para</p></div>", "html"),
        ('{"a": [1, 2], "b": null}', "json"),
        ("SELECT id, name FROM users WHERE id = 1;", "sql"),
        ("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n", "diff"),
        ("FROM alpine\nRUN apk add curl\n", "dockerfile"),
        (".PHONY: all\nall:\n\techo hi\n", "makefile"),
        ("def f(x):\n    return x\n", "python"),
        ("#include <stdio.h>\nint main(void) { return 0; }\n", "c"),
        ("#include <iostream>\nint main() { std::cout << 1; }\n", "cpp"),
        ("package main\n\nfunc main() {}\n", "go"),
        ('fn main() {\n    println!("hi");\n}\n', "rust"),
        ("const x = 1;\nconsole.log(x);\n", "javascript"),
        ("interface A {\n  id: number;\n}\n", "typescript"),
        ("a { color: red; }\nb { margin: 0; }\n", "css"),
        ('[tool.x]\nname = "y"\n', "toml"),
        ("[section]\nname = some value\n", "ini"),
        ("---\ntitle: x\ntags:\n  - a\n", "yaml"),
        ("# Title\n\nSome [link](http://x.y).\n", "markdown"),
        ("if [ -f x ]; then\n  echo hi\nfi\n", "bash"),
    ],
)
def test_guess_from_short_snippets(code, expected):
    assert guess_language(code) == expected
