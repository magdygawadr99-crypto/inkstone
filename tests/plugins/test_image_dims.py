from __future__ import annotations

import struct

import pytest

from inkstone.content import Resource
from inkstone.errors import PluginError
from inkstone.plugins.builtin.image_dims import ImageDims

from .helpers import make_config, make_page, make_site


def png(width, height):
    header = struct.pack(">I4sIIBBBBB", 13, b"IHDR", width, height, 8, 2, 0, 0, 0)
    end = struct.pack(">I4sI", 0, b"IEND", 0)
    return b"\x89PNG\r\n\x1a\n" + header + b"\x00" * 4 + end


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def images(config):
    put(config.static_path / "img" / "wide.png", png(800, 400))
    put(config.static_path / "img" / "with space.png", png(30, 20))
    put(config.static_path / "broken.png", b"\x89PNG\r\n\x1a\nnot really")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"></svg>'
    put(config.static_path / "logo.svg", svg)
    return config.static_path


def run(config, html, page=None, **settings):
    plugin = ImageDims(config, settings)
    page = page or make_page("Post", "/posts/post/")
    plugin.content_loaded(make_site(config, [page]))
    return plugin.page_html(page, html)


def test_adds_width_and_height(config, images):
    html = run(config, '<p><img src="/img/wide.png" alt="Wide"></p>')
    assert html == (
        '<p><img src="/img/wide.png" alt="Wide" width="800" height="400" '
        'loading="lazy" decoding="async"></p>'
    )


def test_self_closing_tags_stay_self_closing(config, images):
    html = run(config, '<img src="/logo.svg" alt="" />')
    assert html == (
        '<img src="/logo.svg" alt="" width="120" height="80" loading="lazy" '
        'decoding="async" />'
    )


@pytest.mark.parametrize(
    "src",
    [
        "/img/wide.png?v=3",
        "/img/wide.png#top",
        "/img/../img/wide.png",
        "../../img/wide.png",
    ],
)
def test_ways_of_writing_the_same_file(config, images, src):
    assert 'width="800" height="400"' in run(config, f'<img src="{src}">')


def test_percent_encoded_names(config, images):
    assert 'width="30" height="20"' in run(config, '<img src="/img/with%20space.png">')


@pytest.mark.parametrize(
    "src",
    [
        "https://other.example/a.png",
        "//cdn.example/a.png",
        "data:image/png;base64,AAAA",
        "/img/missing.png",
        "/broken.png",
        "/../../outside.png",
        "",
    ],
)
def test_images_we_cannot_measure_only_get_the_loading_hints(config, images, src):
    html = run(config, f'<img src="{src}" alt="x">')
    assert "width=" not in html and "height=" not in html
    assert html == f'<img src="{src}" alt="x" loading="lazy" decoding="async">'


def test_existing_dimensions_are_kept(config, images):
    html = run(config, '<img src="/img/wide.png" width="100" height="100">')
    assert 'width="100" height="100"' in html
    assert "800" not in html


@pytest.mark.parametrize(
    "given, added",
    [
        ('width="200"', 'height="100"'),
        ('height="100"', 'width="200"'),
        ('width="201"', 'height="100"'),
        ('width="80px"', 'height="40"'),
    ],
)
def test_one_given_side_keeps_the_aspect_ratio(config, images, given, added):
    html = run(config, f'<img src="/img/wide.png" {given}>')
    assert given in html and added in html
    assert "800" not in html


def test_a_percentage_width_is_left_alone(config, images):
    html = run(config, '<img src="/img/wide.png" width="50%">')
    assert 'width="50%"' in html and "height=" not in html


def test_bundle_resources(config):
    photo = put(config.content_path / "posts" / "trip" / "photo.png", png(640, 480))
    resource = Resource(
        "photo.png", "/posts/trip/photo.png", "posts/trip/photo.png", path=photo
    )
    page = make_page("Trip", "/posts/trip/", resources=[resource])
    html = run(config, '<img src="photo.png"><img src="/posts/trip/photo.png">', page)
    assert html.count('width="640" height="480"') == 2


def test_resources_without_a_path_are_found_below_the_content_dir(config):
    put(config.content_path / "posts" / "trip" / "map.png", png(10, 20))
    resource = Resource("map.png", "/posts/trip/map.png", "posts/trip/map.png")
    page = make_page("Trip", "/posts/trip/", resources=[resource])
    assert 'width="10" height="20"' in run(config, '<img src="map.png">', page)


def test_another_pages_resource_by_its_url(config):
    photo = put(config.content_path / "posts" / "trip" / "photo.png", png(64, 48))
    owner = make_page(
        "Trip",
        "/posts/trip/",
        resources=[Resource("photo.png", "/posts/trip/photo.png", "x", path=photo)],
    )
    other = make_page("Other", "/posts/other/")
    plugin = ImageDims(config, {})
    plugin.content_loaded(make_site(config, [owner, other]))
    html = plugin.page_html(other, '<img src="../trip/photo.png">')
    assert 'width="64" height="48"' in html


def test_theme_static_files_are_found(config):
    html = run(config, '<img src="/favicon.svg">')
    assert "width=" in html and "height=" in html


def test_site_static_wins_over_the_theme(config):
    put(config.static_path / "favicon.svg", png(7, 9))
    assert 'width="7" height="9"' in run(config, '<img src="/favicon.svg">')


def test_base_path_is_stripped(tmp_path):
    config = make_config(tmp_path, base_url="https://example.com/blog/")
    put(config.static_path / "a.png", png(5, 6))
    assert 'width="5" height="6"' in run(config, '<img src="/blog/a.png">')


def test_loading_hints_do_not_override(config, images):
    html = run(config, '<img src="/img/wide.png" loading="eager" decoding="sync">')
    assert 'loading="eager" decoding="sync"' in html
    assert "lazy" not in html and "async" not in html


def test_hints_can_be_switched_off(config, images):
    html = run(config, '<img src="/img/wide.png">', lazy=False, **{"async": False})
    assert html == '<img src="/img/wide.png" width="800" height="400">'


def test_first_images_can_stay_eager(config, images):
    three = '<img src="/a.png"><img src="/b.png"><img src="/c.png">'
    html = run(config, three, eager=2)
    first, second, third = html.split("><")
    assert "lazy" not in first and "lazy" not in second
    assert 'loading="lazy"' in third
    assert html.count('decoding="async"') == 3


def test_code_is_not_touched(config, images):
    html = '<pre><code>&lt;img src="/img/wide.png"&gt;</code></pre>'
    assert run(config, html) == html
    inline = '<code><img src="/img/wide.png"></code>'
    assert run(config, inline) == inline


def test_html_without_images_is_returned_as_is(config):
    html = "<p>No pictures.</p>"
    assert run(config, html) is html


def test_sizes_are_read_once_per_build(config, images, monkeypatch):
    from inkstone.plugins.builtin import image_dims

    calls = []
    real = image_dims.image_info

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(image_dims, "image_info", counting)
    plugin = ImageDims(config, {})
    page = make_page("P")
    site = make_site(config, [page])
    plugin.content_loaded(site)
    for _ in range(3):
        plugin.page_html(page, '<img src="/img/wide.png"><img src="/broken.png">')
    assert len(calls) == 2
    plugin.content_loaded(site)
    plugin.page_html(page, '<img src="/img/wide.png">')
    assert len(calls) == 3


def test_works_without_content_loaded(config, images):
    html = ImageDims(config, {}).page_html(make_page("P"), '<img src="/img/wide.png">')
    assert 'width="800"' in html


@pytest.mark.parametrize("settings", [{"lazy": "yes"}, {"eager": -1}, {"eager": True}])
def test_bad_settings(config, settings):
    with pytest.raises(PluginError, match=r"\[plugin.image_dims\]"):
        ImageDims(config, settings)
