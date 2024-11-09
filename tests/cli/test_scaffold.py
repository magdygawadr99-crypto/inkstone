from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from inkstone import frontmatter, scaffold, tomlw
from inkstone.config import load_config
from inkstone.errors import InkstoneError
from inkstone.scaffold import content as scaffold_content
from inkstone.scaffold import site as scaffold_site
from inkstone.utils import log

from .conftest import TODAY, needs_toml

EXPECTED = [
    ".gitignore",
    "content/_index.md",
    "content/about.md",
    "content/posts/2024-05-03-first-post.md",
    "content/posts/_index.md",
    "content/search.md",
    "inkstone.toml",
    "static/.gitkeep",
    "templates/.gitkeep",
]


def relative(paths, root):
    return sorted(path.relative_to(root).as_posix() for path in paths)


def tree(root):
    return relative((path for path in root.rglob("*") if path.is_file()), root)


def front_matter(path):
    return frontmatter.parse(path.read_text(encoding="utf-8"))[0]


def make(path, **options):
    options.setdefault("author", "Ada Example")
    options.setdefault("today", TODAY)
    options.setdefault("config_format", "toml")
    return scaffold.create_site(path, **options)


class TestRender:
    @pytest.mark.parametrize(
        "template, expected",
        [
            ("Hello {{name}}!", "Hello World!"),
            ("{{ name }} and {{name}}", "World and World"),
            ("title = {{name|json}}", 'title = "World"'),
            ("title = {{ quoted | json }}", 'title = "say \\"hi\\" \\\\ bye"'),
            ("{{year}}-01-01", "2024-01-01"),
            ("n = {{year|json}}", 'n = "2024"'),
            ("{{unknown}} stays", "{{unknown}} stays"),
            ("{{< note >}} and {{% x %}} stay", "{{< note >}} and {{% x %}} stay"),
            ("{{ Name }} {{name.x}} {name}", "{{ Name }} {{name.x}} {name}"),
            ("{{name|upper}}", "{{name|upper}}"),
            ("", ""),
        ],
    )
    def test_substitution(self, template, expected):
        variables = {"name": "World", "quoted": 'say "hi" \\ bye', "year": 2024}
        assert scaffold.render(template, variables) == expected

    def test_json_keeps_unicode_readable(self):
        assert scaffold.render("{{t|json}}", {"t": "Café Zürich"}) == '"Café Zürich"'


class TestSkeleton:
    def test_files_for_toml_and_yaml(self):
        toml = [rel for rel, _source in scaffold.skeleton_files("toml")]
        yaml = [rel for rel, _source in scaffold.skeleton_files("yaml")]
        assert "inkstone.toml" in toml and "inkstone.yaml" not in toml
        assert "inkstone.yaml" in yaml and "inkstone.toml" not in yaml
        assert set(toml) - {"inkstone.toml"} == set(yaml) - {"inkstone.yaml"}

    def test_dot_prefix_is_turned_into_a_dot(self):
        names = dict(scaffold.skeleton_files())
        assert names[".gitignore"].name == "dot-gitignore"
        assert names["static/.gitkeep"].name == "dot-gitkeep"
        assert not any("dot-" in rel for rel in names)

    def test_sources_live_in_the_package_and_exist(self):
        for _rel, source in scaffold.skeleton_files():
            assert source.is_file()
            assert scaffold.SKELETON in source.parents

    def test_markdown_sources_have_valid_front_matter(self):
        for rel, source in scaffold.skeleton_files():
            if not rel.endswith(".md"):
                continue
            text = source.read_text(encoding="utf-8")
            text = scaffold.render(text, {"date": "2024-05-03"})
            meta, _body = frontmatter.parse(text, path=rel)
            assert meta, rel

    def test_sources_are_tidy(self):
        for rel, source in scaffold.skeleton_files():
            raw = source.read_bytes()
            assert b"\r" not in raw and b"\t" not in raw, rel
            if raw:
                assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), rel

    def test_builtin_themes(self):
        assert {"default", "paper"} <= set(scaffold_site.builtin_themes())


class TestCreateSite:
    def test_writes_the_starter_files(self, tmp_path):
        created = make(tmp_path / "blog", title="My Blog")
        assert tree(tmp_path / "blog") == EXPECTED
        assert relative(created, tmp_path / "blog") == EXPECTED

    @needs_toml
    def test_config_has_title_author_theme_and_comments(self, tmp_path):
        make(tmp_path, title="My Blog", theme="paper")
        text = (tmp_path / "inkstone.toml").read_text(encoding="utf-8")
        assert 'title = "My Blog"' in text
        assert 'theme = "paper"' in text
        assert '[author]\nname = "Ada Example"' in text
        assert text.count("\n# ") > 10
        assert "{{" not in text
        data = tomlw.loads(text)
        assert data["plugins"] == ["shortcodes", "toc", "reading_time"]
        assert data["permalinks"] == {"posts": "/:year/:month/:slug/"}

    @needs_toml
    def test_config_loads_without_warnings(self, tmp_path):
        make(tmp_path, title="My Blog")
        config = load_config(tmp_path)
        assert config.title == "My Blog"
        assert config.author.name == "Ada Example"
        assert config.warnings == []
        assert log.warning_count() == 0

    @pytest.mark.parametrize(
        "title",
        ['Say "cheese"', "Back\\slash", "Café del Mar", "100% #1: yes", "{{title}}"],
    )
    @needs_toml
    def test_awkward_titles_survive(self, tmp_path, title):
        make(tmp_path, title=title, author='A "B" C')
        config = load_config(tmp_path)
        assert config.title == title
        assert config.author.name == 'A "B" C'

    def test_first_post_is_dated_today(self, tmp_path):
        make(tmp_path, title="My Blog")
        post = tmp_path / "content" / "posts" / "2024-05-03-first-post.md"
        meta, body = frontmatter.parse(post.read_text(encoding="utf-8"))
        assert meta == {"title": "First post", "date": TODAY, "tags": ["meta"]}
        assert "The first post of My Blog." in body
        assert "<!-- more -->" in body
        assert "content/posts/2024-05-03-first-post.md" in body
        # shortcodes in the sample are not mistaken for placeholders
        assert '{{< note title="Shortcodes" >}}' in body and "{{< /note >}}" in body

    def test_today_defaults_to_the_real_date(self, tmp_path):
        make(tmp_path, today=None)
        today = dt.datetime.now(dt.timezone.utc).date()
        name = f"{today.isoformat()}-first-post.md"
        assert (tmp_path / "content" / "posts" / name).is_file()

    def test_the_date_is_the_one_in_utc_like_the_new_site(self, tmp_path, monkeypatch):
        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                # late in the evening in UTC: already tomorrow further east
                late = cls(2024, 5, 3, 23, 30, tzinfo=dt.timezone.utc)
                return late.astimezone(tz or dt.timezone(dt.timedelta(hours=3)))

        clock = SimpleNamespace(datetime=Clock, timezone=dt.timezone, date=dt.date)
        monkeypatch.setattr(scaffold_site, "dt", clock)
        make(tmp_path, today=None)
        # a post dated the 4th would count as "in the future" and not be built
        posts = [path.name for path in (tmp_path / "content" / "posts").glob("2*.md")]
        assert posts == ["2024-05-03-first-post.md"]

    def test_other_pages(self, tmp_path):
        make(tmp_path, title="My Blog")
        home = (tmp_path / "content" / "_index.md").read_text(encoding="utf-8")
        assert "Welcome to **My Blog**." in home
        assert front_matter(tmp_path / "content" / "about.md")["title"] == "About"
        search = front_matter(tmp_path / "content" / "search.md")
        assert search["template"] == "search.html"

    def test_gitignore_and_keepers(self, tmp_path):
        make(tmp_path)
        ignored = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert "/public/" in ignored and "/.inkstone-cache/" in ignored
        assert (tmp_path / "static" / ".gitkeep").read_bytes() == b""
        assert (tmp_path / "templates" / ".gitkeep").read_bytes() == b""

    def test_files_use_unix_line_endings(self, tmp_path):
        make(tmp_path)
        for rel in EXPECTED:
            assert b"\r" not in (tmp_path / rel).read_bytes(), rel

    def test_author_comes_from_git_when_not_given(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scaffold_site, "git_user_name", lambda: "From Git")
        make(tmp_path, author=None, config_format="yaml")
        assert load_config(tmp_path).author.name == "From Git"

    def test_git_user_name_copes_without_git(self, monkeypatch):
        def no_git(*args, **kwargs):
            raise FileNotFoundError("git")

        monkeypatch.undo()
        monkeypatch.setattr(scaffold_site.subprocess, "run", no_git)
        assert scaffold_site.git_user_name() == ""

    def test_creates_missing_parents(self, tmp_path):
        make(tmp_path / "a" / "b" / "site")
        assert (tmp_path / "a" / "b" / "site" / "inkstone.toml").is_file()

    def test_an_empty_directory_is_fine(self, tmp_path):
        (tmp_path / "empty").mkdir()
        assert len(make(tmp_path / "empty")) == len(EXPECTED)

    def test_refuses_a_directory_with_things_in_it(self, tmp_path):
        (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")
        with pytest.raises(InkstoneError, match="is not empty .*--force"):
            make(tmp_path)
        assert tree(tmp_path) == ["notes.txt"]

    def test_refuses_a_file(self, tmp_path):
        target = tmp_path / "taken"
        target.write_text("x", encoding="utf-8")
        with pytest.raises(InkstoneError, match="is not a directory"):
            make(target)

    def test_force_adds_what_is_missing_and_keeps_the_rest(self, tmp_path):
        (tmp_path / "content").mkdir()
        (tmp_path / "content" / "about.md").write_text("my own about", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")
        created = make(tmp_path, force=True)
        assert (tmp_path / "content" / "about.md").read_text("utf-8") == "my own about"
        assert tmp_path / "content" / "about.md" not in created
        assert len(created) == len(EXPECTED) - 1
        assert tree(tmp_path) == sorted([*EXPECTED, "notes.txt"])

    def test_force_on_a_complete_site_writes_nothing(self, tmp_path):
        make(tmp_path)
        assert make(tmp_path, force=True) == []

    def test_force_does_not_add_a_second_config_file(self, tmp_path):
        (tmp_path / "inkstone.yaml").write_text("title: Mine\n", encoding="utf-8")
        make(tmp_path, force=True)
        assert not (tmp_path / "inkstone.toml").exists()
        assert load_config(tmp_path).title == "Mine"

    def test_unknown_theme(self, tmp_path):
        with pytest.raises(InkstoneError) as caught:
            make(tmp_path / "x", theme="neon")
        assert "no theme called 'neon'" in str(caught.value)
        assert "default" in str(caught.value) and "paper" in str(caught.value)
        assert not (tmp_path / "x").exists()

    def test_a_local_theme_is_accepted_with_force(self, tmp_path):
        (tmp_path / "themes" / "mine" / "templates").mkdir(parents=True)
        make(tmp_path, theme="mine", force=True)
        assert 'theme = "mine"' in (tmp_path / "inkstone.toml").read_text("utf-8")

    def test_yaml_config_when_toml_cannot_be_read(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tomlw, "tomllib", None)
        make(tmp_path, title='The "YAML" one', config_format=None)
        assert (tmp_path / "inkstone.yaml").is_file()
        assert not (tmp_path / "inkstone.toml").exists()
        config = load_config(tmp_path)
        assert config.title == 'The "YAML" one'
        assert config.plugins == ["shortcodes", "toc", "reading_time"]
        assert config.permalinks.posts == "/:year/:month/:slug/"
        assert config.warnings == []

    def test_config_format_can_be_chosen(self, tmp_path):
        make(tmp_path, config_format="yaml")
        assert (tmp_path / "inkstone.yaml").is_file()
        with pytest.raises(ValueError):
            make(tmp_path / "other", config_format="ini")


@pytest.fixture
def config(tmp_path):
    # whichever format this Python can read back
    make(tmp_path, config_format=None)
    return load_config(tmp_path)


class TestNewPost:
    @pytest.mark.parametrize(
        "title, slug, name",
        [
            ("Hello world", None, "2024-05-03-hello-world.md"),
            ("  Padded  ", None, "2024-05-03-padded.md"),
            ("What's new in 1.2?", None, "2024-05-03-whats-new-in-1-2.md"),
            ("Café & Crème", None, "2024-05-03-cafe-and-creme.md"),
            ("Anything", "custom-slug", "2024-05-03-custom-slug.md"),
            ("Anything", "Not A Slug!", "2024-05-03-not-a-slug.md"),
            ("C++ tips", None, "2024-05-03-c-plus-plus-tips.md"),
        ],
    )
    def test_file_name(self, title, slug, name):
        assert scaffold.post_filename(title, TODAY, slug) == name

    def test_file_name_needs_something_to_work_with(self):
        with pytest.raises(InkstoneError, match="pass --slug"):
            scaffold.post_filename("!!!", TODAY)

    def test_front_matter(self, config):
        path = scaffold.new_post(config, "Hello there", date="2024-06-01")
        assert path == config.content_path / "posts" / "2024-06-01-hello-there.md"
        assert path.read_text(encoding="utf-8") == (
            "---\ntitle: Hello there\ndate: 2024-06-01\ntags: []\n---\n\n"
        )

    def test_draft_tags_and_quoting(self, config):
        path = scaffold.new_post(
            config,
            "Notes: part 1",
            date="2024-06-01",
            draft=True,
            tags=["travel", " photos ", ""],
        )
        meta, body = frontmatter.parse(path.read_text(encoding="utf-8"))
        assert meta == {
            "title": "Notes: part 1",
            "date": dt.date(2024, 6, 1),
            "draft": True,
            "tags": ["travel", "photos"],
        }
        assert list(meta) == ["title", "date", "draft", "tags"]
        assert body == "\n"

    def test_date_defaults_to_today(self, config):
        path = scaffold.new_post(config, "Now")
        today = dt.datetime.now(config.tzinfo).date()
        assert path.name == f"{today.isoformat()}-now.md"
        assert front_matter(path)["date"] == today

    @pytest.mark.parametrize(
        "given, name, stored",
        [
            ("2024-06-01", "2024-06-01-x.md", dt.date(2024, 6, 1)),
            ("June 1, 2024", "2024-06-01-x.md", dt.date(2024, 6, 1)),
            ("2024-06-01 14:30", "2024-06-01-x.md", dt.datetime(2024, 6, 1, 14, 30)),
            (dt.date(2023, 1, 2), "2023-01-02-x.md", dt.date(2023, 1, 2)),
        ],
    )
    def test_dates(self, config, given, name, stored):
        path = scaffold.new_post(config, "X", date=given)
        assert path.name == name
        assert front_matter(path)["date"] == stored

    def test_bad_date(self, config):
        with pytest.raises(InkstoneError, match="--date: "):
            scaffold.new_post(config, "X", date="the day after tomorrow")

    def test_other_and_nested_sections(self, config):
        path = scaffold.new_post(config, "X", section="notes/2024/", date="2024-06-01")
        assert path == config.content_path / "notes" / "2024" / "2024-06-01-x.md"

    def test_never_overwrites(self, config):
        first = scaffold.new_post(config, "Twice", date="2024-06-01")
        first.write_text("edited", encoding="utf-8")
        with pytest.raises(InkstoneError) as caught:
            scaffold.new_post(config, "Twice", date="2024-06-01")
        assert str(caught.value) == (
            "content/posts/2024-06-01-twice.md: already exists, not overwriting it"
        )
        assert first.read_text(encoding="utf-8") == "edited"

    def test_cannot_leave_the_content_directory(self, config):
        with pytest.raises(InkstoneError, match="outside the content directory"):
            scaffold.new_post(config, "X", section="../../elsewhere")

    def test_empty_title(self, config):
        with pytest.raises(InkstoneError, match="needs a title"):
            scaffold.new_post(config, "   ")

    def test_the_new_post_loads_as_a_page(self, config):
        from inkstone.content import load_site

        scaffold.new_post(config, "Fresh: one", date="2024-06-01", tags=["a"])
        page = load_site(config).get_page("posts/2024-06-01-fresh-one.md")
        assert (page.title, page.tags) == ("Fresh: one", ["a"])
        assert page.url == "/2024/06/fresh-one/"


class TestNewPage:
    @pytest.mark.parametrize(
        "given, rel, title",
        [
            ("colophon.md", "colophon.md", "Colophon"),
            ("colophon", "colophon.md", "Colophon"),
            ("projects/my-widget.md", "projects/my-widget.md", "My Widget"),
            ("projects\\my_widget", "projects/my_widget.md", "My Widget"),
            ("/projects/widget.md", "projects/widget.md", "Widget"),
            ("content/projects/widget.md", "projects/widget.md", "Widget"),
            ("trip/", "trip/index.md", "Trip"),
            ("docs/guide/_index.md", "docs/guide/_index.md", "Guide"),
            ("notes/2024-05-03-the-day.md", "notes/2024-05-03-the-day.md", "The Day"),
            ("readme.markdown", "readme.markdown", "Readme"),
        ],
    )
    def test_paths_and_titles(self, config, given, rel, title):
        path = scaffold.new_page(config, given)
        assert path == config.content_path / rel
        assert path.read_text(encoding="utf-8") == f"---\ntitle: {title}\n---\n\n"

    def test_explicit_title(self, config):
        path = scaffold.new_page(config, "x.md", title="Something: else")
        assert front_matter(path) == {"title": "Something: else"}

    @pytest.mark.parametrize(
        "given, message",
        [
            ("", "needs a path"),
            ("  ", "needs a path"),
            ("content/", "needs a path"),
            ("photo.jpg", "pages are Markdown files"),
            ("../outside.md", "outside the content directory"),
            ("a/../../b.md", "outside the content directory"),
        ],
    )
    def test_bad_paths(self, config, given, message):
        with pytest.raises(InkstoneError, match=message):
            scaffold.new_page(config, given)

    def test_never_overwrites(self, config):
        with pytest.raises(InkstoneError, match="content/about.md: already exists"):
            scaffold.new_page(config, "about")

    def test_title_from_path(self):
        title = scaffold_content.title_from_path
        assert title("a/b/the-end-of-it.md") == "The End of It"
        assert title("index.md") == "Index"
