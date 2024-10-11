from __future__ import annotations

import pytest

from inkstone.errors import PluginError
from inkstone.plugins.builtin.related import Related

from .helpers import day, make_page, make_site

SQLITE = "SQLite keeps a whole database in one file, with indexes and a query planner."
BREAD = "Sourdough needs flour, water, salt and a patient baker with a warm kitchen."
GARDEN = "Tomatoes want sun, compost and regular watering through the summer months."


def post(title, tags=(), raw="", date=None, **attrs):
    slug = title.lower().replace(" ", "-")
    return make_page(
        title,
        tags=tags,
        raw=raw,
        date=date or day(2024, 1, 1),
        source_path=f"posts/{slug}.md",
        section="posts",
        **attrs,
    )


def relate(config, pages, **settings):
    site = make_site(config, pages)
    Related(config, settings).content_loaded(site)
    return site


def titles(page):
    return [other.title for other in page.related]


def test_shared_tags_make_pages_related(config):
    a = post("Alpha", ["python", "sqlite"])
    b = post("Beta", ["sqlite"])
    c = post("Gamma", ["bread"])
    relate(config, [a, b, c], text_weight=0.0)
    assert titles(a) == ["Beta"]
    assert titles(b) == ["Alpha"]
    assert c.related == []


def test_every_page_gets_a_list_even_when_empty(config):
    lonely = post("Lonely", raw=BREAD)
    other = post("Other", raw=SQLITE)
    relate(config, [lonely, other])
    assert lonely.related == [] and other.related == []


def test_rare_tags_count_for_more_than_common_ones(config):
    target = post("Target", ["notes", "sqlite"])
    common = post("Shares the common tag", ["notes"])
    rare = post("Shares the rare tag", ["sqlite"])
    filler = [post(f"Filler {n}", ["notes"]) for n in range(6)]
    relate(config, [target, common, rare, *filler], text_weight=0.0, limit=3)
    assert titles(target)[0] == "Shares the rare tag"


def test_more_shared_tags_rank_higher(config):
    target = post("Target", ["a", "b", "c"])
    two = post("Two shared", ["a", "b"])
    one = post("One shared", ["a"])
    relate(config, [target, one, two], text_weight=0.0)
    assert titles(target) == ["Two shared", "One shared"]


def test_text_similarity_finds_untagged_pages(config):
    a = post("Indexes in SQLite", raw=SQLITE)
    b = post("The SQLite query planner", raw=SQLITE + " Planner statistics matter.")
    c = post("Sourdough at home", raw=BREAD)
    d = post("A summer of tomatoes", raw=GARDEN)
    relate(config, [a, b, c, d])
    assert titles(a) == ["The SQLite query planner"]
    assert titles(b) == ["Indexes in SQLite"]
    assert c.related == [] and d.related == []


def test_title_words_weigh_in(config):
    a = post("Sourdough starter", raw="Notes from the first week.")
    b = post("Feeding a sourdough starter", raw="What happened in the second week.")
    c = post("Tomatoes", raw=GARDEN)
    d = post("Databases", raw=SQLITE)
    relate(config, [a, b, c, d])
    assert titles(a) == ["Feeding a sourdough starter"]


def test_code_blocks_do_not_make_pages_similar(config):
    code = "```python\nimport sqlite3\nconnection = sqlite3.connect(path)\n```\n"
    a = post("Baking", raw=BREAD + "\n\n" + code)
    b = post("Gardening", raw=GARDEN + "\n\n" + code)
    c = post("Third", raw="Something else entirely about bicycles and long rides.")
    relate(config, [a, b, c])
    assert a.related == [] and b.related == []


def test_limit(config):
    pages = [post(f"Post {n}", ["shared"]) for n in range(8)]
    relate(config, pages, limit=3, text_weight=0.0)
    assert all(len(page.related) == 3 for page in pages)
    relate(config, pages, limit=0)
    assert all(page.related == [] for page in pages)


def test_min_score_cuts_weak_matches(config):
    target = post("Target", ["a", "b", "c", "d", "e", "f"])
    weak = post("Weak", ["a", "x", "y", "z", "w", "v"])
    strong = post("Strong", ["a", "b", "c", "d", "e"])
    relate(config, [target, weak, strong], text_weight=0.0, min_score=0.5)
    assert titles(target) == ["Strong"]
    relate(config, [target, weak, strong], text_weight=0.0, min_score=0.0)
    assert titles(target) == ["Strong", "Weak"]


def test_ties_go_to_the_newer_page_then_the_title(config):
    target = post("Target", ["t"])
    old = post("Old", ["t"], date=day(2023, 1, 1))
    new = post("New", ["t"], date=day(2024, 6, 1))
    same_b = post("Same day B", ["t"], date=day(2023, 5, 5))
    same_a = post("Same day A", ["t"], date=day(2023, 5, 5))
    relate(config, [old, same_b, target, new, same_a], text_weight=0.0)
    assert titles(target) == ["New", "Same day A", "Same day B", "Old"]


def test_order_does_not_depend_on_input_order(config):
    def build(order):
        pages = [
            post("One", ["x", "y"], raw=SQLITE),
            post("Two", ["x"], raw=SQLITE + " More about indexes."),
            post("Three", ["y"], raw=BREAD),
            post("Four", ["x", "y"], raw=GARDEN),
            post("Five", [], raw=BREAD + " And an oven."),
        ]
        relate(config, [pages[i] for i in order])
        return {page.title: titles(page) for page in pages}

    assert build([0, 1, 2, 3, 4]) == build([4, 2, 0, 3, 1]) == build([3, 4, 1, 2, 0])


def test_tags_are_compared_without_case(config):
    a = post("A", ["Python"])
    b = post("B", ["python "])
    relate(config, [a, b], text_weight=0.0)
    assert titles(a) == ["B"]


def test_other_taxonomies_can_take_part(config):
    a = post("A", categories=["Notes"])
    b = post("B", categories=["Notes"])
    relate(config, [a, b], text_weight=0.0)
    assert a.related == []
    relate(config, [a, b], text_weight=0.0, taxonomies=["tags", "categories"])
    assert titles(a) == ["B"]


def project_page():
    return make_page(
        "Project", tags=["t"], section="projects", source_path="projects/p.md"
    )


def test_sections_setting_limits_the_candidates(config):
    a = post("A", ["t"])
    b = post("B", ["t"])
    project = project_page()
    loose = make_page("About", tags=["t"], source_path="about.md")
    relate(config, [a, b, project, loose], text_weight=0.0, sections=["posts"])
    assert titles(a) == ["B"]
    assert project.related == [] and loose.related == []


def test_same_section_only(config):
    a = post("A", ["t"])
    b = post("B", ["t"])
    project = project_page()
    relate(config, [a, b, project], text_weight=0.0, same_section=True)
    assert titles(a) == ["B"]
    assert project.related == []
    relate(config, [a, b, project], text_weight=0.0)
    assert set(titles(a)) == {"B", "Project"}


def test_front_matter_can_opt_out_or_pick_by_hand(config, capsys):
    a = post("A", ["t"], meta={"related": False})
    b = post("B", ["t"], meta={"related": ["posts/d.md", "posts/missing.md"]})
    c = post("C", ["t"])
    d = post("D", [])
    relate(config, [a, b, c, d], text_weight=0.0)
    assert a.related == []
    # the hand-picked one first, then what the scores say
    assert titles(b) == ["D", "A", "C"]
    assert "related page 'posts/missing.md' not found" in capsys.readouterr().err


def test_a_single_page_site(config):
    only = post("Only", ["t"])
    relate(config, [only])
    assert only.related == []


def test_a_rebuild_only_analyses_what_changed(config, monkeypatch):
    from inkstone.search import Analyzer

    analysed = []
    real = Analyzer.terms

    def counting(self, text):
        analysed.append(text)
        return real(self, text)

    monkeypatch.setattr(Analyzer, "terms", counting)
    a = post("Indexes in SQLite", raw=SQLITE)
    b = post("The SQLite query planner", raw=SQLITE + " Planner statistics.")
    c = post("Sourdough at home", raw=BREAD)
    plugin = Related(config, {"min_score": 0.0})
    plugin.content_loaded(make_site(config, [a, b, c]))
    # body and title of each page
    assert len(analysed) == 6
    assert c.related == []

    c.raw = BREAD + " Now with indexes, a planner and a database in one file."
    plugin.content_loaded(make_site(config, [a, b, c]))
    assert len(analysed) == 8
    # the new text was looked at, not the remembered one
    assert len(c.related) == 2

    # and a page that went away is forgotten
    plugin.content_loaded(make_site(config, [a, b]))
    assert set(plugin._words) == {a.source_path, b.source_path}


@pytest.mark.parametrize(
    "settings",
    [{"limit": -1}, {"limit": "5"}, {"min_score": "high"}, {"taxonomies": 3}],
)
def test_bad_settings(config, settings):
    with pytest.raises(PluginError, match=r"\[plugin.related\]"):
        Related(config, settings)
