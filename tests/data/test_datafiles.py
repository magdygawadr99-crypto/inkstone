from __future__ import annotations

import datetime as dt
import sys

import pytest

from inkstone.datafiles import load_data_dir, load_data_file
from inkstone.errors import ContentError

needs_tomllib = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="tomllib is new in Python 3.11"
)


def write(path, text, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode(encoding))
    return path


def test_json(tmp_path):
    path = write(tmp_path / "site.json", '{"name": "Inkstone", "tags": ["a", "b"]}')
    assert load_data_file(path) == {"name": "Inkstone", "tags": ["a", "b"]}
    assert load_data_file(write(tmp_path / "list.json", "[1, 2, 3]")) == [1, 2, 3]


@pytest.mark.parametrize("name", ["authors.yaml", "authors.yml", "AUTHORS.YAML"])
def test_yaml(tmp_path, name):
    path = write(tmp_path / name, "sam:\n  name: Sam\n  joined: 2020-01-15\n")
    assert load_data_file(path) == {
        "sam": {"name": "Sam", "joined": dt.date(2020, 1, 15)}
    }


@needs_tomllib
def test_toml(tmp_path):
    path = write(tmp_path / "menu.toml", '[[item]]\nname = "Home"\nurl = "/"\n')
    assert load_data_file(path) == {"item": [{"name": "Home", "url": "/"}]}


def test_accepts_string_paths_and_strips_a_bom(tmp_path):
    path = write(tmp_path / "bom.json", '\ufeff{"a": 1}')
    assert load_data_file(str(path)) == {"a": 1}


def test_empty_files(tmp_path):
    assert load_data_file(write(tmp_path / "empty.yaml", "")) is None
    assert load_data_file(write(tmp_path / "empty.csv", "")) == []
    with pytest.raises(ContentError, match="invalid JSON"):
        load_data_file(write(tmp_path / "empty.json", ""))


def test_csv_rows_become_dicts_with_inferred_types(tmp_path):
    text = (
        "name,price,stock,active,code,note\r\n"
        "Pen,1.50,12,true,007,\r\n"
        'Ink bottle,12,0,FALSE,A-1,"dark, blue"\r\n'
        "Eraser,-0.5,-3,no,1e3, padded \r\n"
    )
    rows = load_data_file(write(tmp_path / "products.csv", text))
    columns = ["name", "price", "stock", "active", "code", "note"]
    assert all(list(row) == columns for row in rows)
    assert [tuple(row.values()) for row in rows] == [
        ("Pen", 1.5, 12, True, "007", None),
        ("Ink bottle", 12, 0, False, "A-1", "dark, blue"),
        ("Eraser", -0.5, -3, "no", "1e3", "padded"),
    ]


def test_csv_types_are_exact(tmp_path):
    rows = load_data_file(write(tmp_path / "t.csv", "a,b,c\n1,1.0,01\n"))
    assert [type(value) for value in rows[0].values()] == [int, float, str]


def test_csv_edge_cases(tmp_path):
    text = 'id, title \n1,"multi\nline"\n\n2\n   ,  \n3,"say ""hi"""\n'
    assert load_data_file(write(tmp_path / "edge.csv", text)) == [
        {"id": 1, "title": "multi\nline"},
        {"id": 2, "title": None},
        {"id": 3, "title": 'say "hi"'},
    ]
    assert load_data_file(write(tmp_path / "header-only.csv", "a,b\n")) == []


def test_tsv(tmp_path):
    text = "city\tpopulation\nOslo\t709000\nNew York, NY\t8800000\n"
    assert load_data_file(write(tmp_path / "cities.tsv", text)) == [
        {"city": "Oslo", "population": 709000},
        {"city": "New York, NY", "population": 8800000},
    ]


@pytest.mark.parametrize(
    ("name", "text", "line", "fragment"),
    [
        ("bad.json", '{\n  "a": 1,\n  "b"\n}', 4, "invalid JSON"),
        ("bad.yaml", "a: 1\nb: [1, 2\n", 2, "invalid YAML: flow sequence"),
        ("bad.yml", "a: 1\n\tb: 2\n", 2, "tabs"),
        (
            "wide.csv",
            "a,b\n1,2\n3,4,5\n",
            3,
            "row has 3 fields but the header only has 2",
        ),
        ("dupe.csv", "a,b,a\n1,2,3\n", 1, "duplicate column 'a'"),
        ("blank.csv", "a,,c\n1,2,3\n", 1, "column 2 has no name"),
    ],
)
def test_errors_carry_path_and_line(tmp_path, name, text, line, fragment):
    path = write(tmp_path / name, text)
    with pytest.raises(ContentError, match=fragment) as info:
        load_data_file(path)
    assert info.value.path == path
    assert info.value.line == line
    assert str(info.value).startswith(f"{path}:{line}: ")


@needs_tomllib
def test_toml_errors_carry_path_and_line(tmp_path):
    path = write(tmp_path / "bad.toml", "a = 1\nb = \n")
    with pytest.raises(ContentError, match="invalid TOML") as info:
        load_data_file(path)
    assert (info.value.path, info.value.line) == (path, 2)


def test_unsupported_and_unreadable_files(tmp_path):
    with pytest.raises(ContentError, match="unsupported data file type '.xml'"):
        load_data_file(write(tmp_path / "feed.xml", "<x/>"))
    with pytest.raises(ContentError, match="unsupported data file type 'Makefile'"):
        load_data_file(write(tmp_path / "Makefile", "all:"))
    with pytest.raises(ContentError, match="cannot read data file") as info:
        load_data_file(tmp_path / "missing.json")
    assert info.value.path == tmp_path / "missing.json"


def test_invalid_utf8_is_a_content_error(tmp_path):
    path = tmp_path / "latin1.yaml"
    path.write_bytes(b"ok: 1\nname: caf\xe9\n")
    with pytest.raises(ContentError, match="not valid UTF-8") as info:
        load_data_file(path)
    assert info.value.line == 2


def test_load_data_dir_builds_a_nested_dict(tmp_path):
    write(tmp_path / "site.yaml", "title: My site\n")
    write(tmp_path / "authors.json", '{"sam": {"name": "Sam"}}')
    write(tmp_path / "nav" / "main.yaml", "- Home\n- About\n")
    write(tmp_path / "nav" / "footer.csv", "label,url\nRSS,/feed.xml\n")
    write(tmp_path / "nav" / "deep" / "er.json", "[1]")
    assert load_data_dir(tmp_path) == {
        "site": {"title": "My site"},
        "authors": {"sam": {"name": "Sam"}},
        "nav": {
            "main": ["Home", "About"],
            "footer": [{"label": "RSS", "url": "/feed.xml"}],
            "deep": {"er": [1]},
        },
    }


def test_load_data_dir_is_sorted_by_name(tmp_path):
    for name in ("zeta.json", "alpha.json", "Mid.json"):
        write(tmp_path / name, "1")
    assert list(load_data_dir(tmp_path)) == ["Mid", "alpha", "zeta"]


def test_load_data_dir_skips_hidden_and_unknown_files(tmp_path):
    write(tmp_path / "keep.json", "1")
    write(tmp_path / "README.md", "docs")
    write(tmp_path / ".hidden.json", "not even json")
    write(tmp_path / ".git" / "config.yaml", "a: [")
    write(tmp_path / "notes.txt", "text")
    assert load_data_dir(tmp_path) == {"keep": 1}


def test_load_data_dir_missing_or_empty(tmp_path):
    assert load_data_dir(tmp_path / "nope") == {}
    assert load_data_dir(tmp_path) == {}
    (tmp_path / "empty").mkdir()
    assert load_data_dir(tmp_path) == {"empty": {}}


def test_load_data_dir_rejects_clashing_names(tmp_path):
    write(tmp_path / "authors.json", "{}")
    write(tmp_path / "authors.yaml", "{}")
    with pytest.raises(ContentError, match="'authors' is already provided by") as info:
        load_data_dir(tmp_path)
    assert info.value.path == tmp_path / "authors.yaml"


def test_load_data_dir_file_and_directory_clash(tmp_path):
    write(tmp_path / "nav.yaml", "a: 1\n")
    write(tmp_path / "nav" / "main.yaml", "b: 2\n")
    with pytest.raises(ContentError, match="'nav' is already provided by"):
        load_data_dir(tmp_path)


def test_load_data_dir_reports_the_broken_file(tmp_path):
    write(tmp_path / "ok.yaml", "a: 1\n")
    bad = write(tmp_path / "sub" / "bad.yaml", "a: 1\na: 2\n")
    with pytest.raises(ContentError, match="duplicate key") as info:
        load_data_dir(tmp_path)
    assert (info.value.path, info.value.line) == (bad, 2)
