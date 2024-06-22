from __future__ import annotations

import hashlib
import json
import re

import pytest

from inkstone.assets import AssetError, AssetPipeline, Bundle, Manifest, sri_hash
from inkstone.assets.pipeline import CACHE_NAME, BuildReport

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 2
OTHER_PNG = PNG + b"more"
SVG = '<svg xmlns="http://www.w3.org/2000/svg"/>'


def short_hash(data):
    return hashlib.sha256(data).hexdigest()[:8]


def write_tree(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="")
    return root


def output_files(out):
    return sorted(
        path.relative_to(out).as_posix()
        for path in out.rglob("*")
        if path.is_file() and path.name != CACHE_NAME
    )


def read(out, manifest, logical):
    return (out / manifest.url_for(logical)).read_text(encoding="utf-8")


@pytest.fixture
def site(tmp_path):
    return write_tree(
        tmp_path / "static",
        {
            "css/main.css": (
                "body {\n  color: #FFFFFF;\n  background: url(../img/bg.png);\n}\n"
            ),
            "js/app.js": "// greeting\nvar hello = 'world';\n",
            "img/bg.png": PNG,
            "robots.txt": "User-agent: *\n",
        },
    )


@pytest.fixture
def out(tmp_path):
    return tmp_path / "public"


def test_build_minifies_and_fingerprints(site, out):
    manifest = AssetPipeline([site], out).build()
    assert list(manifest) == ["css/main.css", "img/bg.png", "js/app.js", "robots.txt"]

    png = f"img/bg.{short_hash(PNG)}.png"
    assert manifest.url_for("img/bg.png") == png
    assert (out / png).read_bytes() == PNG
    assert re.fullmatch(r"css/main\.[0-9a-f]{8}\.css", manifest.url_for("css/main.css"))
    assert read(out, manifest, "css/main.css") == (
        f"body{{color:#fff;background:url(../{png})}}"
    )
    assert read(out, manifest, "js/app.js") == "var hello='world';"
    assert manifest.url_for("robots.txt") == "robots.txt"
    assert read(out, manifest, "robots.txt") == "User-agent: *\n"
    assert output_files(out) == sorted(manifest.outputs())


def test_manifest_describes_the_output_files(site, out):
    manifest = AssetPipeline([site], out).build()
    for logical, entry in manifest.items():
        data = (out / entry.output).read_bytes()
        assert entry.size == len(data)
        assert entry.hash == hashlib.sha256(data).hexdigest()
        assert entry.integrity == sri_hash(data)
        assert manifest.integrity(logical).startswith("sha384-")
        if logical != "robots.txt":
            assert f".{entry.hash[:8]}." in entry.output


def test_without_fingerprinting(site, out):
    manifest = AssetPipeline([site], out, fingerprint=False).build()
    assert {logical: entry.output for logical, entry in manifest.items()} == {
        name: name for name in manifest
    }
    assert read(out, manifest, "css/main.css") == (
        "body{color:#fff;background:url(../img/bg.png)}"
    )


def test_without_minifying(site, out):
    manifest = AssetPipeline([site], out, minify=False).build()
    for logical in ("js/app.js", "robots.txt", "img/bg.png"):
        copied = (out / manifest.url_for(logical)).read_bytes()
        assert copied == (site / logical).read_bytes()
    # references are still fixed up
    assert read(out, manifest, "css/main.css") == (
        "body {\n  color: #FFFFFF;\n"
        f"  background: url(../img/bg.{short_hash(PNG)}.png);\n}}\n"
    )


def test_well_known_names_are_not_fingerprinted(tmp_path, out):
    names = [
        ".well-known/security.txt",
        "404.html",
        "CNAME",
        "_redirects",
        "favicon.ico",
        "robots.txt",
        "site.webmanifest",
        "sitemap.xml",
        "sw.js",
    ]
    site = write_tree(tmp_path / "static", {name: "x" for name in names})
    write_tree(site, {"js/sw.js": "x", "fonts/a.woff2": b"x"})
    manifest = AssetPipeline([site], out, minify=False).build()
    for name in names:
        assert manifest.url_for(name) == name
    assert manifest.url_for("js/sw.js") == "js/sw.js"
    assert manifest.url_for("fonts/a.woff2") == f"fonts/a.{short_hash(b'x')}.woff2"


def test_custom_no_fingerprint_patterns(site, out):
    manifest = AssetPipeline([site], out, no_fingerprint=["img/*", "app.js"]).build()
    assert manifest.url_for("img/bg.png") == "img/bg.png"
    assert manifest.url_for("js/app.js") == "js/app.js"
    assert manifest.url_for("robots.txt") != "robots.txt"


def test_later_sources_override_earlier_ones(tmp_path, out):
    theme = write_tree(
        tmp_path / "theme",
        {"css/a.css": "a{top:1px}", "css/theme.css": "t{top:1px}", "img/x.png": PNG},
    )
    site = write_tree(
        tmp_path / "site", {"css/a.css": "a{top:2px}", "img/x.png": OTHER_PNG}
    )
    pipeline = AssetPipeline([theme, site, tmp_path / "does-not-exist"], out)
    manifest = pipeline.build()
    assert list(manifest) == ["css/a.css", "css/theme.css", "img/x.png"]
    assert read(out, manifest, "css/a.css") == "a{top:2px}"
    assert read(out, manifest, "css/theme.css") == "t{top:1px}"
    assert (out / manifest.url_for("img/x.png")).read_bytes() == OTHER_PNG
    assert pipeline.scan()["css/a.css"] == site / "css" / "a.css"

    manifest = AssetPipeline([site, theme], out).build()
    assert read(out, manifest, "css/a.css") == "a{top:1px}"


def test_single_source_may_be_passed_bare(site, out):
    assert len(AssetPipeline(site, out).build()) == 4
    assert len(AssetPipeline(str(site), str(out)).build()) == 4


def test_ignore_patterns(site, out):
    write_tree(
        site,
        {
            "js/app.js.map": "{}",
            ".DS_Store": b"\0",
            "img/.DS_Store": b"\0",
            "drafts/a.css": "a{}",
            "drafts/deep/b.css": "b{}",
            "css/old/c.css": "c{top:0}",
            "css/keep.css": "k{top:0}",
        },
    )
    pipeline = AssetPipeline(
        [site], out, ignore=["*.map", ".DS_Store", "drafts", "css/old/*"]
    )
    assert list(pipeline.build()) == [
        "css/keep.css",
        "css/main.css",
        "img/bg.png",
        "js/app.js",
        "robots.txt",
    ]


def test_output_directory_inside_a_source_is_not_scanned(site):
    out = site / "public"
    first = AssetPipeline([site], out).build()
    second = AssetPipeline([site], out).build()
    assert list(first) == list(second) == [
        "css/main.css",
        "img/bg.png",
        "js/app.js",
        "robots.txt",
    ]


def test_imports_are_inlined_and_partials_not_written(tmp_path, out):
    site = write_tree(
        tmp_path / "static",
        {
            "css/main.css": (
                "@import '_vars.css';\n@import 'parts/_type.css' print;\na{top:0}"
            ),
            "css/_vars.css": ":root { --gap: 4px }",
            "css/parts/_type.css": "p { background: url(../../img/bg.png) }",
            "img/bg.png": PNG,
        },
    )
    manifest = AssetPipeline([site], out).build()
    assert list(manifest) == ["css/main.css", "img/bg.png"]
    assert read(out, manifest, "css/main.css") == (
        ":root{--gap:4px}"
        f"@media print{{p{{background:url(../img/bg.{short_hash(PNG)}.png)}}}}"
        "a{top:0}"
    )


def test_absolute_references_honour_base_url(tmp_path, out):
    site = write_tree(
        tmp_path / "static",
        {
            "css/a.css": "a{b:url(/blog/img/bg.png);c:url(/img/bg.png)}",
            "img/bg.png": PNG,
        },
    )
    manifest = AssetPipeline([site], out, base_url="/blog/").build()
    assert read(out, manifest, "css/a.css") == (
        f"a{{b:url(/blog/img/bg.{short_hash(PNG)}.png);c:url(/img/bg.png)}}"
    )


@pytest.fixture
def bundled(tmp_path):
    return write_tree(
        tmp_path / "static",
        {
            "css/reset.css": "* { margin: 0 }\n",
            "css/main.css": (
                "@import 'parts/_type.css';\nbody { background: url(../img/bg.png) }\n"
            ),
            "css/parts/_type.css": "p { background: url(../../img/bg.png) }\n",
            "vendor/lib/lib.css": ".lib { background: url(lib.png) }\n",
            "vendor/lib/lib.png": OTHER_PNG,
            "img/bg.png": PNG,
            "js/a.js": "var a = 1\n",
            "js/b.js": "(function () { window.b = a })()\n",
            "js/vendor/z.min.js": "var z  =  0",
        },
    )


def test_bundles(bundled, out):
    styles = ["css/reset.css", "vendor/lib/lib.css", "css/main.css"]
    scripts = ["js/vendor/*.js", "js/a.js", "js/b.js"]
    pipeline = AssetPipeline(
        [bundled],
        out,
        bundles=[Bundle("css/site.css", styles), Bundle("js/app.js", scripts)],
    )
    manifest = pipeline.build()
    assert list(manifest) == [
        "css/site.css",
        "img/bg.png",
        "js/app.js",
        "vendor/lib/lib.png",
    ]
    bg = f"../img/bg.{short_hash(PNG)}.png"
    lib = f"../vendor/lib/lib.{short_hash(OTHER_PNG)}.png"
    assert read(out, manifest, "css/site.css") == (
        "*{margin:0}\n"
        f".lib{{background:url({lib})}}\n"
        f"p{{background:url({bg})}}body{{background:url({bg})}}\n"
    )
    assert read(out, manifest, "js/app.js") == (
        "var z  =  0;\nvar a=1;\n(function(){window.b=a})();\n"
    )
    assert output_files(out) == sorted(manifest.outputs())


def test_bundle_can_override_minification(bundled, out):
    bundles = [Bundle("js/app.js", ["js/a.js", "js/b.js"], minify=False)]
    manifest = AssetPipeline([bundled], out, bundles=bundles).build()
    assert read(out, manifest, "js/app.js") == (
        "var a = 1;\n(function () { window.b = a })();\n"
    )
    bundles = [Bundle("js/app.js", ["js/a.js", "js/b.js"], minify=True)]
    manifest = AssetPipeline([bundled], out, minify=False, bundles=bundles).build()
    assert read(out, manifest, "js/app.js") == "var a=1;\n(function(){window.b=a})();\n"
    assert read(out, manifest, "css/reset.css") == "* { margin: 0 }\n"


def test_bundle_may_reuse_the_name_of_an_input(bundled, out):
    bundles = [Bundle("css/main.css", ["css/reset.css", "css/main.css"])]
    manifest = AssetPipeline([bundled], out, bundles=bundles).build()
    assert "css/reset.css" not in manifest
    assert read(out, manifest, "css/main.css").startswith("*{margin:0}\np{")


def test_bundle_errors(bundled, out):
    with pytest.raises(AssetError, match="does not match any file") as info:
        AssetPipeline([bundled], out, bundles=[Bundle("x.js", ["js/nope.js"])]).build()
    assert info.value.path == "x.js"
    twice = [Bundle("x.js", ["js/a.js"]), Bundle("x.js", ["js/b.js"])]
    with pytest.raises(AssetError, match="two bundles"):
        AssetPipeline([bundled], out, bundles=twice)


def test_already_minified_files_are_left_alone(bundled, out):
    manifest = AssetPipeline([bundled], out).build()
    assert read(out, manifest, "js/vendor/z.min.js") == "var z  =  0"
    assert read(out, manifest, "js/a.js") == "var a=1"


def test_inline_limit(tmp_path, out):
    site = write_tree(
        tmp_path / "static",
        {
            "css/a.css": (
                "a{background:url(../img/dot.svg)}"
                "b{background:url(../img/bg.png)}"
                "c{background:url(../img/dot.svg#frag)}"
            ),
            "img/dot.svg": SVG,
            "img/bg.png": PNG,
        },
    )
    manifest = AssetPipeline([site], out, inline_limit=100).build()
    dot = f"../img/dot.{short_hash(SVG.encode())}.svg"
    assert read(out, manifest, "css/a.css") == (
        "a{background:url(data:image/svg+xml,"
        "%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22/%3E)}"
        f"b{{background:url(../img/bg.{short_hash(PNG)}.png)}}"
        f"c{{background:url({dot}#frag)}}"
    )
    # the file itself is still published; pages may point at it too
    assert "img/dot.svg" in manifest

    everything = AssetPipeline([site], out, inline_limit=10_000).build()
    assert "url(data:image/png;base64," in read(out, everything, "css/a.css")
    nothing = AssetPipeline([site], out, inline_limit=len(SVG)).build()
    assert "data:" not in read(out, nothing, "css/a.css")


def test_html_and_json_assets(site, out):
    write_tree(
        site,
        {
            "404.html": (
                "<!DOCTYPE html>\n<html>\n  <head>\n"
                '    <link rel="stylesheet" href="/css/main.css">\n  </head>\n'
                '  <body>\n    <img src="img/bg.png">\n  </body>\n</html>\n'
            ),
            "data/search.json": '{\n  "a": [1, 2],\n  "b": "x y"\n}\n',
            "data/broken.json": "{oops",
        },
    )
    manifest = AssetPipeline([site], out).build()
    assert read(out, manifest, "404.html") == (
        '<!doctype html><html><head><link rel="stylesheet" '
        f'href="/{manifest.url_for("css/main.css")}"></head>'
        f'<body><img src="{manifest.url_for("img/bg.png")}"></body></html>'
    )
    assert read(out, manifest, "data/search.json") == '{"a":[1,2],"b":"x y"}'
    assert read(out, manifest, "data/broken.json") == "{oops"


def test_second_build_does_nothing(site, out):
    pipeline = AssetPipeline([site], out)
    first = pipeline.build()
    # stylesheets go last, after the things they refer to
    assert pipeline.report.built == [
        "img/bg.png",
        "js/app.js",
        "robots.txt",
        "css/main.css",
    ]

    def stamps():
        return {name: (out / name).stat().st_mtime_ns for name in output_files(out)}

    before = stamps()
    second = pipeline.build()
    assert second == first
    assert pipeline.report.built == []
    assert sorted(pipeline.report.unchanged) == list(first)
    assert pipeline.report.removed == []
    assert stamps() == before

    # a brand new pipeline object picks the cache up from disk
    fresh = AssetPipeline([site], out)
    assert fresh.build() == first
    assert fresh.report.built == []


def test_changed_file_is_rebuilt_and_its_old_output_removed(site, out):
    pipeline = AssetPipeline([site], out)
    old = pipeline.build().url_for("js/app.js")
    (site / "js" / "app.js").write_text("var hello = 'there';", encoding="utf-8")
    manifest = pipeline.build()
    assert pipeline.report.built == ["js/app.js"]
    assert pipeline.report.removed == [old]
    assert manifest.url_for("js/app.js") != old
    assert read(out, manifest, "js/app.js") == "var hello='there';"
    assert output_files(out) == sorted(manifest.outputs())


def test_same_content_rewritten_is_not_a_change(site, out):
    pipeline = AssetPipeline([site], out)
    pipeline.build()
    path = site / "js" / "app.js"
    path.write_bytes(path.read_bytes())
    pipeline.build()
    assert pipeline.report.built == []


def test_changed_image_rebuilds_the_stylesheet_that_uses_it(site, out):
    pipeline = AssetPipeline([site], out)
    pipeline.build()
    (site / "img" / "bg.png").write_bytes(OTHER_PNG)
    manifest = pipeline.build()
    assert pipeline.report.built == ["img/bg.png", "css/main.css"]
    assert sorted(pipeline.report.unchanged) == ["js/app.js", "robots.txt"]
    assert f"bg.{short_hash(OTHER_PNG)}.png" in read(out, manifest, "css/main.css")
    assert len(pipeline.report.removed) == 2
    assert output_files(out) == sorted(manifest.outputs())


def test_changed_import_rebuilds_the_importer(tmp_path, out):
    site = write_tree(
        tmp_path / "static",
        {
            "css/main.css": "@import '_vars.css';a{top:0}",
            "css/_vars.css": ":root{--gap:4px}",
            "css/other.css": "o{top:0}",
        },
    )
    pipeline = AssetPipeline([site], out)
    pipeline.build()
    (site / "css" / "_vars.css").write_text(":root{--gap:8px}", encoding="utf-8")
    manifest = pipeline.build()
    assert pipeline.report.built == ["css/main.css"]
    assert read(out, manifest, "css/main.css") == ":root{--gap:8px}a{top:0}"


def test_changed_bundle_input_rebuilds_the_bundle(bundled, out):
    bundles = [Bundle("js/app.js", ["js/a.js", "js/b.js"])]
    pipeline = AssetPipeline([bundled], out, bundles=bundles)
    pipeline.build()
    (bundled / "js" / "b.js").write_text("window.b = a", encoding="utf-8")
    manifest = pipeline.build()
    assert pipeline.report.built == ["js/app.js"]
    assert read(out, manifest, "js/app.js") == "var a=1;\nwindow.b=a;\n"


def test_deleted_source_removes_its_output(site, out):
    pipeline = AssetPipeline([site], out)
    old = pipeline.build()
    (site / "img" / "bg.png").unlink()
    (site / "robots.txt").unlink()
    manifest = pipeline.build()
    assert list(manifest) == ["css/main.css", "js/app.js"]
    assert sorted(pipeline.report.removed) == sorted(
        [old.url_for("css/main.css"), old.url_for("img/bg.png"), "robots.txt"]
    )
    assert not (out / "img").exists()
    assert out.is_dir()
    assert read(out, manifest, "css/main.css") == (
        "body{color:#fff;background:url(../img/bg.png)}"
    )
    assert output_files(out) == sorted(manifest.outputs())


def test_everything_deleted(site, out):
    pipeline = AssetPipeline([site], out)
    pipeline.build()
    for path in sorted(site.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    assert len(pipeline.build()) == 0
    assert output_files(out) == []
    assert pipeline.report.summary() == (
        "0 assets: 0 built, 0 unchanged, 4 removed; 0 B -> 0 B"
    )


def test_missing_output_is_rebuilt(site, out):
    pipeline = AssetPipeline([site], out)
    manifest = pipeline.build()
    (out / manifest.url_for("js/app.js")).unlink()
    (out / "robots.txt").write_text("tampered, and a different size", encoding="utf-8")
    assert pipeline.build() == manifest
    assert sorted(pipeline.report.built) == ["js/app.js", "robots.txt"]
    assert read(out, manifest, "robots.txt") == "User-agent: *\n"


def test_changed_settings_rebuild_everything(site, out):
    AssetPipeline([site], out).build()
    pipeline = AssetPipeline([site], out, minify=False)
    manifest = pipeline.build()
    assert len(pipeline.report.built) == 4
    assert pipeline.report.unchanged == []
    # the image came out the same, the minified css and js did not
    assert len(pipeline.report.removed) == 2
    assert output_files(out) == sorted(manifest.outputs())


def test_new_override_in_a_later_source(tmp_path, site, out):
    extra = tmp_path / "extra"
    pipeline = AssetPipeline([site, extra], out)
    pipeline.build()
    write_tree(extra, {"robots.txt": "User-agent: *\nDisallow: /\n"})
    manifest = pipeline.build()
    assert pipeline.report.built == ["robots.txt"]
    assert read(out, manifest, "robots.txt") == "User-agent: *\nDisallow: /\n"


@pytest.mark.parametrize("junk", ["", "{not json", "[]", '{"assets": 3, "config": ""}'])
def test_unreadable_cache_means_a_full_build(site, out, junk):
    pipeline = AssetPipeline([site], out)
    manifest = pipeline.build()
    (out / CACHE_NAME).write_text(junk, encoding="utf-8")
    assert pipeline.build() == manifest
    assert len(pipeline.report.built) == 4
    assert json.loads((out / CACHE_NAME).read_text(encoding="utf-8"))["assets"]


@pytest.mark.parametrize(
    "evil", ["../victim.txt", "sub/../../victim.txt", "/victim.txt", "{abs}"]
)
def test_cache_cannot_make_us_delete_outside_the_output(tmp_path, site, out, evil):
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    pipeline = AssetPipeline([site], out)
    pipeline.build()
    cache = json.loads((out / CACHE_NAME).read_text(encoding="utf-8"))
    record = dict(cache["assets"]["robots.txt"])
    record["output"] = evil.replace("{abs}", victim.as_posix())
    cache["assets"]["gone.txt"] = record
    (out / CACHE_NAME).write_text(json.dumps(cache), encoding="utf-8")
    pipeline.build()
    assert pipeline.report.removed == []
    assert victim.read_text(encoding="utf-8") == "precious"


def test_stale_output_taken_over_by_someone_else_is_kept(site, out):
    pipeline = AssetPipeline([site], out)
    pipeline.build()
    # robots.txt stops being a static file and becomes a rendered page
    (site / "robots.txt").unlink()
    (out / "robots.txt").write_text("rendered by a template", encoding="utf-8")
    manifest = pipeline.build()
    assert "robots.txt" not in manifest
    assert pipeline.report.removed == []
    assert (out / "robots.txt").read_text(encoding="utf-8") == "rendered by a template"
    assert "robots.txt" not in pipeline.clean()
    assert output_files(out) == ["robots.txt"]


def test_other_files_in_the_output_directory_are_left_alone(site, out):
    write_tree(out, {"index.html": "<p>a page</p>", "img/photo.jpg": b"jpeg"})
    pipeline = AssetPipeline([site], out)
    pipeline.build()
    (site / "img" / "bg.png").unlink()
    pipeline.build()
    assert (out / "index.html").read_text(encoding="utf-8") == "<p>a page</p>"
    assert (out / "img" / "photo.jpg").read_bytes() == b"jpeg"
    pipeline.clean()
    assert output_files(out) == ["img/photo.jpg", "index.html"]


def test_clean(site, out):
    pipeline = AssetPipeline([site], out)
    manifest = pipeline.build()
    assert pipeline.clean() == sorted(manifest.outputs())
    assert list(out.iterdir()) == []
    assert pipeline.manifest is None
    assert pipeline.clean() == []
    assert pipeline.build() == manifest
    assert len(pipeline.report.built) == 4


def test_custom_cache_path(tmp_path, site, out):
    cache = tmp_path / "cache" / "assets.json"
    pipeline = AssetPipeline([site], out, cache_path=cache)
    manifest = pipeline.build()
    assert cache.is_file()
    assert not (out / CACHE_NAME).exists()
    assert output_files(out) == sorted(manifest.outputs())
    pipeline.build()
    assert pipeline.report.built == []


@pytest.mark.parametrize(
    "name, content, line, message",
    [
        ("css/broken.css", "a{top:0}\n\n/* never closed", 3, "unterminated comment"),
        ("css/broken.css", "a{top:0}\n}\n", 2, "unexpected '}'"),
        ("css/bad.css", "\n@import 'x.css';", 2, "cannot find imported file 'x.css'"),
        ("js/broken.js", "var a = 1;\nvar b = 'oops\n", 2, "unterminated string"),
        ("page.html", "<p>\n\n\n<!-- never closed", 4, "unterminated comment"),
    ],
)
def test_errors_point_at_the_source_file(site, out, name, content, line, message):
    write_tree(site, {name: content})
    with pytest.raises(AssetError) as info:
        AssetPipeline([site], out).build()
    assert info.value.path == site.joinpath(*name.split("/"))
    assert info.value.line == line
    assert info.value.message == message


def test_error_in_an_imported_file_points_at_that_file(site, out):
    write_tree(
        site, {"css/a.css": "@import '_part.css';", "css/_part.css": "p{top:'oops\n}"}
    )
    with pytest.raises(AssetError) as info:
        AssetPipeline([site], out).build()
    assert info.value.path == site / "css" / "_part.css"
    assert info.value.line == 1


def test_non_utf8_text_is_an_error(site, out):
    write_tree(site, {"css/latin.css": "a{content:'caf\u00e9'}".encode("latin-1")})
    with pytest.raises(AssetError, match="not valid UTF-8") as info:
        AssetPipeline([site], out).build()
    assert info.value.path == site / "css" / "latin.css"
    # binary files do not care
    (site / "css" / "latin.css").rename(site / "css" / "latin.bin")
    assert "css/latin.bin" in AssetPipeline([site], out).build()


def test_rewrite_html(site, out):
    pipeline = AssetPipeline([site], out)
    with pytest.raises(AssetError, match="not been built"):
        pipeline.rewrite_html("<p>hi</p>")
    manifest = pipeline.build()
    css = manifest.url_for("css/main.css")
    png = manifest.url_for("img/bg.png")
    page = '<link rel="stylesheet" href="/css/main.css"><img src="../img/bg.png">'
    assert pipeline.rewrite_html(page) == (
        f'<link rel="stylesheet" href="/{css}"><img src="../img/bg.png">'
    )
    assert pipeline.rewrite_html(page, page_path="blog\\index.html") == (
        f'<link rel="stylesheet" href="/{css}"><img src="../{png}">'
    )
    assert pipeline.rewrite_html(page, integrity=True) == (
        f'<link rel="stylesheet" href="/{css}"'
        f' integrity="{manifest.integrity("css/main.css")}"><img src="../img/bg.png">'
    )


def test_rewrite_html_with_base_url(site, out):
    pipeline = AssetPipeline([site], out, base_url="https://example.com/blog")
    manifest = pipeline.build()
    js = manifest.url_for("js/app.js")
    page = (
        '<script src="https://example.com/blog/js/app.js"></script>'
        '<script src="/blog/js/app.js"></script><script src="/js/app.js"></script>'
    )
    assert pipeline.rewrite_html(page) == (
        f'<script src="https://example.com/blog/{js}"></script>'
        f'<script src="/blog/{js}"></script><script src="/js/app.js"></script>'
    )


def test_report(site, out):
    pipeline = AssetPipeline([site], out)
    assert pipeline.report.total == 0
    manifest = pipeline.build()
    report = pipeline.report
    sources = sum(path.stat().st_size for path in site.rglob("*") if path.is_file())
    assert report.total == 4
    assert report.source_bytes == sources
    assert report.output_bytes == sum(entry.size for _name, entry in manifest.items())
    assert report.saved == report.source_bytes - report.output_bytes > 0
    assert re.fullmatch(
        r"4 assets: 4 built, 0 unchanged; \d+ B -> \d+ B \(\d+% saved\)",
        report.summary(),
    )
    pipeline.build()
    assert pipeline.report.summary().startswith("4 assets: 0 built, 4 unchanged; ")
    assert pipeline.report.source_bytes == sources


@pytest.mark.parametrize(
    "report, expected",
    [
        (BuildReport(), "0 assets: 0 built, 0 unchanged; 0 B -> 0 B"),
        (
            BuildReport(["a"], ["b", "c"], ["x"], 1500, 750),
            "3 assets: 1 built, 2 unchanged, 1 removed; 1.5 kB -> 750 B (50% saved)",
        ),
        (
            BuildReport(["a"], [], [], 2_500_000, 1_250_000),
            "1 assets: 1 built, 0 unchanged; 2.5 MB -> 1.2 MB (50% saved)",
        ),
        (
            BuildReport(["a"], [], [], 100, 140),
            "1 assets: 1 built, 0 unchanged; 100 B -> 140 B",
        ),
    ],
)
def test_report_summary(report, expected):
    assert report.summary() == expected


def test_manifest_survives_a_round_trip_through_disk(site, out, tmp_path):
    manifest = AssetPipeline([site], out).build()
    manifest.save(tmp_path / "assets.json")
    assert Manifest.load(tmp_path / "assets.json") == manifest
