from __future__ import annotations

import pytest

from inkstone.markdown import Markdown, Table, TableCell, TableRow
from inkstone.markdown.extensions.tables import parse_delimiter_row, split_row

md = Markdown(extensions=["tables"], heading_ids=False)


def table(*rows: str, body: tuple = ()) -> str:
    """Expected markup for a header row and body rows of plain cells."""
    out = ["<table>", "<thead>", "<tr>"]
    out += [f"<th>{cell}</th>" for cell in rows]
    out += ["</tr>", "</thead>"]
    if body:
        out.append("<tbody>")
        for row in body:
            out.append("<tr>")
            out += [f"<td>{cell}</td>" for cell in row]
            out.append("</tr>")
        out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out) + "\n"


def test_simple_table():
    source = "| foo | bar |\n| --- | --- |\n| baz | bim |\n"
    assert md.convert(source) == table("foo", "bar", body=[("baz", "bim")])


def test_outer_pipes_are_optional():
    source = "foo | bar\n--- | ---\nbaz | bim\n"
    assert md.convert(source) == table("foo", "bar", body=[("baz", "bim")])


def test_alignment():
    html = md.convert("| l | c | r | n |\n|:--|:-:|--:|---|\n| 1 | 2 | 3 | 4 |\n")
    assert '<th style="text-align: left">l</th>' in html
    assert '<th style="text-align: center">c</th>' in html
    assert '<th style="text-align: right">r</th>' in html
    assert "<th>n</th>" in html
    assert '<td style="text-align: center">2</td>' in html
    assert "<td>4</td>" in html


def test_alignments_are_recorded_on_the_node():
    doc = md.parse("a | b | c\n:- | :-: | -:\n")
    (tbl,) = doc.children
    assert isinstance(tbl, Table)
    assert tbl.alignments == ["left", "center", "right"]
    assert [cell.align for cell in tbl.children[0].children] == tbl.alignments


def test_cells_contain_inline_markup():
    html = md.convert("| *a* | `b` |\n|---|---|\n| [c](/d) | **e** |\n")
    assert "<th><em>a</em></th>" in html
    assert "<th><code>b</code></th>" in html
    assert '<td><a href="/d">c</a></td>' in html
    assert "<td><strong>e</strong></td>" in html


def test_escaped_pipes_stay_in_the_cell():
    html = md.convert("| a | b |\n|---|---|\n| x \\| y | `p \\| q` |\n")
    assert "<td>x | y</td>" in html
    assert "<td><code>p | q</code></td>" in html


def test_short_rows_are_padded_and_long_rows_cut():
    source = "| a | b |\n|---|---|\n| 1 |\n| 1 | 2 | 3 |\n"
    assert md.convert(source) == table("a", "b", body=[("1", ""), ("1", "2")])


def test_header_only_table_has_no_tbody():
    html = md.convert("| a | b |\n|---|---|\n")
    assert html == table("a", "b")


def test_header_and_delimiter_must_have_the_same_number_of_cells():
    assert md.convert("| a | b |\n|---|\n| 1 | 2 |\n") == (
        "<p>| a | b |\n|---|\n| 1 | 2 |</p>\n"
    )


def test_table_ends_at_blank_line():
    html = md.convert("a | b\n--|--\n1 | 2\n\nafter\n")
    assert html.endswith("</table>\n<p>after</p>\n")


def test_table_ends_where_another_block_starts():
    html = md.convert("a | b\n--|--\n1 | 2\n> quote\n")
    assert html.endswith("</table>\n<blockquote>\n<p>quote</p>\n</blockquote>\n")
    html = md.convert("a | b\n--|--\n1 | 2\n# heading\n")
    assert html.endswith("</table>\n<h1>heading</h1>\n")


def test_line_without_pipes_right_below_is_still_a_row():
    html = md.convert("a | b\n--|--\n1 | 2\nplain\n")
    assert html == table("a", "b", body=[("1", "2"), ("plain", "")])


def test_table_interrupts_a_paragraph():
    html = md.convert("intro line\na | b\n--|--\n1 | 2\n")
    assert html == "<p>intro line</p>\n" + table("a", "b", body=[("1", "2")])


def test_table_inside_list_item_and_quote():
    html = md.convert("- item\n\n  a | b\n  --|--\n  1 | 2\n")
    assert "<li>\n<p>item</p>\n<table>" in html
    html = md.convert("> a | b\n> --|--\n> 1 | 2\n")
    assert html == "<blockquote>\n" + table("a", "b", body=[("1", "2")]) + (
        "</blockquote>\n"
    )


@pytest.mark.parametrize(
    "source",
    [
        "a | b\n=====\n",
        "a | b\n-----\n",
        "a | b\n--x | --\n",
        "    a | b\n    --|--\n",
    ],
)
def test_not_a_table(source):
    assert "<table>" not in md.convert(source)


def test_setext_underline_still_wins_without_pipes():
    assert md.convert("a | b\n-----\n") == "<h2>a | b</h2>\n"


def test_tables_can_be_switched_off():
    source = "a | b\n--|--\n1 | 2\n"
    assert Markdown(extensions=[]).convert(source) == "<p>a | b\n--|--\n1 | 2</p>\n"


def test_rows_and_cells_know_their_source_line():
    doc = md.parse("intro\n\n| a |\n|---|\n| 1 |\n| 2 |\n")
    tbl = doc.children[1]
    assert (tbl.line, tbl.end_line) == (3, 6)
    assert [row.line for row in tbl.children] == [3, 5, 6]
    assert all(isinstance(row, TableRow) for row in tbl.children)
    assert all(isinstance(c, TableCell) for row in tbl.children for c in row.children)
    assert [row.header for row in tbl.children] == [True, False, False]


@pytest.mark.parametrize(
    "line, cells",
    [
        ("| a | b |", ["a", "b"]),
        ("a | b", ["a", "b"]),
        ("|a|b|", ["a", "b"]),
        ("| a | |", ["a", ""]),
        ("||", [""]),
        ("a \\| b | c", ["a | b", "c"]),
        ("  | padded |  ", ["padded"]),
        ("no pipes", ["no pipes"]),
    ],
)
def test_split_row(line, cells):
    assert split_row(line) == cells


@pytest.mark.parametrize(
    "line, expected",
    [
        ("|---|---|", [None, None]),
        ("| :-- | --: | :-: |", ["left", "right", "center"]),
        ("-|-", [None, None]),
        ("---", None),
        ("| --- | abc |", None),
        ("| -- - |", None),
        ("|:|", None),
    ],
)
def test_parse_delimiter_row(line, expected):
    assert parse_delimiter_row(line) == expected
