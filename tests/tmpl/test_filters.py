from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import PurePosixPath

import pytest

from inkstone.tmpl import Environment, Markup, TemplateRuntimeError, UndefinedError
from inkstone.tmpl.filters import FILTERS


@dataclass
class Post:
    title: str
    year: int
    tags: tuple = ()
    draft: bool = False


POSTS = [
    Post("Zebra crossing", 2023, ("animals", "roads")),
    Post("apple pie", 2024, ("food",), draft=True),
    Post("Mango lassi", 2023, ("food", "drinks")),
]


def titles(render, expression):
    source = "{{ posts | " + expression + " | map(attribute='title') | join('|') }}"
    return render(source, posts=POSTS)


def test_there_are_plenty_of_filters(env):
    assert len(FILTERS) >= 50
    assert env.filters == FILTERS
    assert env.filters is not FILTERS


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ 'hello World' | upper }}", "HELLO WORLD"),
        ("{{ 'Hello WORLD' | lower }}", "hello world"),
        ("{{ 'hello WORLD' | capitalize }}", "Hello world"),
        ("{{ 'hello wORLD' | title }}", "Hello World"),
        ("{{ '  padded  ' | trim }}|", "padded|"),
        ("{{ 'xxhixx' | trim('x') }}", "hi"),
        ("{{ 'ab' | center(6) }}|", "  ab  |"),
        ("{{ 42 | string | length }}", "2"),
        ("{{ none | string }}|", "|"),
        ("{{ none | upper }}|", "|"),
        ("{{ 5 | upper }}", "5"),
        ("{{ 'one two  three' | wordcount }}", "3"),
        ("{{ '' | wordcount }}", "0"),
        ("{{ 'abc' | reverse }}", "cba"),
        ("{{ 'a-b-c' | replace('-', '+') }}", "a+b+c"),
        ("{{ 'a-b-c' | replace('-', '+', 1) }}", "a+b-c"),
        ("{{ 'a1b1' | replace(1, 2) }}", "a2b2"),
        ("{{ '%s is %d' | format('x', 3) }}", "x is 3"),
        ("{{ '%(a)s-%(b)s' | format(a=1, b=2) }}", "1-2"),
    ],
)
def test_string_filters(render, source, expected):
    assert render(source) == expected


def test_title_knows_where_words_start(render):
    text = "they're well-known (old) friends"
    assert render("{{ text | title }}", text=text) == "They're Well-Known (Old) Friends"


def test_striptags(render):
    html = "<p>Some <b>bold</b>\n   &amp; <!-- not this -->plain text</p>"
    assert render("{{ html | striptags }}", html=html) == "Some bold & plain text"
    assert render("{{ '1 < 2' | striptags }}") == "1 < 2"


def test_format_refuses_mixed_arguments(render):
    with pytest.raises(TemplateRuntimeError, match="positional or keyword"):
        render("{{ '%s' | format(1, a=2) }}")


@pytest.mark.parametrize(
    "text, args, expected",
    [
        ("short", "", "short"),
        ("The quick brown fox jumps", "(10)", "The..."),
        ("The quick brown fox jumps", "(12)", "The quick..."),
        ("The quick brown fox jumps", "(12, true)", "The quick..."),
        ("The quick brown fox jumps", "(14, true)", "The quick b..."),
        ("The quick brown fox jumps", "(14, false, '…')", "The quick…"),
        ("The quick brown fox jumps", "(12, end='')", "The quick"),
        ("exactly twenty chars", "(20)", "exactly twenty chars"),
        ("only a little too long", "(20)", "only a little too long"),
        ("only a little too long", "(20, leeway=0)", "only a little too..."),
        ("nospacesinthisstringatall", "(10)", "nospace..."),
    ],
)
def test_truncate(render, text, args, expected):
    assert render("{{ text | truncate" + args + " }}", text=text) == expected


def test_truncate_length_must_fit_the_end_marker(render):
    with pytest.raises(TemplateRuntimeError, match="leaves no room"):
        render("{{ 'some long text here' | truncate(2) }}")


def test_wordwrap(render):
    text = "The quick brown fox jumps over the lazy dog"
    assert render("{{ t | wordwrap(15) }}", t=text) == (
        "The quick brown\nfox jumps over\nthe lazy dog"
    )
    assert render("{{ t | wordwrap(20, wrapstring='<br>') }}", t=text) == (
        "The quick brown fox<br>jumps over the lazy<br>dog"
    )
    assert render("{{ 'one two\n\nthree four' | wordwrap(5) }}") == (
        "one\ntwo\n\nthree\nfour"
    )
    assert render("{{ 'abcdefgh' | wordwrap(3) }}") == "abc\ndef\ngh"
    assert render("{{ 'abcdefgh' | wordwrap(3, false) }}") == "abcdefgh"


@pytest.mark.parametrize(
    "args, expected",
    [
        ("", "a\n    b\n\n    c"),
        ("(2)", "a\n  b\n\n  c"),
        ("(2, true)", "  a\n  b\n\n  c"),
        ("(2, first=true, blank=true)", "  a\n  b\n  \n  c"),
        ("('> ')", "a\n> b\n\n> c"),
    ],
)
def test_indent(render, args, expected):
    assert render("{{ text | indent" + args + " }}", text="a\nb\n\nc") == expected


def test_indent_single_line(render):
    assert render("{{ 'solo' | indent }}") == "solo"
    assert render("{{ '' | indent(first=true) }}|") == "    |"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ -5 | abs }}", "5"),
        ("{{ 2.5 | abs }}", "2.5"),
        ("{{ '42' | int }}", "42"),
        ("{{ '42.9' | int }}", "42"),
        ("{{ 42.9 | int }}", "42"),
        ("{{ 'nope' | int }}", "0"),
        ("{{ 'nope' | int(-1) }}", "-1"),
        ("{{ none | int }}", "0"),
        ("{{ missing | int(7) }}", "7"),
        ("{{ 'ff' | int(base=16) }}", "255"),
        ("{{ '0b101' | int(base=2) }}", "5"),
        ("{{ true | int }}", "1"),
        ("{{ '3.5' | float }}", "3.5"),
        ("{{ 3 | float }}", "3.0"),
        ("{{ 'x' | float }}", "0.0"),
        ("{{ 'x' | float(1.5) }}", "1.5"),
        ("{{ 2.5 | round }}", "3.0"),
        ("{{ 3.5 | round }}", "4.0"),
        ("{{ -2.5 | round }}", "-3.0"),
        ("{{ 2.4 | round }}", "2.0"),
        ("{{ 2.675 | round(2) }}", "2.68"),
        ("{{ 1234 | round(-2) }}", "1200.0"),
        ("{{ 42 | round }}", "42.0"),
        ("{{ 2.11 | round(1, 'ceil') }}", "2.2"),
        ("{{ 2.19 | round(1, 'floor') }}", "2.1"),
        ("{{ 2.5 | round | int }}", "3"),
        ("{{ '2.5' | round }}", "3.0"),
    ],
)
def test_number_filters(render, source, expected):
    assert render(source) == expected


def test_round_rejects_unknown_method(render):
    with pytest.raises(TemplateRuntimeError, match='"common", "ceil" or "floor"'):
        render("{{ 1.5 | round(0, 'up') }}")


@pytest.mark.parametrize(
    "size, binary, expected",
    [
        (0, False, "0 Bytes"),
        (1, False, "1 Byte"),
        (999, False, "999 Bytes"),
        (1000, False, "1.0 kB"),
        (1500, False, "1.5 kB"),
        (2_500_000, False, "2.5 MB"),
        (3_000_000_000, False, "3.0 GB"),
        (1023, True, "1023 Bytes"),
        (1024, True, "1.0 KiB"),
        (1024 * 1024 * 5, True, "5.0 MiB"),
        (10**30, False, "1000000.0 YB"),
    ],
)
def test_filesizeformat(render, size, binary, expected):
    assert render("{{ size | filesizeformat(binary) }}", size=size, binary=binary) == (
        expected
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ [1, 2, 3] | length }}", "3"),
        ("{{ 'four' | count }}", "4"),
        ("{{ {'a': 1} | length }}", "1"),
        ("{{ missing | length }}", "0"),
        ("{{ [3, 1, 2] | first }}", "3"),
        ("{{ [3, 1, 2] | last }}", "2"),
        ("{{ 'abc' | first }}{{ 'abc' | last }}", "ac"),
        ("[{{ [] | first }}{{ [] | last }}]", "[]"),
        ("{{ [] | first | default('none') }}", "none"),
        ("{{ [1, 2, 3] | reverse }}", "[3, 2, 1]"),
        ("{{ (1, 2) | list }}", "[1, 2]"),
        ("{{ 'ab' | list }}", "['a', 'b']"),
        ("{{ [1, 2, 3] | sum }}", "6"),
        ("{{ [] | sum }}", "0"),
        ("{{ [1, 2] | sum(start=10) }}", "13"),
        ("{{ [3, 1, 2] | min }}/{{ [3, 1, 2] | max }}", "1/3"),
        ("{{ ['b', 'A', 'c'] | min }}/{{ ['b', 'A', 'C'] | max }}", "A/C"),
        ("{{ ['b', 'A'] | min(case_sensitive=true) }}", "A"),
        ("[{{ [] | min }}{{ [] | max }}]", "[]"),
        ("{{ [1, 2, 3] | join }}", "123"),
        ("{{ [1, 2, 3] | join(', ') }}", "1, 2, 3"),
        ("{{ ['a', none, 'b'] | join('-') }}", "a--b"),
        ("{{ [] | join(', ') }}", ""),
        ("{{ [1, 2, 3, 4, 5] | batch(2) }}", "[[1, 2], [3, 4], [5]]"),
        ("{{ [1, 2, 3, 4, 5] | batch(3, 0) }}", "[[1, 2, 3], [4, 5, 0]]"),
        ("{{ [1, 2, 3, 4] | batch(2, 'x') }}", "[[1, 2], [3, 4]]"),
        ("{{ [] | batch(2) }}", "[]"),
        ("{{ [1, 2, 3, 4, 5] | slice(2) }}", "[[1, 2, 3], [4, 5]]"),
        ("{{ [1, 2, 3, 4, 5] | slice(3) }}", "[[1, 2], [3, 4], [5]]"),
        ("{{ [1, 2, 3, 4, 5] | slice(2, 'x') }}", "[[1, 2, 3], [4, 5, 'x']]"),
        ("{{ [1, 2, 3, 4] | slice(2, 'x') }}", "[[1, 2], [3, 4]]"),
        ("{{ [1, 2] | slice(3) }}", "[[1], [2], []]"),
    ],
)
def test_sequence_filters(render, source, expected):
    assert render(source) == expected


def test_batch_and_slice_need_a_positive_size(render):
    with pytest.raises(TemplateRuntimeError, match="batch: a row needs at least one"):
        render("{{ [1, 2] | batch(0) }}")
    with pytest.raises(TemplateRuntimeError, match="slice: there has to be at least"):
        render("{{ [1, 2] | slice(0) }}")


def test_first_last_and_length_work_on_iterators(render):
    assert render("{{ g | first }}", g=iter([1, 2])) == "1"
    assert render("{{ g | last }}", g=iter([1, 2])) == "2"
    assert render("{{ g | length }}", g=iter([1, 2])) == "2"
    assert render("{{ g | reverse }}", g=iter([1, 2])) == "[2, 1]"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ [3, 1, 2] | sort }}", "[1, 2, 3]"),
        ("{{ [3, 1, 2] | sort(reverse=true) }}", "[3, 2, 1]"),
        ("{{ ['b', 'A', 'c'] | sort }}", "['A', 'b', 'c']"),
        ("{{ ['b', 'A', 'c'] | sort(case_sensitive=true) }}", "['A', 'b', 'c']"),
        ("{{ ['b', 'a', 'C'] | sort(case_sensitive=true) }}", "['C', 'a', 'b']"),
        ("{{ 'cab' | sort | join }}", "abc"),
        ("{{ [[2, 'b'], [1, 'a']] | sort(attribute=0) }}", "[[1, 'a'], [2, 'b']]"),
        ("{{ [1, 2, 1, 3, 2] | unique }}", "[1, 2, 3]"),
        ("{{ ['a', 'A', 'b'] | unique }}", "['a', 'b']"),
        ("{{ ['a', 'A', 'b'] | unique(case_sensitive=true) }}", "['a', 'A', 'b']"),
        ("{{ [[1], [1], [2]] | unique }}", "[[1], [2]]"),
    ],
)
def test_sort_and_unique(render, source, expected):
    assert render(source) == expected


def test_sort_by_attribute(render):
    assert titles(render, "sort(attribute='title')") == (
        "apple pie|Mango lassi|Zebra crossing"
    )
    assert titles(render, "sort(attribute='title', case_sensitive=true)") == (
        "Mango lassi|Zebra crossing|apple pie"
    )
    assert titles(render, "sort(attribute='year,title')") == (
        "Mango lassi|Zebra crossing|apple pie"
    )
    assert titles(render, "sort(attribute='tags.0', reverse=true)") == (
        "apple pie|Mango lassi|Zebra crossing"
    )


def test_sort_by_nested_dict_key(render):
    rows = [{"meta": {"rank": 2}, "n": "b"}, {"meta": {"rank": 1}, "n": "a"}]
    source = "{{ rows | sort(attribute='meta.rank') | map(attribute='n') | join }}"
    assert render(source, rows=rows) == "ab"


def test_unique_by_attribute(render):
    assert titles(render, "unique(attribute='year')") == "Zebra crossing|apple pie"


def test_sum_min_max_by_attribute(render):
    assert render("{{ posts | sum(attribute='year') }}", posts=POSTS) == "6070"
    assert render("{{ (posts | min(attribute='title')).title }}", posts=POSTS) == (
        "apple pie"
    )
    assert render("{{ (posts | max(attribute='year')).title }}", posts=POSTS) == (
        "apple pie"
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ ['a', 'b'] | map('upper') | list }}", "['A', 'B']"),
        ("{{ ['abcd', 'efgh'] | map('truncate', 2, true, '', 0) | join }}", "abef"),
        ("{{ [1.4, 2.6] | map('round') | map('int') | list }}", "[1, 3]"),
        ("{{ ['a-b', 'c-d'] | map('replace', '-', '+') | list }}", "['a+b', 'c+d']"),
        ("{{ [{'n': 1}, {'n': 2}] | map(attribute='n') | sum }}", "3"),
        ("{{ [{'n': 1}, {}] | map(attribute='n', default=0) | list }}", "[1, 0]"),
        ("{{ [{'a': {'b': 'deep'}}] | map(attribute='a.b') | first }}", "deep"),
        ("{{ [[1, 2], [3, 4]] | map(attribute=1) | list }}", "[2, 4]"),
        ("{{ [] | map('upper') | list }}", "[]"),
    ],
)
def test_map(render, source, expected):
    assert render(source) == expected


def test_map_errors(render):
    with pytest.raises(TemplateRuntimeError, match="needs a filter name or attribute"):
        render("{{ [1] | map }}")
    with pytest.raises(TemplateRuntimeError, match="unexpected argument 'nope'"):
        render("{{ [1] | map(attribute='x', nope=1) }}")
    with pytest.raises(TemplateRuntimeError, match="no filter named 'shout'"):
        render("{{ ['a'] | map('shout') }}")


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ [0, 1, '', 'a', none] | select | list }}", "[1, 'a']"),
        ("{{ [0, 1, '', 'a', none] | reject | list }}", "[0, '', None]"),
        ("{{ range(6) | select('odd') | list }}", "[1, 3, 5]"),
        ("{{ range(6) | reject('odd') | list }}", "[0, 2, 4]"),
        ("{{ range(10) | select('divisibleby', 3) | list }}", "[0, 3, 6, 9]"),
        ("{{ range(6) | select('gt', 3) | list }}", "[4, 5]"),
        ("{{ ['a', 1, 'b'] | select('string') | join }}", "ab"),
        ("{{ [1, 2, 3] | reject('in', [2, 3]) | list }}", "[1]"),
    ],
)
def test_select_and_reject(render, source, expected):
    assert render(source) == expected


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("selectattr('draft')", "apple pie"),
        ("rejectattr('draft')", "Zebra crossing|Mango lassi"),
        ("selectattr('year', 'eq', 2023)", "Zebra crossing|Mango lassi"),
        ("selectattr('year', '>', 2023)", "apple pie"),
        ("rejectattr('title', 'startingwith', 'Z')", "apple pie|Mango lassi"),
        ("selectattr('tags', 'containing', 'food')", "apple pie|Mango lassi"),
        ("selectattr('tags.0', 'in', ['food'])", "apple pie|Mango lassi"),
        ("selectattr('nope')", ""),
        ("rejectattr('nope', 'defined')", "Zebra crossing|apple pie|Mango lassi"),
    ],
)
def test_selectattr_and_rejectattr(render, expression, expected):
    assert titles(render, expression) == expected


def test_selectattr_needs_an_attribute(render):
    with pytest.raises(TemplateRuntimeError, match="selectattr: needs the name"):
        render("{{ [1] | selectattr }}")
    with pytest.raises(TemplateRuntimeError, match="no test named 'biggish'"):
        render("{{ [1] | select('biggish') }}")


def test_groupby(render):
    source = (
        "{% for year, items in posts | groupby('year') %}"
        "{{ year }}: {{ items | map(attribute='title') | join(', ') }}\n"
        "{% endfor %}"
    )
    assert render(source, posts=POSTS) == (
        "2023: Zebra crossing, Mango lassi\n2024: apple pie\n"
    )


def test_groupby_result_has_named_fields(render):
    source = (
        "{% for group in posts | groupby('draft') %}"
        "{{ group.grouper }}={{ group.list | length }} "
        "{% endfor %}"
    )
    assert render(source, posts=POSTS) == "False=2 True=1 "


def group_sizes(render, rows, arguments):
    source = (
        "{% for key, items in rows | groupby(" + arguments + ") %}"
        "{{ key }}:{{ items | length }} "
        "{% endfor %}"
    )
    return render(source, rows=rows)


def test_groupby_ignores_case_but_keeps_the_first_spelling(render):
    rows = [{"lang": "python"}, {"lang": "Go"}, {"lang": "Python"}, {"lang": "go"}]
    assert group_sizes(render, rows, "'lang'") == "Go:2 python:2 "
    assert group_sizes(render, rows, "'lang', case_sensitive=true") == (
        "Go:1 Python:1 go:1 python:1 "
    )


def test_groupby_default_for_missing_values(render):
    rows = [{"city": "Oslo"}, {}, {"city": "Bergen"}]
    assert group_sizes(render, rows, "'city', default='?'") == "?:1 Bergen:1 Oslo:1 "


def test_groupby_nested_attribute(render):
    rows = [{"a": {"b": 2}}, {"a": {"b": 1}}, {"a": {"b": 2}}]
    assert group_sizes(render, rows, "'a.b'") == "1:1 2:2 "


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ d | dictsort }}", "[('a', 3), ('B', 1), ('c', 2)]"),
        ("{{ d | dictsort(true) }}", "[('B', 1), ('a', 3), ('c', 2)]"),
        ("{{ d | dictsort(by='value') }}", "[('B', 1), ('c', 2), ('a', 3)]"),
        ("{{ d | dictsort(reverse=true) }}", "[('c', 2), ('B', 1), ('a', 3)]"),
        ("{{ d | items | length }}", "3"),
        ("{{ d | items | first }}", "('c', 2)"),
        ("{{ missing | items }}", "[]"),
    ],
)
def test_dict_filters(render, source, expected):
    assert render(source, d={"c": 2, "a": 3, "B": 1}) == expected


def test_dictsort_and_items_errors(render):
    with pytest.raises(TemplateRuntimeError, match='"key" or "value"'):
        render("{{ {} | dictsort(by='size') }}")
    with pytest.raises(TemplateRuntimeError, match="'list' object is not a mapping"):
        render("{{ [1] | items }}")


def test_default(render):
    assert render("{{ missing | default('x') }}") == "x"
    assert render("{{ missing | d('x') }}") == "x"
    assert render("[{{ missing | default }}]") == "[]"
    assert render("{{ value | default('x') }}", value="given") == "given"
    assert render("{{ value | default('x') }}", value="") == ""
    assert render("{{ value | default('x', true) }}", value="") == "x"
    assert render("{{ value | default('x', boolean=true) }}", value=0) == "x"
    assert render("[{{ value | default('x') }}]", value=None) == "[]"
    assert render("{{ page.author.name | default('nobody') }}", page={}) == "nobody"


def test_attr_does_not_fall_back_to_items(render):
    data = {"keys": "the item", "plain": 1}
    assert render("{{ (d | attr('keys'))() | list }}", d=data) == "['keys', 'plain']"
    assert render("[{{ d | attr('plain') }}]", d=data) == "[]"
    assert render("{{ post | attr('title') }}", post=POSTS[0]) == "Zebra crossing"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("a b/c?d=e&f", "a%20b/c%3Fd%3De%26f"),
        ("café", "caf%C3%A9"),
        (42, "42"),
        ({"q": "a b", "page": 2}, "q=a+b&page=2"),
        ([("x", "1/2"), ("y", "ü")], "x=1%2F2&y=%C3%BC"),
        ({}, ""),
    ],
)
def test_urlencode(render, value, expected):
    assert render("{{ value | urlencode }}", value=value) == expected


def test_tojson(render):
    assert render("{{ value | tojson }}", value={"a": [1, 2.5, None, True]}) == (
        '{"a": [1, 2.5, null, true]}'
    )
    assert render("{{ 'café' | tojson }}") == '"café"'
    assert render("{{ value | tojson(2) }}", value={"a": 1}) == '{\n  "a": 1\n}'


def test_tojson_is_safe_inside_script_tags(html_env):
    template = html_env.from_string("<script>var x = {{ value | tojson }};</script>")
    out = template.render(value="</script><b>&'")
    assert out == (
        '<script>var x = "\\u003c/script\\u003e\\u003cb\\u003e\\u0026\\u0027";</script>'
    )


def test_tojson_handles_the_types_a_site_has(render):
    value = {
        "date": datetime.date(2024, 3, 5),
        "when": datetime.datetime(2024, 3, 5, 10, 30),
        "path": PurePosixPath("posts/hello.md"),
        "post": Post("T", 2024, ("x",)),
        "html": Markup("<b>"),
        "tags": ("a", "b"),
        "gen": (n for n in [1, 2]),
    }
    assert render("{{ value | tojson }}", value=value) == (
        '{"date": "2024-03-05", "when": "2024-03-05T10:30:00",'
        ' "path": "posts/hello.md",'
        ' "post": {"title": "T", "year": 2024, "tags": ["x"], "draft": false},'
        ' "html": "\\u003cb\\u003e", "tags": ["a", "b"], "gen": [1, 2]}'
    )
    assert render("{{ {'a': missing} | tojson }}") == '{"a": null}'


def test_tojson_rejects_what_it_can_not_serialise(render):
    with pytest.raises(TemplateRuntimeError, match="can't be turned into JSON"):
        render("{{ value | tojson }}", value=object())


def test_pprint(render):
    assert render("{{ value | pprint }}", value={"b": 1, "a": [1, 2]}) == (
        "{'a': [1, 2], 'b': 1}"
    )


@pytest.mark.parametrize(
    "value, fmt, expected",
    [
        (datetime.date(2024, 3, 5), None, "2024-03-05"),
        (datetime.date(2024, 3, 5), "%d.%m.%Y", "05.03.2024"),
        (datetime.datetime(2024, 3, 5, 14, 7, 9), "%d.%m. %H:%M:%S", "05.03. 14:07:09"),
        (datetime.date(2024, 3, 5), "%-d/%-m/%y", "5/3/24"),
        (datetime.date(2024, 3, 5), "%#d %b %Y", "5 Mar 2024"),
        (datetime.date(2024, 12, 25), "%B %-d, %Y", "December 25, 2024"),
        ("2024-03-05", "%d %B %Y", "05 March 2024"),
        ("2024-03-05T14:07:09", "%H:%M", "14:07"),
        ("2024-03-05 14:07:09+02:00", "%H:%M %z", "14:07 +0200"),
        ("2024-03-05T14:07:09Z", "%Y %z", "2024 +0000"),
        (0, "%Y-%m-%d %H:%M", "1970-01-01 00:00"),
        (1709647629.5, "%Y-%m-%d", "2024-03-05"),
        (None, "%Y", ""),
        ("", "%Y", ""),
    ],
)
def test_date(render, value, fmt, expected):
    source = "{{ value | date }}" if fmt is None else "{{ value | date(fmt) }}"
    assert render(source, value=value, fmt=fmt) == expected


def test_date_now_and_undefined(render):
    this_year = str(datetime.date.today().year)
    assert render("{{ 'now' | date('%Y') }}") == this_year
    assert render("[{{ page.date | date('%Y') }}]", page={}) == "[]"


def test_date_errors(render):
    with pytest.raises(TemplateRuntimeError, match="can't read 'yesterday'"):
        render("{{ 'yesterday' | date }}")
    with pytest.raises(TemplateRuntimeError, match="'list' object is not a date"):
        render("{{ [] | date }}")


def test_date_in_strict_mode_does_not_hide_undefined():
    env = Environment(strict_undefined=True)
    with pytest.raises(UndefinedError):
        env.from_string("{{ page.date | date }}").render(page={})


def test_xmlattr(render):
    attrs = {
        "class": "a b",
        "id": None,
        "title": 'say "hi"',
        "hidden": True,
        "disabled": False,
        "data-n": 3,
    }
    assert render("<a{{ attrs | xmlattr }}>", attrs=attrs) == (
        '<a class="a b" title="say &#34;hi&#34;" hidden data-n="3">'
    )
    assert render("<a{{ {} | xmlattr }}>") == "<a>"
    assert render("<a {{ {'x': 1} | xmlattr(false) }}>") == '<a x="1">'
    with pytest.raises(TemplateRuntimeError, match="not a usable name"):
        render("{{ {'on click': 1} | xmlattr }}")


def test_urlize(render):
    assert render("{{ 'see https://example.org/a?b=1&c=2.' | urlize }}") == (
        'see <a href="https://example.org/a?b=1&amp;c=2">'
        "https://example.org/a?b=1&amp;c=2</a>."
    )
    assert render("{{ 'www.example.org and me@example.org' | urlize }}") == (
        '<a href="https://www.example.org">www.example.org</a> and '
        '<a href="mailto:me@example.org">me@example.org</a>'
    )
    source = "{{ '<b> http://x.org/' | urlize(nofollow=true, target='_blank') }}"
    assert render(source) == (
        '&lt;b&gt; <a href="http://x.org/" rel="nofollow" target="_blank">'
        "http://x.org/</a>"
    )
    assert render("{{ 'http://example.org/long/path' | urlize(18) }}") == (
        '<a href="http://example.org/long/path">http://example.org...</a>'
    )
    assert render("{{ '(http://a.org/x_(y)) (http://b.org)' | urlize }}") == (
        '(<a href="http://a.org/x_(y)">http://a.org/x_(y)</a>) '
        '(<a href="http://b.org">http://b.org</a>)'
    )


def test_unknown_filter_suggests_a_close_match(render):
    with pytest.raises(TemplateRuntimeError) as excinfo:
        render("{{ 'x' | uper }}")
    assert excinfo.value.message == "no filter named 'uper', did you mean 'upper'?"
    with pytest.raises(TemplateRuntimeError) as excinfo:
        render("{{ 'x' | zzzzzz }}")
    assert excinfo.value.message == "no filter named 'zzzzzz'"


def test_filter_called_with_bad_arguments(render):
    with pytest.raises(TemplateRuntimeError, match="TypeError.*unexpected keyword"):
        render("{{ 'x' | upper(loud=true) }}")
