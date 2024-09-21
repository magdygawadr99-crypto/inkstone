"""minify, drafts_banner and footnote_previews: each too small for a file of its own."""

from __future__ import annotations

import pytest

from inkstone.errors import PluginError
from inkstone.markdown import Markdown
from inkstone.plugins.builtin.drafts_banner import DraftsBanner
from inkstone.plugins.builtin.footnote_previews import FootnotePreviews, shorten
from inkstone.plugins.builtin.minify import Minify

from .helpers import make_config, make_page

DOCUMENT = """<!doctype html>
<html>
  <head>
    <title>Page</title>
    <style>
      body { margin: 0; }
    </style>
  </head>
  <body class="kind-page">
    <!-- a comment -->
    <p>Some   text
       over lines.</p>
    <pre>  keep
    this  </pre>
  </body>
</html>
"""


class TestMinify:
    def test_minifies_html_pages(self, config):
        out = Minify(config, {}).page_output(make_page("P", "/p/"), DOCUMENT)
        assert len(out) < len(DOCUMENT)
        assert "<!-- a comment -->" not in out
        assert "<p>Some text over lines.</p>" in out
        assert "<pre>  keep\n    this  </pre>" in out
        assert "body{margin:0}" in out

    def test_settings_are_passed_on(self, config):
        settings = {"remove_comments": False, "inline_css": False}
        out = Minify(config, settings).page_output(make_page("P", "/p/"), DOCUMENT)
        assert "<!-- a comment -->" in out
        assert "margin: 0;" in out

    def test_quotes_can_be_removed(self, config):
        page = make_page("P", "/p/")
        html = '<p class="lead" id="a b">x</p>'
        assert Minify(config, {}).page_output(page, html) == html
        unquoting = Minify(config, {"remove_attribute_quotes": True})
        loose = unquoting.page_output(page, html)
        assert loose == '<p class=lead id="a b">x</p>'

    def test_other_files_are_left_alone(self, config):
        xml = "<feed>\n  <entry>  spaced  </entry>\n</feed>\n"
        feed = make_page("Feed", "/feed.xml")
        assert Minify(config, {}).page_output(feed, xml) == xml

    def test_steps_aside_when_the_build_minifies_already(self, tmp_path):
        config = make_config(tmp_path, **{"build.minify": True})
        page = make_page("P", "/p/")
        assert Minify(config, {}).page_output(page, DOCUMENT) is DOCUMENT

    def test_runs_after_other_plugins(self, config):
        assert Minify(config, {}).priority > DraftsBanner(config, {}).priority

    def test_bad_settings(self, config):
        with pytest.raises(PluginError, match=r"\[plugin.minify\] remove_comments"):
            Minify(config, {"remove_comments": "all"})


class TestDraftsBanner:
    def test_draft_pages_get_a_banner_after_body(self, config):
        page = make_page("Draft", "/d/", draft=True)
        out = DraftsBanner(config, {}).page_output(page, DOCUMENT)
        start = out.index('<body class="kind-page">') + len('<body class="kind-page">')
        banner = '\n<div class="draft-banner" role="status" style="'
        assert out[start:].startswith(banner)
        assert ">Draft: not published</div>" in out
        # nothing else changes
        assert out.replace("\n" + DraftsBanner(config, {}).banner(), "", 1) == DOCUMENT

    def test_published_pages_are_untouched(self, config):
        page = make_page("Fine", "/f/")
        assert DraftsBanner(config, {}).page_output(page, DOCUMENT) is DOCUMENT

    def test_text_class_and_style_settings(self, config):
        settings = {"text": "WIP <draft>", "class": "wip", "style": ""}
        plugin = DraftsBanner(config, settings)
        assert plugin.banner() == (
            '<div class="wip" role="status">WIP &lt;draft&gt;</div>'
        )
        styled = DraftsBanner(config, {"style": 'color: "red"'}).banner()
        assert 'style="color: &quot;red&quot;"' in styled

    def test_documents_without_a_body_are_left_alone(self, config):
        page = make_page("Draft", "/d.xml", draft=True)
        xml = "<feed><title>x</title></feed>"
        assert DraftsBanner(config, {}).page_output(page, xml) == xml

    def test_body_tag_in_any_case(self, config):
        page = make_page("Draft", "/d/", draft=True)
        shouting = "<HTML><BODY>\n<p>x</p></BODY></HTML>"
        out = DraftsBanner(config, {}).page_output(page, shouting)
        assert out.startswith('<HTML><BODY>\n<div class="draft-banner"')

    def test_bad_settings(self, config):
        with pytest.raises(PluginError, match=r"\[plugin.drafts_banner\] text"):
            DraftsBanner(config, {"text": 5})


FOOTNOTES = """\
A claim[^one] and another[^two], and the first again[^one].

[^one]: The *first* note, with `code` & an [inline link](https://example.com/).
[^two]: Second note.

    With a second paragraph.
"""


class TestFootnotePreviews:
    def render(self, config, text=FOOTNOTES, **settings):
        html = Markdown().convert(text)
        return FootnotePreviews(config, settings).page_html(make_page("P"), html)

    def test_references_get_the_note_text(self, config):
        html = self.render(config)
        first = "The first note, with code &amp; an inline link."
        assert (
            f'<a href="#fn-1" id="fnref-1" data-footnote-preview="{first}" '
            f'title="{first}">1</a>'
        ) in html
        assert 'data-footnote-preview="Second note. With a second paragraph."' in html

    def test_every_reference_to_a_note_gets_it(self, config):
        html = self.render(config)
        assert html.count('data-footnote-preview="The first note') == 2

    def test_backlinks_and_notes_are_untouched(self, config):
        html = self.render(config)
        plain = Markdown().convert(FOOTNOTES)
        assert html[html.index('<section class="footnotes">') :] == (
            plain[plain.index('<section class="footnotes">') :]
        )
        assert html.count("data-footnote-preview") == 3

    def test_title_can_be_left_out(self, config):
        html = self.render(config, title=False)
        assert "data-footnote-preview=" in html and "title=" not in html

    def test_attribute_name_is_a_setting(self, config):
        html = self.render(config, attribute="data-note", title=False)
        assert 'data-note="Second note.' in html
        assert "data-footnote-preview" not in html

    def test_long_notes_are_shortened(self, config):
        text = "Text[^1].\n\n[^1]: " + "word " * 200
        html = self.render(config, text, max_length=40)
        assert 'data-footnote-preview="word word word word word word word…"' in html
        full = self.render(config, text, max_length=0)
        assert "word word…" not in full

    def test_quotes_in_notes_are_escaped(self, config):
        html = self.render(config, 'T[^1].\n\n[^1]: She said "no" <b>twice</b>.\n')
        assert 'title="She said &quot;no&quot; twice."' in html

    def test_pages_without_footnotes_are_returned_as_they_are(self, config):
        html = Markdown().convert("No notes here, just [a link](#fn-like).")
        assert FootnotePreviews(config, {}).page_html(make_page("P"), html) is html

    def test_links_into_missing_notes_are_left_alone(self, config):
        html = '<p><a href="#fn-9">9</a></p><ol><li id="fn-1"><p>One.</p></li></ol>'
        assert FootnotePreviews(config, {}).page_html(make_page("P"), html) == html

    @pytest.mark.parametrize(
        "text, limit, expected",
        [
            ("short", 10, "short"),
            ("exactly ten", 11, "exactly ten"),
            ("one two three four", 12, "one two…"),
            ("one two, three", 9, "one two…"),
            ("abcdefghijklmnop", 8, "abcdefg…"),
            ("anything", 0, "anything"),
        ],
    )
    def test_shorten(self, text, limit, expected):
        assert shorten(text, limit) == expected

    def test_bad_settings(self, config):
        with pytest.raises(PluginError, match=r"footnote_previews\] max_length"):
            FootnotePreviews(config, {"max_length": -1})
