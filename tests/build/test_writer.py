from __future__ import annotations

import os

import pytest

from inkstone.build import OutputWriter
from inkstone.build.writer import normalise_output_path
from inkstone.errors import BuildError


@pytest.fixture
def writer(tmp_path):
    return OutputWriter(tmp_path / "public")


def test_write_creates_directories(writer):
    assert writer.write("a/b/index.html", "<p>hi</p>") is True
    target = writer.output_dir / "a" / "b" / "index.html"
    assert target.read_text(encoding="utf-8") == "<p>hi</p>"
    assert writer.written == ["a/b/index.html"]
    assert writer.outputs == {"a/b/index.html"}
    assert writer.exists("a/b/index.html")
    assert not writer.exists("a/b")
    assert not writer.exists("nope.html")


def test_write_skips_identical_content(writer):
    writer.write("page.html", "same")
    target = writer.output_dir / "page.html"
    old = target.stat().st_mtime_ns - 10_000_000_000
    os.utime(target, ns=(old, old))
    assert writer.write("page.html", "same") is False
    assert target.stat().st_mtime_ns == old
    assert writer.unchanged == ["page.html"]
    assert writer.write("page.html", "different") is True
    assert target.stat().st_mtime_ns != old
    assert writer.written == ["page.html", "page.html"]


def test_text_is_written_as_utf8_without_newline_translation(writer):
    writer.write("t.txt", "café\nline\r\nend")
    assert (writer.output_dir / "t.txt").read_bytes() == b"caf\xc3\xa9\nline\r\nend"
    writer.write("b.bin", b"\x00\x01\x02")
    assert (writer.output_dir / "b.bin").read_bytes() == b"\x00\x01\x02"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("a/b.html", "a/b.html"),
        ("a\\b.html", "a/b.html"),
        ("/a/b.html", "a/b.html"),
        ("./a/b.html", "a/b.html"),
        ("././a.html", "a.html"),
    ],
)
def test_output_paths_are_normalised(writer, given, expected):
    assert normalise_output_path(given) == expected
    writer.write(given, "x")
    assert writer.written == [expected]
    assert (writer.output_dir / expected).is_file()


@pytest.mark.parametrize(
    "path", ["../escape.html", "a/../../escape.html", "..\\escape.html", "", "/"]
)
def test_writing_outside_the_output_directory_is_refused(writer, path):
    with pytest.raises(BuildError):
        writer.write(path, "x")
    assert not (writer.output_dir.parent / "escape.html").exists()
    assert writer.written == []


def test_writing_over_a_directory_is_an_error(writer):
    writer.write("a/index.html", "x")
    with pytest.raises(BuildError, match="directory of that name is in the way"):
        writer.write("a", "x")


def test_copy_and_copy_again(writer, tmp_path):
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"jpeg")
    assert writer.copy(source, "img/photo.jpg") is True
    assert (writer.output_dir / "img/photo.jpg").read_bytes() == b"jpeg"
    assert writer.copy(source, "img/photo.jpg") is False
    assert writer.written == ["img/photo.jpg"]
    assert writer.unchanged == ["img/photo.jpg"]
    source.write_bytes(b"jpeg, edited")
    assert writer.copy(source, "img/photo.jpg") is True
    assert (writer.output_dir / "img/photo.jpg").read_bytes() == b"jpeg, edited"


def test_copy_of_a_missing_file_is_a_build_error(writer, tmp_path):
    with pytest.raises(BuildError, match="cannot copy"):
        writer.copy(tmp_path / "nope.jpg", "img/nope.jpg")


def test_keep_and_claim_mark_outputs_without_writing(writer):
    writer.keep("cached/index.html")
    writer.claim("css/main.css")
    assert writer.outputs == {"cached/index.html", "css/main.css"}
    assert writer.unchanged == ["cached/index.html"]
    assert writer.written == []
    assert not writer.output_dir.exists()


def test_remove_deletes_the_file_and_empty_parents(writer):
    writer.write("a/b/c/index.html", "x")
    writer.write("a/keep.html", "x")
    assert writer.remove("a/b/c/index.html") is True
    assert not (writer.output_dir / "a" / "b").exists()
    assert (writer.output_dir / "a" / "keep.html").is_file()
    assert writer.removed == ["a/b/c/index.html"]
    assert writer.remove("a/b/c/index.html") is False
    assert writer.remove("a") is False


def test_removing_the_last_file_leaves_the_output_directory_itself(writer):
    writer.write("only.html", "x")
    writer.remove("only.html")
    assert writer.output_dir.is_dir()
    assert list(writer.output_dir.iterdir()) == []


def test_remove_stale_only_touches_what_was_ours(writer):
    for name in ("old/index.html", "kept/index.html", "foreign.html"):
        (writer.output_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (writer.output_dir / name).write_text("x", encoding="utf-8")
    writer.keep("kept/index.html")
    previous = ["old/index.html", "kept/index.html", "never-existed.html"]
    gone = writer.remove_stale(previous)
    assert gone == ["old/index.html"]
    assert not (writer.output_dir / "old").exists()
    assert (writer.output_dir / "kept/index.html").is_file()
    assert (writer.output_dir / "foreign.html").is_file()


@pytest.mark.parametrize(
    "path", ["../outside.txt", "a/../../outside.txt", "..\\outside.txt"]
)
def test_stale_paths_are_never_followed_out_of_the_output_directory(writer, path):
    writer.output_dir.mkdir()
    outside = writer.output_dir.parent / "outside.txt"
    outside.write_text("precious", encoding="utf-8")
    assert writer.remove(path) is False
    assert writer.remove_stale([path]) == []
    assert outside.read_text(encoding="utf-8") == "precious"


def test_absolute_stale_path_stays_inside_the_output_directory(writer, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    writer.output_dir.mkdir()
    # leading slashes are dropped, so this names public/<...>/victim.txt
    assert writer.remove_stale([str(victim)]) == []
    assert victim.read_text(encoding="utf-8") == "precious"


def test_symlinks_out_of_the_output_directory_are_not_followed(writer, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.txt").write_text("precious", encoding="utf-8")
    writer.output_dir.mkdir()
    try:
        os.symlink(outside, writer.output_dir / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks here")
    assert writer.remove("link/file.txt") is False
    with pytest.raises(BuildError):
        writer.write("link/new.txt", "x")
    assert (outside / "file.txt").read_text(encoding="utf-8") == "precious"
    assert not (outside / "new.txt").exists()
