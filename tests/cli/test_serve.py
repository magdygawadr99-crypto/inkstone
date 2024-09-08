from __future__ import annotations

from pathlib import Path

import pytest

from inkstone.cli import serve as serve_command
from inkstone.errors import InkstoneError
from inkstone.server import DEFAULT_IGNORE, ChangeSet

from .conftest import configure, write

POST = "public/2024/05/first-post/index.html"
BROKEN = "---\ntitle: Bad\n---\n\n{{< frobnicate >}}\n"


class FakeServer:
    """Records how `inkstone serve` drives the dev server, and serves nothing."""

    instances: list = []
    # what start() pretends the port turned out to be; None keeps the one asked for
    bound_port = None
    # called with the server once it is "serving", to play the part of time passing
    while_serving = None

    def __init__(self, root, **options):
        self.root = Path(root)
        self.options = options
        self.host = options["host"]
        self.port = options["port"]
        self.calls = []
        self.requested = []
        FakeServer.instances.append(self)

    @property
    def url(self):
        host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
        return f"http://{host}:{self.port}/"

    def start(self):
        self.calls.append("start")
        if self.bound_port is not None:
            self.port = self.bound_port

    def request_rebuild(self, changes=None):
        self.requested.append(changes)

    def serve_forever(self):
        self.calls.append("serve_forever")
        if FakeServer.while_serving is not None:
            FakeServer.while_serving(self)

    def stop(self):
        self.calls.append("stop")


@pytest.fixture
def server(monkeypatch, builder):
    FakeServer.instances = []
    FakeServer.bound_port = None
    FakeServer.while_serving = None
    monkeypatch.setattr(serve_command, "DevServer", FakeServer)
    return FakeServer


def started(server):
    assert len(server.instances) == 1
    return server.instances[0]


def test_builds_then_serves_the_output_directory(run, site, server):
    result = run("serve")
    assert result.code == 0
    fake = started(server)
    assert fake.root == (site / "public").resolve()
    assert fake.calls[:2] == ["start", "serve_forever"]
    assert fake.calls[-1] == "stop"
    # built before the server came up
    assert (site / POST).is_file()
    assert result.out == "Serving on http://127.0.0.1:8000/ (Ctrl-C to stop)\n"
    assert " written" in result.err and result.err.endswith("stopped\n")


def test_defaults_come_from_the_config(run, site, server):
    run("serve")
    options = started(server).options
    assert (options["host"], options["port"]) == ("127.0.0.1", 8000)
    assert options["livereload"] is True
    assert options["open_browser"] is False
    assert callable(options["rebuild"]) and callable(options["log"])


def test_server_table_in_the_config(run, site, server):
    table = '[server]\nhost = "0.0.0.0"\nport = 9001\nlivereload = false\nopen = true\n'
    configure(site, append="\n" + table)
    result = run("serve")
    options = started(server).options
    assert (options["host"], options["port"]) == ("0.0.0.0", 9001)
    assert options["livereload"] is False
    assert options["open_browser"] is True
    assert "Serving on http://127.0.0.1:9001/" in result.out


def test_flags_win_over_the_config(run, site, server):
    run("serve", "--host", "localhost", "--port", "8123", "--no-livereload", "--open")
    options = started(server).options
    assert (options["host"], options["port"]) == ("localhost", 8123)
    assert options["livereload"] is False
    assert options["open_browser"] is True


def test_port_zero_is_passed_on(run, site, server):
    run("serve", "--port", "0")
    assert started(server).options["port"] == 0


def test_watches_the_sources_and_the_config(run, site, server):
    run("serve")
    watched = [Path(path) for path in started(server).options["watch"]]
    for name in ("content", "templates", "static", "data", "themes", "plugins"):
        assert (site / name).resolve() in watched, name
    assert (site / "inkstone.toml").resolve() in watched
    # the built-in theme, which lives inside the package
    assert any(path.parts[-2:] == ("themes", "default") for path in watched)
    assert (site / "public").resolve() not in watched
    assert len(watched) == len(set(watched))


def test_ignore_patterns(run, site, server):
    configure(site, prepend='ignore = ["*.bak", "drafts/"]\n')
    run("serve")
    ignore = started(server).options["ignore"]
    assert set(DEFAULT_IGNORE) <= set(ignore)
    assert "*.bak" in ignore and "drafts/" in ignore


def test_base_url_becomes_the_local_address(run, site, server):
    configure(site, replace={"http://localhost:8000/": "https://example.com/blog/"})
    run("serve", "--port", "8123")
    html = (site / POST).read_text(encoding="utf-8")
    assert 'rel="canonical" href="http://127.0.0.1:8123/2024/05/first-post/"' in html
    assert "example.com" not in html
    assert 'href="/css/main.css"' in html


def test_a_plain_build_afterwards_uses_the_real_base_url_again(run, site, server):
    run("serve")
    run("build", "--base-url", "https://example.com/")
    html = (site / POST).read_text(encoding="utf-8")
    assert 'href="https://example.com/2024/05/first-post/"' in html


def test_drafts_and_future_flags(run, site, server):
    draft = "---\ntitle: WIP\ndate: 2024-05-04\ndraft: true\n---\n\nSoon.\n"
    write(site / "content" / "posts" / "wip.md", draft)
    run("serve")
    assert not (site / "public" / "2024" / "05" / "wip").exists()
    run("serve", "--drafts")
    assert (site / "public" / "2024" / "05" / "wip" / "index.html").is_file()


def test_rebuild_callback_builds_again_and_reports_what_changed(run, site, server):
    outputs = {}

    def edit_and_rebuild(fake):
        post = site / "content" / "posts" / "2024-05-03-first-post.md"
        post.write_text(
            post.read_text("utf-8").replace("First post", "Second thoughts"), "utf-8"
        )
        rebuild = fake.options["rebuild"]
        outputs["changed"] = rebuild(ChangeSet(modified=[post]))
        outputs["unchanged"] = rebuild(ChangeSet())

    server.while_serving = edit_and_rebuild
    assert run("serve").code == 0
    assert "2024/05/first-post/index.html" in outputs["changed"]
    assert "index.html" in outputs["changed"]
    assert "about/index.html" not in outputs["changed"]
    assert outputs["unchanged"] == []
    assert "<title>Second thoughts" in (site / POST).read_text(encoding="utf-8")


def test_rebuild_callback_wants_a_full_reload_after_deletions(run, site, server):
    outputs = {}

    def delete_and_rebuild(fake):
        about = site / "content" / "about.md"
        about.unlink()
        outputs["result"] = fake.options["rebuild"](ChangeSet(removed=[about]))

    server.while_serving = delete_and_rebuild
    run("serve")
    assert outputs["result"] is None
    assert not (site / "public" / "about").exists()


def test_rebuild_callback_lets_build_errors_through(run, site, server):
    caught = {}

    def break_and_rebuild(fake):
        bad = write(site / "content" / "bad.md", BROKEN)
        try:
            fake.options["rebuild"](ChangeSet(added=[bad]))
        except InkstoneError as exc:
            caught["error"] = str(exc)

    server.while_serving = break_and_rebuild
    assert run("serve").code == 0
    # the dev server turns the exception into the overlay in the browser
    assert caught["error"] == "content/bad.md:5: unknown shortcode 'frobnicate'"


def test_config_edits_are_picked_up_with_the_overrides_kept(run, site, server):
    def retitle_and_rebuild(fake):
        config = site / "inkstone.toml"
        text = config.read_text("utf-8").replace('"Test Site"', '"Renamed"')
        config.write_text(text.replace("localhost:8000", "example.org"), "utf-8")
        fake.options["rebuild"](ChangeSet(modified=[config]))

    server.while_serving = retitle_and_rebuild
    run("serve")
    html = (site / POST).read_text(encoding="utf-8")
    assert "Renamed" in html
    assert 'rel="canonical" href="http://127.0.0.1:8000/' in html


def test_a_taken_port_means_building_again_for_the_new_address(run, site, server):
    server.bound_port = 8001
    result = run("serve")
    assert result.code == 0
    assert result.out == "Serving on http://127.0.0.1:8001/ (Ctrl-C to stop)\n"
    html = (site / POST).read_text(encoding="utf-8")
    assert 'rel="canonical" href="http://127.0.0.1:8001/' in html
    assert started(server).requested == []


def test_a_site_that_does_not_build_is_served_anyway(run, site, server):
    write(site / "content" / "bad.md", BROKEN)
    result = run("serve")
    assert result.code == 0
    fake = started(server)
    assert "error: content/bad.md:5: unknown shortcode 'frobnicate'\n" in result.err
    assert "serve_forever" in fake.calls
    # asked to build once more, so the error also reaches the browser
    assert len(fake.requested) == 1
    assert "Serving on http://127.0.0.1:8000/" in result.out


def test_broken_config_stops_before_the_server_starts(run, site, server):
    write(site / "inkstone.toml", "title = 5\n")
    result = run("serve")
    assert result.code == 1
    assert server.instances == []
    assert "title must be a string" in result.err


def test_config_warnings_are_printed_once(run, site, server):
    configure(site, prepend="titel = 'typo'\n")
    result = run("serve")
    assert result.err.count("unknown setting 'titel'") == 1


def test_server_failing_to_start_is_an_error(run, site, server, monkeypatch):
    from inkstone.server import ServerError

    def refuse(self):
        raise ServerError("cannot listen on 127.0.0.1:80: permission denied")

    monkeypatch.setattr(FakeServer, "start", refuse)
    result = run("serve", "--port", "80")
    assert result.code == 1
    assert result.err.endswith(
        "error: cannot listen on 127.0.0.1:80: permission denied\n"
    )
    assert started(server).calls == ["stop"]


def test_ctrl_c_during_the_first_build(run, site, server, builder, monkeypatch):
    class Interrupted(builder.Builder):
        def build(self, changed=None):
            raise KeyboardInterrupt

    monkeypatch.setattr(builder, "Builder", Interrupted)
    assert run("serve").code == 130


def test_quiet(run, site, server):
    result = run("-q", "serve")
    assert (result.code, result.out, result.err) == (0, "", "")


def test_outside_a_site(run, tmp_path, monkeypatch, server):
    monkeypatch.chdir(tmp_path)
    result = run("serve")
    assert result.code == 1
    assert server.instances == []


def test_watch_paths_without_a_theme(site):
    from inkstone.config import load_config

    configure(site, replace={'theme = "default"': 'theme = "gone"'})
    paths = serve_command.watch_paths(load_config(site))
    assert (site / "content").resolve() in paths
    assert not any("gone" in str(path) for path in paths)
