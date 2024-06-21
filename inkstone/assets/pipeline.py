from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import css as _css
from . import fingerprint as _fp
from .bundle import Bundle
from .datauri import data_uri, guess_mime
from .errors import AssetError
from .html import minify_html
from .js import minify_js
from .manifest import Manifest, normalise

CACHE_NAME = ".inkstone-assets.json"
# bump when a change to the minifiers should invalidate existing caches
_CACHE_VERSION = 1

# Files that are looked up by a fixed, well-known name.
DEFAULT_NO_FINGERPRINT = (
    "*.html",
    "*.htm",
    "*.txt",
    "*.xml",
    "*.webmanifest",
    "favicon.ico",
    "CNAME",
    ".nojekyll",
    ".htaccess",
    "_headers",
    "_redirects",
    ".well-known/*",
    "sw.js",
    "service-worker.js",
)

_KINDS = {
    ".css": "css",
    ".js": "js",
    ".mjs": "js",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".webmanifest": "json",
}
# Files are built in stages so that anything a stylesheet or page points at
# already has its final name by the time the reference is rewritten.
_STAGES = {"css": 1, "html": 2}
_RECORD_FIELDS = {
    "primary": list,
    "inputs": dict,
    "refs": dict,
    "output": str,
    "hash": str,
    "size": int,
    "integrity": str,
    "source_size": int,
}


def _kind_of(path: str) -> str:
    return _KINDS.get(posixpath.splitext(path)[1].lower(), "")


def _matches(patterns: Iterable[str], path: str) -> bool:
    name = posixpath.basename(path)
    return any(
        fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(name, pattern)
        for pattern in patterns
    )


def _is_minified(path: str) -> bool:
    return ".min." in posixpath.basename(path)


def _human(size: int) -> str:
    if size < 1000:
        return f"{size} B"
    if size < 1000_000:
        return f"{size / 1000:.1f} kB"
    return f"{size / 1000_000:.1f} MB"


def _compact_json(data: bytes) -> bytes:
    try:
        value = json.loads(data.decode("utf-8-sig"))
        text = json.dumps(
            value, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (ValueError, RecursionError):
        # not JSON after all (comments, NaN...); ship it untouched
        return data
    return text.encode("utf-8")


@dataclass
class BuildReport:
    """What the last build did. Paths in `built` and `unchanged` are logical
    ones; `removed` lists output files that were deleted."""

    built: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    source_bytes: int = 0
    output_bytes: int = 0

    @property
    def total(self) -> int:
        return len(self.built) + len(self.unchanged)

    @property
    def saved(self) -> int:
        return self.source_bytes - self.output_bytes

    def summary(self) -> str:
        text = f"{self.total} assets: {len(self.built)} built"
        text += f", {len(self.unchanged)} unchanged"
        if self.removed:
            text += f", {len(self.removed)} removed"
        text += f"; {_human(self.source_bytes)} -> {_human(self.output_bytes)}"
        if self.source_bytes and self.saved > 0:
            text += f" ({100 * self.saved // self.source_bytes}% saved)"
        return text


@dataclass
class _Target:
    logical: str
    inputs: list[str]
    kind: str
    minify: bool
    bundle: Bundle | None = None


class _Lookups:
    """Stands in for the manifest while one file is being built and notes
    which assets that file asked about, found or not. Those are the things
    whose renaming means the file has to be built again."""

    def __init__(self, manifest: Manifest):
        self.manifest = manifest
        self.names: list[str] = []

    def get(self, logical: str):
        if logical not in self.names:
            self.names.append(logical)
        return self.manifest.get(logical)


class AssetPipeline:
    """Copies static files to the output directory, improving them on the way.

    `sources` are searched in order and later ones win, so a site can
    override a file shipped by its theme by putting one at the same relative
    path. CSS files whose name starts with an underscore are partials: they
    can be @imported or bundled but are not written out on their own.

    A small JSON cache in the output directory remembers what each output
    was built from; a rebuild only touches files whose inputs changed and
    deletes outputs that no longer have a source.
    """

    def __init__(
        self,
        sources,
        output_dir,
        *,
        minify: bool = True,
        fingerprint: bool = True,
        bundles: Iterable[Bundle] = (),
        ignore: Iterable[str] = (),
        inline_limit: int = 0,
        no_fingerprint: Iterable[str] | None = None,
        base_url: str = "/",
        cache_path=None,
    ):
        if isinstance(sources, (str, os.PathLike)):
            sources = [sources]
        self.sources = [Path(source) for source in sources]
        self.output_dir = Path(output_dir)
        self.minify = minify
        self.fingerprint = fingerprint
        self.bundles = list(bundles)
        self.ignore = list(ignore)
        self.inline_limit = int(inline_limit)
        if no_fingerprint is None:
            no_fingerprint = DEFAULT_NO_FINGERPRINT
        self.no_fingerprint = list(no_fingerprint)
        self.base_url = base_url
        if cache_path is None:
            cache_path = self.output_dir / CACHE_NAME
        self.cache_path = Path(cache_path)
        self.manifest: Manifest | None = None
        self.report = BuildReport()
        self._files: dict[str, Path] = {}
        self._digests: dict[str, str | None] = {}

        seen: set[str] = set()
        for bundle in self.bundles:
            if bundle.output in seen:
                raise AssetError("two bundles write to this path", path=bundle.output)
            seen.add(bundle.output)

    def scan(self) -> dict[str, Path]:
        """Find the source files: logical path -> file, overrides applied."""
        found: dict[str, Path] = {}
        output_root = self.output_dir.resolve()
        for root in self.sources:
            if not root.is_dir():
                # a theme without a static/ directory is perfectly normal
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                here = Path(dirpath)
                rel = here.relative_to(root).as_posix()
                rel = "" if rel == "." else rel
                dirnames[:] = sorted(
                    name
                    for name in dirnames
                    if not _matches(self.ignore, posixpath.join(rel, name))
                    and (here / name).resolve() != output_root
                )
                for name in sorted(filenames):
                    logical = posixpath.join(rel, name)
                    if name != CACHE_NAME and not _matches(self.ignore, logical):
                        found[logical] = here / name
        return found

    def build(self) -> Manifest:
        """Bring the output directory up to date and return the manifest."""
        self._files = self.scan()
        self._digests = {}
        previous, config_matches = self._load_cache()
        targets = self._targets()

        manifest = Manifest()
        report = BuildReport()
        records: dict[str, dict] = {}
        for target in targets:
            old = previous.get(target.logical) if config_matches else None
            if old is not None and self._fresh(old, target, manifest):
                record = old
                report.unchanged.append(target.logical)
            else:
                record = self._build(target, manifest)
                report.built.append(target.logical)
            records[target.logical] = record
            manifest.add(
                target.logical,
                record["output"],
                hash=record["hash"],
                size=record["size"],
                integrity=record["integrity"],
            )
            report.source_bytes += record["source_size"]
            report.output_bytes += record["size"]

        live = manifest.outputs()
        stale = {r["output"]: r for r in previous.values() if r["output"] not in live}
        for output in sorted(stale):
            if self._remove(stale[output]):
                report.removed.append(output)
        self._save_cache(records)
        self.manifest = manifest
        self.report = report
        return manifest

    def rewrite_html(
        self, html: str, *, page_path: str = "", integrity: bool = False
    ) -> str:
        """Replace asset references in a rendered page with the built names.

        `page_path` is where the page will live in the output directory
        (`blog/post/index.html`); it is only needed for pages that refer to
        assets with relative URLs.
        """
        if self.manifest is None:
            raise AssetError("assets have not been built yet; call build() first")
        return _fp.rewrite_html(
            html,
            self.manifest,
            page_path=normalise(page_path) if page_path else "",
            base_url=self.base_url,
            integrity=integrity,
        )

    def clean(self) -> list[str]:
        """Delete everything a previous build wrote, cache included."""
        previous, _ = self._load_cache()
        removed = [
            record["output"] for record in previous.values() if self._remove(record)
        ]
        try:
            self.cache_path.unlink()
        except OSError:
            pass
        self.manifest = None
        return sorted(removed)

    def _targets(self) -> list[_Target]:
        targets: list[_Target] = []
        consumed: set[str] = set()
        for bundle in self.bundles:
            inputs = bundle.expand(self._files)
            consumed.update(inputs)
            minify = self.minify if bundle.minify is None else bundle.minify
            targets.append(_Target(bundle.output, inputs, bundle.kind, minify, bundle))
        taken = {target.logical for target in targets}
        for logical in self._files:
            if logical in consumed or logical in taken:
                continue
            kind = _kind_of(logical)
            if kind == "css" and posixpath.basename(logical).startswith("_"):
                continue
            targets.append(_Target(logical, [logical], kind, self.minify))
        targets.sort(key=lambda t: (_STAGES.get(t.kind, 0), t.logical))
        return targets

    def _read(self, name: str) -> bytes:
        path = self._files[name]
        try:
            return path.read_bytes()
        except OSError as exc:
            raise AssetError(f"cannot read file: {exc.strerror}", path=path) from None

    def _read_text(self, name: str) -> str:
        try:
            return self._read(name).decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AssetError("not valid UTF-8", path=self._files[name]) from None

    def _digest(self, name: str) -> str | None:
        if name not in self._digests:
            known = name in self._files
            digest = hashlib.sha256(self._read(name)).hexdigest() if known else None
            self._digests[name] = digest
        return self._digests[name]

    def _ref_state(self, manifest: Manifest, name: str) -> str:
        """What a file that refers to `name` has baked into it: the name the
        asset was published under and, since small files get inlined, its
        contents."""
        entry = manifest.get(name)
        return f"{entry.output if entry else ''}:{self._digest(name) or ''}"

    def _fresh(self, old: dict, target: _Target, manifest: Manifest) -> bool:
        if old["primary"] != target.inputs:
            return False
        for name, digest in old["inputs"].items():
            if self._digest(name) != digest:
                return False
        for name, state in old["refs"].items():
            if self._ref_state(manifest, name) != state:
                return False
        try:
            return (self.output_dir / old["output"]).stat().st_size == old["size"]
        except OSError:
            # somebody emptied the output directory behind our back
            return False

    def _build(self, target: _Target, manifest: Manifest) -> dict:
        lookups = _Lookups(manifest)
        try:
            data, deps = self._render(target, lookups)
        except AssetError as exc:
            # the minifiers only know the logical name; point at the real file
            if exc.path is None:
                exc.path = self._files[target.inputs[0]]
            else:
                exc.path = self._files.get(str(exc.path), exc.path)
            raise
        digest = hashlib.sha256(data).hexdigest()
        output = target.logical
        if self.fingerprint and not _matches(self.no_fingerprint, output):
            output = _fp.insert_hash(output, digest[:8])
        dest = self.output_dir / output
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return {
            "primary": list(target.inputs),
            "inputs": {name: self._digest(name) for name in target.inputs + deps},
            "refs": {name: self._ref_state(manifest, name) for name in lookups.names},
            "output": output,
            "hash": digest,
            "size": len(data),
            "integrity": _fp.sri_hash(data),
            "source_size": sum(
                self._files[name].stat().st_size for name in target.inputs
            ),
        }

    def _render(self, target: _Target, lookups: _Lookups) -> tuple[bytes, list[str]]:
        deps: list[str] = []
        bundle = target.bundle
        if target.kind == "css":
            parts = [
                (name, self._css_part(name, target, deps)) for name in target.inputs
            ]
            text = bundle.concat(parts) if bundle else parts[0][1]
            text = self._link_css(text, target.logical, lookups)
            return text.encode("utf-8"), deps
        if target.kind == "js":
            if bundle is None and not self._should_minify(target, target.logical):
                return self._read(target.logical), deps
            parts = []
            for name in target.inputs:
                text = self._read_text(name)
                if self._should_minify(target, name):
                    text = minify_js(text, path=name)
                parts.append((name, text))
            text = bundle.concat(parts) if bundle else parts[0][1]
            return text.encode("utf-8"), deps
        if bundle is not None:
            # no idea what these are; glue the bytes together and hope
            return b"\n".join(self._read(name) for name in target.inputs), deps

        name = target.logical
        if target.kind == "html":
            text = self._read_text(name)
            if target.minify:
                text = minify_html(text, path=name)
            text = _fp.rewrite_html(
                text, lookups, page_path=name, base_url=self.base_url
            )
            return text.encode("utf-8"), deps
        data = self._read(name)
        if target.kind == "json" and target.minify:
            data = _compact_json(data)
        return data, deps

    def _should_minify(self, target: _Target, name: str) -> bool:
        return target.minify and not _is_minified(name)

    def _css_part(self, name: str, target: _Target, deps: list[str]) -> str:
        def load(wanted: str) -> str | None:
            return self._read_text(wanted) if wanted in self._files else None

        text = _css.inline_imports_from(name, load, deps=deps)
        # in a bundle the file may end up in a different directory
        here = posixpath.dirname(name)
        there = posixpath.dirname(target.logical)
        text = _css.rebase_urls(text, here, there, path=name)
        if self._should_minify(target, name):
            text = _css.minify_css(text, path=name)
        return text

    def _link_css(self, text: str, logical: str, lookups: _Lookups) -> str:
        """Resolve url() references: inline the small ones, fingerprint the rest."""
        where = {"from_path": logical, "base_url": self.base_url}

        def fix(url: str) -> str | None:
            if self.inline_limit and "#" not in url:
                found = _fp.resolve_ref(url, **where)
                name = found[0] if found else ""
                path = self._files.get(name)
                small = path is not None and path.stat().st_size < self.inline_limit
                if small and _kind_of(name) != "css":
                    lookups.get(name)
                    return data_uri(self._read(name), guess_mime(name))
            return _fp.map_ref(url, lookups, **where)

        return _css.rewrite_urls(text, fix, path=logical)

    def _remove(self, record: dict) -> bool:
        """Delete an output of an earlier build, if it is still that file."""
        dest = self.output_dir / record["output"]
        try:
            # The page generator shares this directory. A static 404.html
            # that became a rendered page must not be deleted as "stale".
            if hashlib.sha256(dest.read_bytes()).hexdigest() != record["hash"]:
                return False
            dest.unlink()
        except OSError:
            return False
        # tidy up directories this left empty, but never the root itself
        parent = dest.parent
        while parent != self.output_dir:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return True

    def _config_key(self) -> str:
        config = {
            "version": _CACHE_VERSION,
            "minify": self.minify,
            "fingerprint": self.fingerprint,
            "inline_limit": self.inline_limit,
            "base_url": self.base_url,
            "no_fingerprint": self.no_fingerprint,
            "bundles": [[b.output, b.inputs, b.minify] for b in self.bundles],
        }
        text = json.dumps(config, sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _load_cache(self) -> tuple[dict[str, dict], bool]:
        """Records from the last build, and whether they were made with the
        settings we have now. Records made with other settings still tell us
        which files are ours to delete."""
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            assets = data["assets"]
            matches = data["config"] == self._config_key()
        except (OSError, ValueError, KeyError, TypeError):
            return {}, False
        if not isinstance(assets, dict):
            return {}, False
        records = {
            logical: record
            for logical, record in assets.items()
            if _valid_record(record)
        }
        return records, matches

    def _save_cache(self, records: dict[str, dict]) -> None:
        data = {"config": self._config_key(), "assets": records}
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        scratch = self.cache_path.with_name(self.cache_path.name + ".tmp")
        scratch.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        os.replace(scratch, self.cache_path)


def _valid_record(record) -> bool:
    if not isinstance(record, dict):
        return False
    for name, kind in _RECORD_FIELDS.items():
        if not isinstance(record.get(name), kind):
            return False
    # the output path gets deleted when it goes stale, so be sure it cannot
    # point outside the output directory
    output = record["output"]
    return (
        output == normalise(output)
        and not output.startswith("..")
        and ":" not in output
    )
