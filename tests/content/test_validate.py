from __future__ import annotations

import pytest

from inkstone.content import Page, Problem, validate_site
from inkstone.content.validate import PROBLEM_KINDS


def kinds(problems):
    return sorted(problem.kind for problem in problems)


def test_clean_site_has_no_problems(files):
    files.page("_index.md", title="Home")
    files.page("about.md", title="About")
    files.page("posts/_index.md", title="Posts")
    files.page("posts/2024-01-01-a.md", title="A", tags=["x"])
    assert validate_site(files.load()) == []


def test_problem_is_a_dataclass_with_a_one_line_report():
    problem = Problem("broken-link", "about/index.html", "no such page", "/nope/", 12)
    assert problem.kind == "broken-link"
    assert problem.target == "/nope/"
    assert str(problem) == "about/index.html:12: broken-link: no such page (/nope/)"
    assert "\n" not in str(problem)
    plain = Problem("missing-title", "a.md", "no title")
    assert plain.target is None and plain.line is None
    assert str(plain) == "a.md: missing-title: no title"
    assert Problem("x", "a", "m") == Problem("x", "a", "m")


def test_target_is_not_repeated_when_the_message_has_it():
    problem = Problem("duplicate-url", "a.md", "same URL as b.md: /x/", target="/x/")
    assert str(problem).count("/x/") == 1


def test_problem_kinds_cover_the_contract():
    assert set(PROBLEM_KINDS) == {
        "broken-link",
        "missing-anchor",
        "missing-image",
        "external-link",
        "duplicate-url",
        "front-matter",
        "missing-title",
        "bad-date",
        "orphan-alias",
    }


def test_duplicate_urls(files):
    files.page("a.md", title="A", url="/same/")
    files.page("b.md", title="B", url="/same/")
    (problem,) = validate_site(files.load())
    assert problem.kind == "duplicate-url"
    assert problem.source == "a.md"
    assert "b.md" in problem.message
    assert "same/index.html" in problem.message
    assert problem.target == "/same/"


def test_page_at_the_address_of_a_taxonomy_page(files):
    files.page("tags.md", title="My tags")
    files.page("posts/a.md", title="A", date="2024-01-01", tags=["x"])
    files.page("other.md", title="Other", url="/tags/x/")
    problems = validate_site(files.load())
    assert kinds(problems) == ["duplicate-url", "duplicate-url"]
    messages = " | ".join(problem.message for problem in problems)
    assert "the list of tags" in messages
    assert "the tag page for 'x'" in messages


def test_missing_title(files):
    files.write("posts/2024-01-01-untitled.md", "Just text.\n")
    files.write("posts/_index.md", "Section text without a title is fine.\n")
    (problem,) = validate_site(files.load())
    assert problem.kind == "missing-title"
    assert problem.source == "posts/2024-01-01-untitled.md"
    assert "'Untitled'" in problem.message


def test_front_matter_typos_are_suggested_with_their_line(files):
    files.write(
        "a.md",
        """
        ---
        title: A
        tag: [x]
        drafts: true
        catagories: [y]
        toc: false
        ---
        """,
    )
    problems = validate_site(files.load())
    assert kinds(problems) == ["front-matter"] * 3
    by_line = {problem.line: problem.message for problem in problems}
    assert by_line == {
        3: "unknown key 'tag', did you mean 'tags'?",
        4: "unknown key 'drafts', did you mean 'draft'?",
        5: "unknown key 'catagories', did you mean 'categories'?",
    }


def test_theme_params_are_not_mistaken_for_typos(files):
    files.write(
        "a.md",
        "---\ntitle: A\ntoc: false\nimage: /a.png\n"
        "author: R\nseries: S\nlayout: x\n---\n",
    )
    assert validate_site(files.load()) == []


def test_custom_taxonomy_names_count_as_known(files):
    files.configure("taxonomies:\n  authors: author\n")
    files.page("a.md", title="A", author="me")
    (problem,) = validate_site(files.load())
    assert problem.message == "unknown key 'author', did you mean 'authors'?"


def test_section_settings_on_a_regular_page(files):
    files.page("a.md", title="A", sort_by="title", paginate=5)
    problems = validate_site(files.load())
    assert kinds(problems) == ["front-matter", "front-matter"]
    assert all("_index.md" in problem.message for problem in problems)


def test_repeated_terms(files):
    files.write("a.md", "---\ntitle: A\ntags: [x, y]\n---\n")
    site = files.load()
    site.get_page("a.md").taxonomies["tags"] = ["x", "", "x"]
    problems = validate_site(site)
    assert kinds(problems) == ["front-matter", "front-matter"]
    messages = sorted(problem.message for problem in problems)
    assert messages == ["tags contains an empty entry", "tags lists x more than once"]


def test_updated_before_date(files):
    files.page("a.md", title="A", date="2024-05-03", updated="2024-05-01")
    (problem,) = validate_site(files.load())
    assert problem.kind == "bad-date"
    assert "updated (2024-05-01) is earlier than date (2024-05-03)" in problem.message
    assert problem.line == 4


def test_file_name_that_only_looks_like_a_date(files):
    files.page("notes/2024-13-45-nope.md", title="Nope")
    (problem,) = validate_site(files.load())
    assert problem.kind == "bad-date"
    assert "'2024-13-45'" in problem.message


def test_undated_page_under_a_dated_permalink_pattern(files):
    files.page("posts/someday.md", title="Someday")
    (problem,) = validate_site(files.load())
    assert problem.kind == "bad-date"
    assert problem.source == "posts/someday.md"
    assert "/:year/:month/:slug/" in problem.message
    assert "/posts/someday/" in problem.message


def test_aliases_without_the_redirects_plugin(files):
    files.page("a.md", title="A", aliases=["/old-a/"])
    files.page("b.md", title="B", aliases=["/old-b/"])
    problems = validate_site(files.load())
    # said once, not for every page
    assert kinds(problems) == ["orphan-alias"]
    assert "'redirects' plugin is not enabled" in problems[0].message


def test_aliases_that_cannot_work(files):
    files.configure("plugins: [redirects]\n")
    files.page("a.md", title="A", aliases=["/a/", "/b/", "/shared/", "/fine/"])
    files.page("b.md", title="B", aliases=["/shared/"])
    problems = validate_site(files.load())
    assert kinds(problems) == ["orphan-alias"] * 3
    by_target = {problem.target: problem for problem in problems}
    assert "own URL" in by_target["/a/"].message
    assert "the URL of b.md" in by_target["/b/"].message
    assert by_target["/shared/"].source == "b.md"
    assert "also claimed by a.md" in by_target["/shared/"].message
    assert by_target["/a/"].line == 3


def test_generated_pages_are_not_checked_for_front_matter(files):
    files.page("a.md", title="A")
    site = files.load()
    site.add_page(Page.virtual("/archive/", template="archive.html"))
    assert validate_site(site) == []


def test_problems_from_a_lenient_load_are_included(files):
    files.page("good.md", title="Good")
    files.write("bad.md", "---\ndraft: maybe\n---\n")
    problems = validate_site(files.load(strict=False))
    (problem,) = problems
    assert problem.kind == "front-matter"
    assert problem.source == "bad.md"
    assert "draft must be true or false" in problem.message


def test_problems_come_back_sorted(files):
    files.write("z.md", "Text.\n")
    files.write("a.md", "---\ntitel: A\n---\n")
    problems = validate_site(files.load())
    assert [problem.source for problem in problems] == ["a.md", "a.md", "z.md"]


@pytest.mark.parametrize("drafts", [True, False])
def test_drafts_are_only_checked_when_they_are_built(files, drafts):
    files.write("wip.md", "---\ndraft: true\n---\nNo title yet.\n")
    problems = validate_site(files.load(drafts=drafts))
    assert kinds(problems) == (["missing-title"] if drafts else [])
