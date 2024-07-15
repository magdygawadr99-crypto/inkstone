from __future__ import annotations

import pytest

from inkstone.build import DepGraph
from inkstone.build.depgraph import CONFIG, OUTPUT, SOURCE, TEMPLATE, node, split_node


@pytest.fixture
def graph():
    g = DepGraph()
    g.set("output:a/index.html", ["source:a.md", "template:page.html", "config"])
    g.set("output:b/index.html", ["source:b.md", "template:page.html", "config"])
    g.set("output:index.html", ["source:a.md", "source:b.md", "template:index.html"])
    g.set("template:page.html", ["template:base.html"])
    g.set("template:index.html", ["template:base.html", "template:card.html"])
    return g


def test_node_names():
    assert node(SOURCE, "posts/a.md") == "source:posts/a.md"
    assert node(TEMPLATE, "base.html") == "template:base.html"
    assert node(OUTPUT, "a/index.html") == "output:a/index.html"
    assert node(CONFIG) == "config"
    assert split_node("source:posts/a:b.md") == ("source", "posts/a:b.md")
    assert split_node("config") == ("config", "")


def test_dependencies_and_dependents(graph):
    assert graph.dependencies("output:a/index.html") == {
        "source:a.md",
        "template:page.html",
        "config",
    }
    assert graph.dependencies("nope") == set()
    assert graph.dependents("source:a.md") == {
        "output:a/index.html",
        "output:index.html",
    }
    assert graph.dependents("config") == {"output:a/index.html", "output:b/index.html"}
    assert graph.dependents("nope") == set()
    assert len(graph) == 5
    assert "output:index.html" in graph
    assert "source:a.md" not in graph


def test_returned_sets_are_copies(graph):
    graph.dependencies("output:a/index.html").add("junk")
    graph.dependents("config").clear()
    assert "junk" not in graph.dependencies("output:a/index.html")
    assert graph.dependents("config")


def test_affected_follows_chains(graph):
    assert graph.affected(["template:base.html"]) == {
        "template:page.html",
        "template:index.html",
        "output:a/index.html",
        "output:b/index.html",
        "output:index.html",
    }
    assert graph.affected(["template:card.html"]) == {
        "template:index.html",
        "output:index.html",
    }
    assert graph.affected(["source:b.md"]) == {
        "output:b/index.html",
        "output:index.html",
    }
    assert graph.affected([]) == set()
    assert graph.affected(["never-heard-of-it"]) == set()


def test_affected_outputs_strips_the_prefix(graph):
    assert graph.affected_outputs(["template:page.html"]) == {
        "a/index.html",
        "b/index.html",
    }
    assert graph.affected_outputs(["config", "template:card.html"]) == {
        "a/index.html",
        "b/index.html",
        "index.html",
    }


def test_reasons_names_the_changed_inputs_behind_a_target(graph):
    changed = ["template:base.html", "source:b.md", "source:zzz.md"]
    assert graph.reasons("output:a/index.html", changed) == ["template:base.html"]
    assert graph.reasons("output:index.html", changed) == [
        "source:b.md",
        "template:base.html",
    ]
    assert graph.reasons("output:a/index.html", ["source:b.md"]) == []


def test_set_replaces_earlier_dependencies(graph):
    graph.set("output:a/index.html", ["source:a.md", "template:other.html"])
    assert graph.dependencies("output:a/index.html") == {
        "source:a.md",
        "template:other.html",
    }
    assert graph.dependents("config") == {"output:b/index.html"}
    assert graph.dependents("template:page.html") == {"output:b/index.html"}


def test_add_and_self_references():
    g = DepGraph()
    g.add("output:x", "source:x.md")
    g.add("output:x", "source:x.md")
    g.add("output:x", "output:x")
    g.set("output:y", ["output:y", "source:y.md"])
    assert g.dependencies("output:x") == {"source:x.md"}
    assert g.dependencies("output:y") == {"source:y.md"}


def test_discard_and_prune(graph):
    graph.discard("output:index.html")
    assert "output:index.html" not in graph
    assert graph.dependents("source:a.md") == {"output:a/index.html"}
    assert graph.dependents("template:index.html") == set()
    graph.discard("not there")
    graph.prune(["output:a/index.html"])
    assert list(graph) == ["output:a/index.html"]
    assert graph.dependents("source:b.md") == set()


def test_cycles_do_not_hang():
    g = DepGraph()
    g.set("template:a.html", ["template:b.html"])
    g.set("template:b.html", ["template:a.html"])
    g.set("output:x", ["template:a.html"])
    assert g.affected(["template:a.html"]) == {
        "template:a.html",
        "template:b.html",
        "output:x",
    }
    assert g.reasons("output:x", ["template:b.html"]) == ["template:b.html"]


def test_round_trip_through_plain_data(graph):
    data = graph.to_dict()
    assert data["template:page.html"] == ["template:base.html"]
    assert list(data) == sorted(data)
    assert all(deps == sorted(deps) for deps in data.values())
    again = DepGraph.from_dict(data)
    assert again == graph
    base = "template:base.html"
    assert again.dependents(base) == graph.dependents(base)
    assert graph != DepGraph()
    assert "5 targets" in repr(graph)


@pytest.mark.parametrize("junk", [[], "text", {"a": "b"}, {"a": [1]}, {1: []}])
def test_from_dict_rejects_junk(junk):
    with pytest.raises(ValueError):
        DepGraph.from_dict(junk)
