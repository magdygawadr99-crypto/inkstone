from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from inkstone.errors import ContentError
from inkstone.utils import fs
from inkstone.utils.glob import GlobSet


def make_tree(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))


def listing(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )


def relative(paths, root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]


def age(path: Path, seconds: float) -> None:
    info = path.stat()
    os.utime(path, (info.st_atime, info.st_mtime - seconds))


def test_ensure_dir(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert fs.ensure_dir(target) == target
    assert target.is_dir()
    assert fs.ensure_dir(str(target)) == target
    (tmp_path / "file").write_text("x")
    with pytest.raises(FileExistsError):
        fs.ensure_dir(tmp_path / "file")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"plain ascii\n", "plain ascii\n"),
        ("héllo ✓\n".encode("utf-8"), "héllo ✓\n"),
        (b"\xef\xbb\xbfwith bom\n", "with bom\n"),
        (b"dos\r\nlines\r\n", "dos\nlines\n"),
        (b"old mac\rlines\r", "old mac\nlines\n"),
        (b"mixed\r\n\rendings\n", "mixed\n\nendings\n"),
        ("utf16 ✓\r\n".encode("utf-16"), "utf16 ✓\n"),
        (b"\xfe\xff" + "big endian".encode("utf-16-be"), "big endian"),
        (b"", ""),
    ],
)
def test_read_text(tmp_path, raw, expected):
    path = tmp_path / "file.txt"
    path.write_bytes(raw)
    assert fs.read_text(path) == expected


def test_read_text_can_keep_line_endings(tmp_path):
    path = tmp_path / "file.txt"
    path.write_bytes(b"\xef\xbb\xbfa\r\nb\r\n")
    assert fs.read_text(path, normalize_newlines=False) == "a\r\nb\r\n"
    assert fs.read_text(str(path)) == "a\nb\n"


def test_read_text_reports_where_the_bad_byte_is(tmp_path):
    path = tmp_path / "latin1.md"
    path.write_bytes(b"line one\nline two\ncaf\xe9 au lait\n")
    with pytest.raises(ContentError) as info:
        fs.read_text(path)
    error = info.value
    assert error.path == path
    assert error.line == 3
    assert "not valid UTF-8" in error.message
    assert "0xe9" in error.message and "offset 21" in error.message


def test_read_text_missing_file_is_a_plain_oserror(tmp_path):
    with pytest.raises(FileNotFoundError):
        fs.read_text(tmp_path / "nope.txt")


def test_atomic_write_text_and_bytes(tmp_path):
    target = tmp_path / "out" / "deep" / "page.html"
    fs.atomic_write(target, "<p>héllo</p>\n")
    assert target.read_bytes() == "<p>héllo</p>\n".encode("utf-8")
    fs.atomic_write(target, b"\x00\x01binary")
    assert target.read_bytes() == b"\x00\x01binary"
    fs.atomic_write(str(target), "latin é", encoding="latin-1")
    assert target.read_bytes() == b"latin \xe9"


def test_atomic_write_does_not_translate_newlines(tmp_path):
    target = tmp_path / "file.txt"
    fs.atomic_write(target, "a\nb\r\nc\n")
    assert target.read_bytes() == b"a\nb\r\nc\n"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "file.txt"
    for content in ("one", "two", "three"):
        fs.atomic_write(target, content)
    assert listing(tmp_path) == ["file.txt"]
    assert target.read_text() == "three"


def test_atomic_write_failure_keeps_the_old_file(tmp_path, monkeypatch):
    target = tmp_path / "file.txt"
    fs.atomic_write(target, "original")

    def explode(src, dst):
        raise OSError("disk on fire")

    monkeypatch.setattr(fs.os, "replace", explode)
    with pytest.raises(OSError, match="disk on fire"):
        fs.atomic_write(target, "replacement")
    monkeypatch.undo()
    assert target.read_text() == "original"
    assert listing(tmp_path) == ["file.txt"]


def test_atomic_write_retries_when_windows_has_the_file_locked(tmp_path, monkeypatch):
    target = tmp_path / "file.txt"
    real_replace = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) < 3:
            raise PermissionError("locked")
        real_replace(src, dst)

    monkeypatch.setattr(fs.os, "replace", flaky)
    monkeypatch.setattr(fs, "_WINDOWS", True)
    monkeypatch.setattr(fs.time, "sleep", lambda seconds: None)
    fs.atomic_write(target, "made it")
    assert len(calls) == 3
    assert target.read_text() == "made it"

    # elsewhere a permission error is not going to fix itself
    calls.clear()
    monkeypatch.setattr(fs, "_WINDOWS", False)
    with pytest.raises(PermissionError):
        fs.atomic_write(target, "no retry")
    monkeypatch.undo()
    assert len(calls) == 1
    assert listing(tmp_path) == ["file.txt"]


TREE = {
    "index.md": "home",
    "about.md": "about",
    "blog/first.md": "one",
    "blog/second.md": "two",
    "blog/img/photo.png": "png",
    "static/site.css": "css",
    ".hidden": "secret",
    ".git/config": "git",
    "blog/.draft.md": "draft",
    "build/out.html": "generated",
}


def test_walk_files_order_and_hidden_files(tmp_path):
    make_tree(tmp_path, TREE)
    assert relative(fs.walk_files(tmp_path), tmp_path) == [
        "about.md",
        "index.md",
        "blog/first.md",
        "blog/second.md",
        "blog/img/photo.png",
        "build/out.html",
        "static/site.css",
    ]
    everything = relative(fs.walk_files(tmp_path, include_hidden=True), tmp_path)
    assert sorted(everything) == sorted(TREE)


def test_walk_files_ignore_patterns(tmp_path):
    make_tree(tmp_path, TREE)
    found = fs.walk_files(tmp_path, ignore=["build/", "*.png", "/about.md"])
    assert relative(found, tmp_path) == [
        "index.md",
        "blog/first.md",
        "blog/second.md",
        "static/site.css",
    ]
    ready = GlobSet(["blog/"])
    assert relative(fs.walk_files(str(tmp_path), ignore=ready), tmp_path) == [
        "about.md",
        "index.md",
        "build/out.html",
        "static/site.css",
    ]


def test_walk_files_negated_pattern_reaches_into_ignored_directory(tmp_path):
    make_tree(tmp_path, TREE)
    found = fs.walk_files(tmp_path, ignore=["blog/", "!blog/second.md", "build/"])
    assert relative(found, tmp_path) == [
        "about.md",
        "index.md",
        "blog/second.md",
        "static/site.css",
    ]


def test_walk_files_on_missing_or_empty_directory(tmp_path):
    assert list(fs.walk_files(tmp_path / "missing")) == []
    assert list(fs.walk_files(tmp_path)) == []


def test_copy_tree_copies_everything_the_first_time(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    make_tree(src, {"a.txt": "a", "sub/b.txt": "b", ".nojekyll": "", "sub/.keep": ""})
    copied = fs.copy_tree(src, dst)
    assert sorted(relative(copied, dst)) == listing(src)
    assert listing(dst) == [".nojekyll", "a.txt", "sub/.keep", "sub/b.txt"]
    assert (dst / "sub" / "b.txt").read_text() == "b"


def test_copy_tree_skips_unchanged_files(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    make_tree(src, {"a.txt": "a", "b.txt": "b", "c.txt": "c"})
    fs.copy_tree(src, dst)
    assert fs.copy_tree(src, dst) == []

    (src / "a.txt").write_text("longer content")
    # same size, so only the modification time gives it away
    (src / "b.txt").write_text("B")
    age(src / "b.txt", 60)
    make_tree(src, {"new.txt": "n"})

    copied = fs.copy_tree(src, dst)
    assert sorted(relative(copied, dst)) == ["a.txt", "b.txt", "new.txt"]
    assert (dst / "a.txt").read_text() == "longer content"
    assert (dst / "b.txt").read_text() == "B"
    assert fs.copy_tree(src, dst) == []


def test_copy_tree_ignore_and_stale_files(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    make_tree(src, {"keep.css": "k", "skip.map": "s", "node_modules/x.js": "x"})
    make_tree(dst, {"stale.txt": "old"})
    copied = fs.copy_tree(src, dst, ignore=["*.map", "node_modules/"])
    assert relative(copied, dst) == ["keep.css"]
    assert listing(dst) == ["keep.css", "stale.txt"]


def test_copy_tree_overwrites_read_only_copies(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    make_tree(src, {"locked.txt": "v1"})
    os.chmod(src / "locked.txt", stat.S_IREAD)
    try:
        fs.copy_tree(src, dst)
        os.chmod(src / "locked.txt", stat.S_IREAD | stat.S_IWRITE)
        (src / "locked.txt").write_text("version two")
        os.chmod(src / "locked.txt", stat.S_IREAD)
        assert relative(fs.copy_tree(src, dst), dst) == ["locked.txt"]
        assert (dst / "locked.txt").read_text() == "version two"
    finally:
        for path in (src / "locked.txt", dst / "locked.txt"):
            if path.exists():
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


def test_sync_tree_removes_stale_files_and_empty_directories(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    make_tree(src, {"a.txt": "a", "sub/b.txt": "b"})
    make_tree(
        dst,
        {
            "a.txt": "old a!",
            "gone.txt": "x",
            "old/deep/c.txt": "c",
            "sub/d.txt": "d",
        },
    )
    copied, removed = fs.sync_tree(src, dst)
    assert sorted(relative(copied, dst)) == ["a.txt", "sub/b.txt"]
    assert sorted(relative(removed, dst)) == ["gone.txt", "old/deep/c.txt", "sub/d.txt"]
    assert listing(dst) == ["a.txt", "sub/b.txt"]
    assert not (dst / "old").exists()
    assert fs.sync_tree(src, dst) == ([], [])


def test_sync_tree_respects_ignore_on_both_sides(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    make_tree(src, {"a.txt": "a", "a.map": "m"})
    make_tree(dst, {"old.map": "m", ".stale": "s"})
    copied, removed = fs.sync_tree(src, dst, ignore=["*.map"])
    assert relative(copied, dst) == ["a.txt"]
    assert sorted(relative(removed, dst)) == [".stale", "old.map"]
    assert listing(dst) == ["a.txt"]


def test_sync_tree_into_missing_destination(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "does" / "not" / "exist"
    make_tree(src, {"a.txt": "a"})
    copied, removed = fs.sync_tree(src, dst)
    assert relative(copied, dst) == ["a.txt"] and removed == []


@pytest.mark.parametrize("algo", ["sha1", "sha256", "md5"])
def test_file_hash(tmp_path, algo):
    path = tmp_path / "blob.bin"
    data = bytes(range(256)) * 1000
    path.write_bytes(data)
    assert fs.file_hash(path, algo) == hashlib.new(algo, data).hexdigest()


def test_file_hash_default_and_errors(tmp_path):
    path = tmp_path / "empty"
    path.write_bytes(b"")
    assert fs.file_hash(path) == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    with pytest.raises(ValueError):
        fs.file_hash(path, "not-a-hash")
    with pytest.raises(FileNotFoundError):
        fs.file_hash(tmp_path / "missing")


def test_remove_tree(tmp_path):
    root = tmp_path / "site"
    make_tree(root, {"a.txt": "a", "sub/deep/b.txt": "b"})
    fs.remove_tree(root)
    assert not root.exists()
    fs.remove_tree(root)
    fs.remove_tree(str(tmp_path / "never-existed"))


def test_remove_tree_handles_read_only_files(tmp_path):
    root = tmp_path / "repo"
    make_tree(root, {"objects/pack/data.pack": "x", "objects/info": "y", "HEAD": "ref"})
    for path in root.rglob("*"):
        if path.is_file():
            os.chmod(path, stat.S_IREAD)
    fs.remove_tree(root)
    assert not root.exists()


def test_remove_tree_on_a_single_file(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("x")
    os.chmod(path, stat.S_IREAD)
    fs.remove_tree(path)
    assert not path.exists()


def test_tempdir_is_removed_afterwards():
    with fs.tempdir() as path:
        assert path.is_dir()
        assert path.name.startswith("inkstone-")
        (path / "sub").mkdir()
        (path / "sub" / "file.txt").write_text("x")
    assert not path.exists()


def test_tempdir_is_removed_on_error_and_takes_a_prefix():
    with pytest.raises(RuntimeError):
        with fs.tempdir(prefix="custom-") as path:
            assert path.name.startswith("custom-")
            raise RuntimeError("boom")
    assert not path.exists()
