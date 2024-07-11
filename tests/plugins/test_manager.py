from __future__ import annotations

import sys
import textwrap
from types import SimpleNamespace

import pytest

from inkstone.errors import ContentError, PluginError
from inkstone.plugins import Plugin, PluginManager, hook_names
from inkstone.plugins import manager as manager_module
from inkstone.utils import log


HELLO = """\
from inkstone.plugins import Plugin


class Hello(Plugin):
    name = "hello"
"""


def make_config(tmp_path, plugins=(), settings=None):
    return SimpleNamespace(
        root=tmp_path,
        plugins=list(plugins),
        plugin=settings or {},
        plugins_path=tmp_path / "plugins",
    )


def write_plugin(tmp_path, name, source):
    directory = tmp_path / "plugins"
    directory.mkdir(exist_ok=True)
    path = directory / f"{name}.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def forget_local_modules():
    yield
    for name in [n for n in sys.modules if n.startswith("_inkstone_site_plugins.")]:
        del sys.modules[name]
    log.reset()


class Recorder(Plugin):
    """Writes down which hooks were called, into a list shared by a test."""

    def __init__(self, name, calls, priority=100):
        super().__init__(None, {})
        self.name = name
        self.priority = priority
        self.calls = calls

    def content_loaded(self, site):
        self.calls.append((self.name, "content_loaded", site))

    def page_html(self, page, html):
        self.calls.append((self.name, "page_html", page))
        return f"{html}<{self.name}>"

    def generate_pages(self, site):
        return [f"{self.name}-page"]


def test_hook_names_lists_the_contract_hooks():
    assert tuple(hook_names) == (
        "setup",
        "content_loaded",
        "page_markdown",
        "page_html",
        "generate_pages",
        "template_context",
        "page_output",
        "extra_files",
        "build_finished",
    )
    assert "page_html" in hook_names


def test_every_hook_has_a_default_on_the_base_class():
    plugin = Plugin(None, None)
    assert plugin.settings == {}
    assert plugin.priority == 100
    for name in hook_names:
        assert callable(getattr(plugin, name))
    assert plugin.page_markdown(None, "text") == "text"
    assert plugin.page_html(None, "<p>") == "<p>"
    assert plugin.page_output(None, "doc") == "doc"
    assert list(plugin.generate_pages(None)) == []
    assert list(plugin.extra_files(None)) == []


def test_plugin_keeps_config_and_a_copy_of_its_settings():
    settings = {"limit": 5}
    plugin = Plugin(config="cfg", settings=settings)
    settings["limit"] = 6
    assert plugin.config == "cfg"
    assert plugin.settings == {"limit": 5}


def test_load_with_an_empty_list_gives_no_plugins(tmp_path):
    manager = PluginManager(make_config(tmp_path))
    assert manager.load() == []
    assert manager.plugins == []
    assert len(manager) == 0
    manager.call("content_loaded", object())
    assert manager.pipe("page_html", "<p>x</p>", object()) == "<p>x</p>"
    assert manager.collect("generate_pages", object()) == []


def test_load_defaults_to_the_configured_names(tmp_path):
    write_plugin(
        tmp_path,
        "hello",
        """
        from inkstone.plugins import Plugin

        class Hello(Plugin):
            name = "hello"
        """,
    )
    manager = PluginManager(make_config(tmp_path, ["hello"]))
    manager.load()
    assert [plugin.name for plugin in manager.plugins] == ["hello"]
    assert manager.get("hello") is manager.plugins[0]
    assert manager.get("nope") is None
    assert "hello" in manager


def test_local_plugin_gets_its_settings_table(tmp_path):
    write_plugin(
        tmp_path,
        "wordstats",
        """
        from inkstone.plugins import Plugin

        class WordStats(Plugin):
            name = "wordstats"
        """,
    )
    settings = {"wordstats": {"skip": ["projects"]}, "other": {"x": 1}}
    config = make_config(tmp_path, ["wordstats"], settings)
    manager = PluginManager(config)
    (plugin,) = manager.load()
    assert plugin.settings == {"skip": ["projects"]}
    assert plugin.config is config


def test_plugin_without_a_name_takes_the_configured_one(tmp_path):
    write_plugin(
        tmp_path,
        "anonymous",
        """
        from inkstone.plugins import Plugin

        class Thing(Plugin):
            pass
        """,
    )
    config = make_config(tmp_path, ["anonymous"], {"anonymous": {"a": 1}})
    (plugin,) = PluginManager(config).load()
    assert plugin.name == "anonymous"
    assert plugin.settings == {"a": 1}


def test_module_attribute_plugin_picks_among_several_classes(tmp_path):
    write_plugin(
        tmp_path,
        "two",
        """
        from inkstone.plugins import Plugin

        class First(Plugin):
            name = "first"

        class Second(Plugin):
            name = "second"

        plugin = Second
        """,
    )
    (plugin,) = PluginManager(make_config(tmp_path, ["two"])).load()
    assert plugin.name == "second"


def test_several_plugin_classes_without_a_pick_is_an_error(tmp_path):
    write_plugin(
        tmp_path,
        "two",
        """
        from inkstone.plugins import Plugin

        class First(Plugin):
            name = "first"

        class Second(Plugin):
            name = "second"
        """,
    )
    with pytest.raises(PluginError, match="several plugins.*First, Second"):
        PluginManager(make_config(tmp_path, ["two"])).load()


def test_shared_base_class_in_the_module_is_not_a_second_plugin(tmp_path):
    write_plugin(
        tmp_path,
        "family",
        """
        from inkstone.plugins import Plugin

        class Base(Plugin):
            def helper(self):
                return 1

        class Real(Base):
            name = "real"
        """,
    )
    (plugin,) = PluginManager(make_config(tmp_path, ["family"])).load()
    assert plugin.name == "real"


def test_module_without_a_plugin_class_is_an_error(tmp_path):
    write_plugin(tmp_path, "empty", "VALUE = 1\n")
    with pytest.raises(PluginError, match="no Plugin subclass"):
        PluginManager(make_config(tmp_path, ["empty"])).load()


def test_plugin_attribute_of_the_wrong_kind_is_an_error(tmp_path):
    write_plugin(tmp_path, "odd", "plugin = 'not a class'\n")
    with pytest.raises(PluginError, match="has to be a Plugin subclass"):
        PluginManager(make_config(tmp_path, ["odd"])).load()


def test_unknown_name_says_where_it_looked(tmp_path):
    with pytest.raises(PluginError) as excinfo:
        PluginManager(make_config(tmp_path, ["no_such_plugin_here"])).load()
    message = str(excinfo.value)
    assert "no_such_plugin_here" in message
    assert "not found" in message
    assert "no_such_plugin_here.py" in message


def test_missing_builtin_plugin_gives_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_module, "BUILTIN_PACKAGE", "inkstone.plugins.not_there")
    with pytest.raises(PluginError, match="built-in plugin 'related' is not available"):
        PluginManager(make_config(tmp_path, ["related"])).load()


def test_local_plugin_stands_in_when_the_builtin_package_is_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(manager_module, "BUILTIN_PACKAGE", "inkstone.plugins.not_there")
    write_plugin(
        tmp_path,
        "toc",
        """
        from inkstone.plugins import Plugin

        class MyToc(Plugin):
            name = "toc"
        """,
    )
    (plugin,) = PluginManager(make_config(tmp_path, ["toc"])).load()
    assert type(plugin).__name__ == "MyToc"


@pytest.mark.parametrize("name", ["../evil", "a b", "", "9lives", "a..b"])
def test_names_that_cannot_be_modules_are_rejected(tmp_path, name):
    with pytest.raises(PluginError):
        PluginManager(make_config(tmp_path, [name])).load()


def test_dotted_name_is_imported_as_a_module(tmp_path, monkeypatch):
    package = tmp_path / "extpkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "inkplug.py").write_text(
        "from inkstone.plugins import Plugin\n\n\n"
        "class External(Plugin):\n    name = 'external'\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    config = make_config(tmp_path, ["extpkg.inkplug"], {"external": {"on": True}})
    try:
        (plugin,) = PluginManager(config).load()
    finally:
        sys.modules.pop("extpkg.inkplug", None)
        sys.modules.pop("extpkg", None)
    assert plugin.name == "external"
    # the settings table goes by the plugin's own name, not the module path
    assert plugin.settings == {"on": True}


def test_syntax_error_in_a_local_plugin_names_file_and_line(tmp_path):
    path = write_plugin(tmp_path, "broken", "def oops(:\n    pass\n")
    with pytest.raises(PluginError) as excinfo:
        PluginManager(make_config(tmp_path, ["broken"])).load()
    assert excinfo.value.path == path
    assert excinfo.value.line == 1
    assert "syntax error" in excinfo.value.message


def test_import_error_inside_a_plugin_is_wrapped(tmp_path):
    write_plugin(tmp_path, "needy", "import a_module_that_does_not_exist_anywhere\n")
    with pytest.raises(PluginError, match="could not be imported.*ModuleNotFoundError"):
        PluginManager(make_config(tmp_path, ["needy"])).load()


def test_exception_in_the_constructor_is_wrapped(tmp_path):
    write_plugin(
        tmp_path,
        "picky",
        """
        from inkstone.plugins import Plugin

        class Picky(Plugin):
            name = "picky"

            def __init__(self, config, settings):
                super().__init__(config, settings)
                raise ValueError("limit must be positive")
        """,
    )
    with pytest.raises(PluginError, match="'picky' could not be set up.*limit must"):
        PluginManager(make_config(tmp_path, ["picky"])).load()


def test_settings_that_are_not_a_table_are_rejected(tmp_path):
    write_plugin(tmp_path, "hello", HELLO)
    config = make_config(tmp_path, ["hello"], {"hello": 3})
    with pytest.raises(PluginError, match=r"\[plugin.hello\] has to be a table"):
        PluginManager(config).load()


def test_a_name_listed_twice_is_loaded_once(tmp_path):
    write_plugin(tmp_path, "hello", HELLO)
    manager = PluginManager(make_config(tmp_path, ["hello", "hello"]))
    assert len(manager.load()) == 1


def test_load_replaces_what_was_loaded_before(tmp_path):
    write_plugin(tmp_path, "hello", HELLO)
    manager = PluginManager(make_config(tmp_path, ["hello"]))
    first = manager.load()[0]
    second = manager.load()[0]
    assert first is not second
    assert manager.plugins == [second]


def test_reloading_picks_up_an_edited_plugin_file(tmp_path):
    source = (
        "from inkstone.plugins import Plugin\n\n\n"
        "class Hello(Plugin):\n    name = 'hello'\n    greeting = '{}'\n"
    )
    path = write_plugin(tmp_path, "hello", source.format("one"))
    manager = PluginManager(make_config(tmp_path, ["hello"]))
    assert manager.load()[0].greeting == "one"
    path.write_text(source.format("two"), encoding="utf-8")
    assert manager.load()[0].greeting == "two"


def test_plugins_run_in_config_order():
    calls = []
    manager = PluginManager(None)
    for name in ("a", "b", "c"):
        manager.add(Recorder(name, calls))
    manager.call("content_loaded", "site")
    assert [name for name, _hook, _arg in calls] == ["a", "b", "c"]


def test_lower_priority_runs_earlier_and_ties_keep_config_order():
    calls = []
    manager = PluginManager(None)
    manager.add(Recorder("late", calls, priority=200))
    manager.add(Recorder("first", calls))
    manager.add(Recorder("second", calls))
    manager.add(Recorder("early", calls, priority=10))
    assert [plugin.name for plugin in manager.plugins] == [
        "early",
        "first",
        "second",
        "late",
    ]
    manager.call("content_loaded", "site")
    assert [name for name, _hook, _arg in calls] == ["early", "first", "second", "late"]


def test_call_passes_arguments_and_returns_nothing():
    calls = []
    manager = PluginManager(None)
    manager.add(Recorder("a", calls))
    site = object()
    assert manager.call("content_loaded", site) is None
    assert calls == [("a", "content_loaded", site)]


def test_call_skips_plugins_that_do_not_implement_the_hook():
    calls = []
    manager = PluginManager(None)
    manager.add(Recorder("a", calls))
    manager.call("build_finished", "site", "report")
    assert calls == []
    assert manager.implementers("build_finished") == []
    assert [p.name for p in manager.implementers("page_html")] == ["a"]


def test_pipe_threads_the_value_through_every_plugin():
    calls = []
    manager = PluginManager(None)
    manager.add(Recorder("a", calls))
    manager.add(Recorder("b", calls))
    page = object()
    assert manager.pipe("page_html", "<p>", page) == "<p><a><b>"
    assert [arg for _name, _hook, arg in calls] == [page, page]


def test_pipe_keeps_the_value_when_a_plugin_forgets_to_return(capsys):
    class Forgetful(Plugin):
        name = "forgetful"

        def page_html(self, page, html):
            html + "ignored"

    manager = PluginManager(None)
    manager.add(Forgetful(None, {}))
    manager.add(Recorder("after", []))
    assert manager.pipe("page_html", "<p>", None) == "<p><after>"
    assert "returned None" in capsys.readouterr().err


def test_collect_flattens_iterables_and_generators():
    class Lists(Plugin):
        name = "lists"

        def generate_pages(self, site):
            return ["a", "b"]

    class Yields(Plugin):
        name = "yields"

        def generate_pages(self, site):
            yield "c"
            yield "d"

    class Nothing(Plugin):
        name = "nothing"

        def generate_pages(self, site):
            return None

    manager = PluginManager(None)
    for cls in (Lists, Yields, Nothing):
        manager.add(cls(None, {}))
    assert manager.collect("generate_pages", "site") == ["a", "b", "c", "d"]


def test_collect_treats_a_lone_path_and_text_pair_as_one_file():
    class OneFile(Plugin):
        name = "one"

        def extra_files(self, site):
            return ("stats.json", "{}")

    class ManyFiles(Plugin):
        name = "many"

        def extra_files(self, site):
            return (("a.txt", "a"), ("b.bin", b"b"))

    manager = PluginManager(None)
    manager.add(OneFile(None, {}))
    manager.add(ManyFiles(None, {}))
    assert manager.collect("extra_files", "site") == [
        ("stats.json", "{}"),
        ("a.txt", "a"),
        ("b.bin", b"b"),
    ]


def test_exception_in_a_hook_becomes_a_plugin_error():
    class Broken(Plugin):
        name = "broken"

        def page_html(self, page, html):
            raise KeyError("missing")

    manager = PluginManager(None)
    manager.add(Broken(None, {}))
    page = SimpleNamespace(source_path="posts/a.md")
    with pytest.raises(PluginError) as excinfo:
        manager.pipe("page_html", "<p>", page)
    error = excinfo.value
    assert "'broken'" in error.message
    assert "page_html" in error.message
    assert "KeyError" in error.message
    assert error.plugin == "broken"
    assert error.hook == "page_html"
    assert error.path == "posts/a.md"
    assert isinstance(error.__cause__, KeyError)


def test_exception_inside_a_generator_hook_is_attributed_too():
    class Lazy(Plugin):
        name = "lazy"

        def generate_pages(self, site):
            yield "fine"
            raise RuntimeError("halfway")

    manager = PluginManager(None)
    manager.add(Lazy(None, {}))
    with pytest.raises(PluginError, match="'lazy' failed in generate_pages.*halfway"):
        manager.collect("generate_pages", "site")


def test_inkstone_errors_from_a_plugin_pass_through_unchanged():
    class Strict(Plugin):
        name = "strict"

        def page_markdown(self, page, text):
            raise ContentError("unknown shortcode 'figur'", path="a.md", line=3)

        def content_loaded(self, site):
            raise PluginError("refusing to continue")

    manager = PluginManager(None)
    manager.add(Strict(None, {}))
    with pytest.raises(ContentError) as excinfo:
        manager.pipe("page_markdown", "text", None)
    assert str(excinfo.value) == "a.md:3: unknown shortcode 'figur'"
    assert excinfo.value.plugin == "strict"
    with pytest.raises(PluginError, match="^refusing to continue$"):
        manager.call("content_loaded", None)


def test_unknown_hook_name_is_an_error():
    manager = PluginManager(None)
    with pytest.raises(PluginError, match="unknown plugin hook 'page_htlm'"):
        manager.call("page_htlm")


def test_add_refuses_things_that_are_not_plugins():
    manager = PluginManager(None)
    with pytest.raises(PluginError, match="not a plugin"):
        manager.add(object())


def test_manager_without_a_config_loads_nothing():
    manager = PluginManager(None)
    assert manager.load() == []


def test_local_plugin_directory_is_derived_from_the_root_when_needed(tmp_path):
    write_plugin(tmp_path, "hello", HELLO)
    config = SimpleNamespace(root=tmp_path, plugins=["hello"], plugin={})
    assert PluginManager(config).load()[0].name == "hello"


def test_plugin_package_directory_is_accepted(tmp_path):
    package = tmp_path / "plugins" / "bundle"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        HELLO.replace("Hello", "Bundle").replace("hello", "bundle"),
        encoding="utf-8",
    )
    assert PluginManager(make_config(tmp_path, ["bundle"])).load()[0].name == "bundle"
