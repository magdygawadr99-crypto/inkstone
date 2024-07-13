from __future__ import annotations

import concurrent.futures
import contextlib
import inspect
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from .. import __version__
from ..config import CONFIG_NAMES
from ..content import Page, load_site
from ..content import summary as summaries
from ..content.permalinks import check_collisions
from ..errors import BuildError, InkstoneError
from ..plugins import PluginManager
from ..tmpl import Environment, Markup, Template, TemplateError
from ..utils import log as default_log
from ..utils.fs import atomic_write, remove_tree
from ..utils.hashing import hash_text, stable_hash
from ..utils.timer import Profiler
from . import depgraph, generators, keys
from .cache import CACHE_VERSION, BuildCache
from .context import TemplateHelpers, page_context
from .markdown import MarkdownRenderer
from .report import BuildReport
from .templates import (
    THEME_FILE,
    TemplateFingerprints,
    Theme,
    make_environment,
    select_template,
    static_search_path,
    theme_chain,
)
from .writer import OutputWriter, normalise_output_path

GENERATED_DIR = "generated"
ASSET_CACHE = "assets.json"
# kinds a theme may leave out without it being an error
_OPTIONAL_KINDS = ("taxonomy", "term", "404")
# attributes a plugin may reasonably rewrite while a page renders
_MUTABLE_FIELDS = ("title", "description", "date", "updated", "weight")


def _is_html(path: str) -> bool:
    return path.lower().endswith((".html", ".htm"))


def _inside(path: Path, directory: Path) -> bool:
    return path == directory or directory in path.parents


class Builder:
    """Builds a site, and keeps enough state to build it again cheaply.

    `inkstone serve` holds on to one of these and calls build() after every
    change, so nothing here may assume it only runs once.
    """

    def __init__(
        self,
        config,
        *,
        drafts: bool | None = None,
        future: bool | None = None,
        incremental: bool | None = None,
        log=None,
    ):
        self.config = config
        self.log = log if log is not None else default_log
        self.site = None
        self.report = BuildReport()
        self.cache: BuildCache | None = None
        self.themes: list[Theme] = []
        self._drafts = drafts
        self._future = future
        self._incremental = incremental
        self._env: Environment | None = None
        self._plugins: PluginManager | None = None
        self._assets = None
        self._manifest = None
        self._markdown: MarkdownRenderer | None = None
        self._fingerprints: TemplateFingerprints | None = None
        self._helpers = TemplateHelpers(self)
        self._ready = False
        self._stamp: tuple = ()
        self._uses: dict[str, tuple[bool, bool]] = {}
        self._missing_kinds: set[str] = set()
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return f"<Builder {str(self.config.root)!r}>"

    @property
    def drafts(self) -> bool:
        return bool(self.config.build.drafts if self._drafts is None else self._drafts)

    @property
    def future(self) -> bool:
        return bool(self.config.build.future if self._future is None else self._future)

    @property
    def incremental(self) -> bool:
        if self._incremental is None:
            return bool(self.config.build.incremental)
        return bool(self._incremental)

    @property
    def env(self) -> Environment:
        self._setup()
        return self._env

    @property
    def plugins(self) -> PluginManager:
        self._setup()
        return self._plugins

    @property
    def assets(self):
        self._setup()
        return self._assets

    @property
    def jobs(self) -> int:
        """Worker threads for rendering. 0 in the config means "you decide"."""
        wanted = int(self.config.build.jobs)
        if wanted > 0:
            return wanted
        # With the GIL threads only add overhead to CPU-bound rendering, so
        # "auto" is one worker unless this is a free-threaded interpreter.
        gil_enabled = getattr(sys, "_is_gil_enabled", lambda: True)()
        return 1 if gil_enabled else min(os.cpu_count() or 1, 8)

    def warn(self, message: str) -> None:
        if message not in self.report.warnings:
            self.report.warnings.append(message)
            self.log.warning(message)

    def source_label(self, page) -> str:
        """How a page is named in error messages."""
        if page.source_path:
            prefix = str(self.config.content_dir).replace("\\", "/").strip("/")
            return f"{prefix}/{page.source_path}" if prefix else page.source_path
        return f"the generated {page.kind} page {page.url}"

    def _setup(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            config = self.config
            self.themes = theme_chain(config)
            self._env = make_environment(config, self.themes)
            self._helpers.install(self._env)
            self._env.globals["config"] = config
            self._fingerprints = TemplateFingerprints(self._env)
            self._markdown = MarkdownRenderer(config, url_for=self._helpers.url_for)
            self._markdown.site = self.site
            self._assets = self._make_pipeline()
            self._manifest = None
            plugins = PluginManager(config)
            plugins.load()
            self._plugins = plugins
            self._stamp = self._config_stamp()
            # before the hook runs: plugins reach for builder.env in setup()
            self._ready = True
            try:
                plugins.call("setup", self)
            except BaseException:
                # half set up is not set up; try again from scratch next time
                self._ready = False
                raise

    def _make_pipeline(self):
        from ..assets import AssetPipeline

        config = self.config
        sources = [config.cache_path / GENERATED_DIR]
        sources += static_search_path(config, self.themes)
        # the pipeline matches with fnmatch, which has no "!" or "dir/" forms
        ignore = [p.rstrip("/") for p in config.ignore if not p.startswith("!")]
        return AssetPipeline(
            sources,
            config.output_path,
            minify=bool(config.build.minify),
            fingerprint=bool(config.build.fingerprint),
            ignore=ignore,
            base_url=config.base_path,
            cache_path=config.cache_path / ASSET_CACHE,
        )

    def _config_stamp(self) -> tuple:
        """Changes when the config file or a theme.toml was edited."""
        paths = [self.config.path] if self.config.path else []
        paths += [theme.path / THEME_FILE for theme in self.themes]
        stamp = []
        for path in paths:
            try:
                info = os.stat(path)
                stamp.append((str(path), info.st_mtime_ns, info.st_size))
            except OSError:
                stamp.append((str(path), 0, 0))
        return tuple(stamp)

    def _note_changes(self, changed) -> None:
        """Reload what a batch of changed files makes stale before building."""
        if changed is None:
            paths: set[Path] = set()
        else:
            # the dev server's ChangeSet keeps its paths in an attribute
            changed = getattr(changed, "paths", changed)
            paths = {Path(path).resolve() for path in changed}
        if not self._ready:
            return
        config = self.config
        reload_config = self._config_stamp() != self._stamp
        if config.path is not None and config.path in paths:
            reload_config = True
        elif config.path is None:
            # a site that had no config file may just have got one
            reload_config = any(
                path.parent == config.root and path.name in CONFIG_NAMES
                for path in paths
            )
        if reload_config:
            self.log.verbose("configuration changed, loading it again")
            self.config = config.reload()
            self._ready = False
            return
        plugins_dir = config.plugins_path
        if any(plugins_dir == path or plugins_dir in path.parents for path in paths):
            self.log.verbose("a plugin changed, loading plugins again")
            self._ready = False

    def affected_outputs(self, changed: Iterable) -> set[str] | None:
        """Outputs the last build made from the given source files.

        Answered from the dependency graph of that build, so a file nobody
        has seen yet affects nothing. None means "could be anything": the
        config, a data file or a plugin is among the changes.
        """
        cache = self.cache or BuildCache.load(self.config.cache_path)
        config = self.config
        themes = self.themes or theme_chain(config)
        template_dirs = [config.templates_path]
        template_dirs += [theme.templates_path for theme in themes]
        nodes = []
        for path in getattr(changed, "paths", changed):
            path = Path(path).resolve()
            if path == config.path or path.name == THEME_FILE:
                return None
            if _inside(path, config.data_path) or _inside(path, config.plugins_path):
                return None
            if _inside(path, config.content_path):
                relative = path.relative_to(config.content_path).as_posix()
                nodes.append(depgraph.node(depgraph.SOURCE, relative))
                continue
            for directory in template_dirs:
                if _inside(path, directory):
                    name = path.relative_to(directory).as_posix()
                    nodes.append(depgraph.node(depgraph.TEMPLATE, name))
                    break
        return cache.graph.affected_outputs(nodes)

    def build(self, changed: Iterable | None = None) -> BuildReport:
        """Build the site and return what was done.

        ``changed`` is a hint from the dev server: the source paths that were
        touched since the last build. What actually gets rebuilt is decided
        from the cache either way.
        """
        with self._lock:
            return self._build(changed)

    def _build(self, changed) -> BuildReport:
        started = time.perf_counter()
        profiler = Profiler()
        report = self.report = BuildReport()
        self._helpers.reset()
        self._uses = {}
        self._missing_kinds = set()

        with profiler.phase("setup"):
            if changed is not None and self._ready:
                touched = self.affected_outputs(changed)
                self.log.verbose(
                    "the changed files reach %s",
                    "everything" if touched is None else f"{len(touched)} outputs",
                )
            self._note_changes(changed)
            self._setup()
            report.incremental = self.incremental
            for message in self.config.warnings:
                report.warn(message)
            self._fingerprints.reset()
            cache = self.cache = BuildCache.load(self.config.cache_path)
            if not self.incremental:
                cache.clear()
            elif cache.reset_reason and cache.previous_outputs:
                self.log.verbose("full rebuild: %s", cache.reset_reason)
            writer = OutputWriter(self.config.output_path)

        with profiler.phase("load"):
            site = self._load()
        with profiler.phase("markdown"):
            self._render_all_content()
        with profiler.phase("generate"):
            self._generate_pages()
        with profiler.phase("lists"):
            site.refresh()
            site.generate_list_pages()
            generators.not_found_page(site)
            check_collisions(site.all_pages)
        with profiler.phase("assets"):
            self._build_assets(writer, report)
        with profiler.phase("templates"):
            rendered = self._render_templates(writer, report)
        with profiler.phase("write"):
            self._write_pages(rendered, writer, report)
            self._copy_resources(writer, report)
        with profiler.phase("extras"):
            self._write_generated(writer, report)
            self._write_plugin_files(writer, report)
        with profiler.phase("cleanup"):
            stale = writer.remove_stale(cache.previous_outputs)
            report.removed_paths += stale
            report.files_removed = len(report.removed_paths)
            cache.retain(writer.outputs)
            cache.prune_renders()
            cache.save()

        report.output_paths = sorted(set(report.output_paths) | set(writer.written))
        report.phases = {name: seconds for name, seconds, _calls in profiler.phases()}
        report.duration = time.perf_counter() - started
        self.plugins.call("build_finished", site, report)
        report.duration = time.perf_counter() - started
        return report

    def clean(self) -> None:
        """Delete the output and cache directories."""
        with self._lock:
            remove_tree(self.config.output_path)
            remove_tree(self.config.cache_path)
            self.cache = None
            self._manifest = None

    def _load(self):
        site = load_site(self.config, drafts=self.drafts, future=self.future)
        self.site = site
        self._markdown.site = site
        self._env.globals.update(site=site, config=self.config, now=site.build_time)
        for message in site.warnings:
            self.report.warn(message)
        self.plugins.call("content_loaded", site)
        # plugins may have added pages or changed dates and tags
        site.refresh()
        return site

    def _map(self, func: Callable, items: list) -> list:
        """Apply func to every item, on a few threads when that is allowed."""
        jobs = min(self.jobs, len(items))
        if jobs <= 1:
            return [func(item) for item in items]
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            # list() re-raises the first failure, in item order
            return list(pool.map(func, items))

    def markdown_for(self, page=None):
        """The configured Markdown converter (one per thread)."""
        self._setup()
        return self._markdown.converter()

    def render_markdown(self, text: str, page=None) -> Markup:
        """Markdown to HTML with the site's settings, for plugins and filters."""
        self._setup()
        return Markup(self._markdown.render(text, page).html)

    def _render_all_content(self) -> None:
        pending = [page for page in self.site.all_pages if not page._rendered]
        if not pending:
            return
        environment = stable_hash(
            [__version__, CACHE_VERSION, self._config_key(), self._plugin_key()]
        )
        self._map(lambda page: self._render_content(page, environment), pending)

    def _render_key(self, page, environment: str) -> str:
        resources = []
        for resource in page.resources:
            try:
                info = os.stat(resource.path)
                resources.append([resource.name, info.st_size, info.st_mtime_ns])
            except (OSError, TypeError):
                resources.append([resource.name, 0, 0])
        return stable_hash(
            [
                environment,
                page.source_path,
                page.url,
                hash_text(page.raw),
                keys.describe(page.meta, 1, refs_only=True),
                self._markdown.link_signature(page),
                resources,
            ]
        )

    def _render_content(self, page, environment: str) -> None:
        if not page.source_path:
            # a page some plugin built by hand with Markdown in page.raw
            self._render_page_content(page)
            return
        key = self._render_key(page, environment)
        if self.incremental:
            fields = self.cache.get_render(page.source_path, key)
            if fields is not None and self._restore(page, fields):
                return
        before = set(vars(page))
        originals = {name: getattr(page, name) for name in _MUTABLE_FIELDS}
        self._render_page_content(page)
        fields = {
            "content": page.content,
            "summary": page.summary,
            "truncated": page.truncated,
            "toc": page.toc,
            "toc_html": page.toc_html,
            "word_count": page._word_count,
            "reading_time": page._reading_time,
            # whatever plugins attached to the page while it rendered
            "extras": {
                name: value
                for name, value in vars(page).items()
                if name not in before and not name.startswith("_")
            },
            "changed": {
                name: getattr(page, name)
                for name in _MUTABLE_FIELDS
                if getattr(page, name) != originals[name]
            },
        }
        if not self.cache.put_render(page.source_path, key, fields):
            self.log.debug(
                "%s: not cached, a plugin attached something that is not plain data",
                self.source_label(page),
            )

    @staticmethod
    def _restore(page, fields: dict) -> bool:
        try:
            page.content = Markup(fields["content"])
            page.summary = Markup(fields["summary"])
            page.truncated = bool(fields["truncated"])
            page.toc = fields["toc"]
            page.toc_html = Markup(fields["toc_html"])
            page._word_count = fields["word_count"]
            page._reading_time = fields["reading_time"]
            for name, value in fields["extras"].items():
                setattr(page, name, value)
            for name, value in fields["changed"].items():
                if name in _MUTABLE_FIELDS:
                    setattr(page, name, value)
        except (KeyError, TypeError, AttributeError):
            return False
        page._rendered = True
        return True

    def _render_page_content(self, page) -> None:
        label = self.source_label(page)
        try:
            text = self.plugins.pipe("page_markdown", page.raw, page)
            rendered = self._markdown.render(text, page)
            page.toc = rendered.toc
            page.toc_html = Markup(rendered.toc_html)
            # visible to page_html hooks that look at the page, not the argument
            page.content = Markup(rendered.html)
            html = str(self.plugins.pipe("page_html", rendered.html, page))
            explicit = page.meta.get("summary")
            if isinstance(explicit, str) and explicit.strip():
                explicit = self._markdown.render(explicit).html
            else:
                explicit = None
            summary, html = summaries.make_summary(html, explicit=explicit)
            page.content = Markup(html)
            page.summary = Markup(summary.html)
            page.truncated = summary.truncated
            page._rendered = True
        except InkstoneError as exc:
            # name the file the reader has to open, whoever raised it
            if exc.path is None or exc.path == page.source_path:
                exc.path = label
            raise
        except Exception as exc:
            raise BuildError(
                f"cannot render the page: {type(exc).__name__}: {exc}", path=label
            ) from exc

    def _generate_pages(self) -> None:
        site = self.site
        for page in self.plugins.collect("generate_pages", site):
            if not isinstance(page, Page):
                raise BuildError(
                    f"a plugin's generate_pages() returned {page!r}; it has to "
                    "return Page objects (Page.virtual(...))"
                )
            site.add_page(page)

    @property
    def assets_built(self) -> bool:
        return self._manifest is not None

    def asset_output(self, logical: str) -> str | None:
        """Output path of a static file, None when there is no such file."""
        if self._manifest is None:
            return None
        entry = self._manifest.get(logical)
        return entry.output if entry is not None else None

    def asset_integrity(self, logical: str) -> str | None:
        if self._manifest is None:
            return None
        entry = self._manifest.get(logical)
        return entry.integrity if entry is not None else None

    def _build_assets(self, writer: OutputWriter, report: BuildReport) -> None:
        self._write_generated_assets()
        pipeline = self._assets
        manifest = self._manifest = pipeline.build()
        result = pipeline.report
        report.assets_copied = len(result.built)
        for logical in result.built:
            entry = manifest.get(logical)
            if entry is not None:
                report.output_paths.append(entry.output)
        report.removed_paths += list(result.removed)
        for output in manifest.outputs():
            writer.claim(output)

    def _write_generated_assets(self) -> None:
        """Put highlight.css and the search client where the pipeline finds them."""
        directory = self.config.cache_path / GENERATED_DIR
        wanted = generators.generated_assets(self.config)
        for logical, text in wanted.items():
            target = directory / logical
            data = text.encode("utf-8")
            try:
                current = target.read_bytes()
            except OSError:
                current = None
            if current != data:
                atomic_write(target, data)
        if not directory.is_dir():
            return
        for path in list(directory.rglob("*")):
            leftover = path.relative_to(directory).as_posix() not in wanted
            if leftover and path.is_file():
                with contextlib.suppress(OSError):
                    path.unlink()

    def _config_key(self) -> str:
        tree = self.config.to_dict()
        # the dev server's port has no business invalidating pages
        tree.pop("server", None)
        return stable_hash(keys.describe(tree))

    def _plugin_key(self) -> list:
        signature = []
        for plugin in self.plugins:
            entry: list[Any] = [plugin.name, getattr(plugin, "priority", 100)]
            try:
                info = os.stat(inspect.getfile(type(plugin)))
                entry += [info.st_size, info.st_mtime_ns]
            except (OSError, TypeError):
                pass
            signature.append(entry)
        return signature

    def _global_key(self) -> str:
        """Hash of everything that every page depends on."""
        site = self.site
        return stable_hash(
            {
                "inkstone": __version__,
                "cache": CACHE_VERSION,
                "config": self._config_key(),
                "drafts": self.drafts,
                "future": self.future,
                "themes": [[t.name, keys.describe(t.meta)] for t in self.themes],
                "plugins": self._plugin_key(),
                "data": keys.describe(site.data.to_dict()),
                "outline": keys.site_outline(site),
                # {{ now.year }} in a footer is the one use of the build time
                # that is worth keeping right
                "year": site.build_time.year,
            }
        )

    def _template_uses(self, name: str) -> tuple[bool, bool]:
        """Does a template (or anything it pulls in) look at the whole site?"""
        try:
            return self._uses[name]
        except KeyError:
            pass
        loader = self._env.loader
        uses_pages = uses_taxonomies = False
        for dependency in self._fingerprints.dependencies(name):
            try:
                source = loader.get_source(dependency)[0]
            except TemplateError:
                continue
            pages, taxonomies = keys.template_uses(source)
            uses_pages = uses_pages or pages
            uses_taxonomies = uses_taxonomies or taxonomies
        self._uses[name] = (uses_pages, uses_taxonomies)
        return self._uses[name]

    def _template_for(self, page) -> Template | None:
        try:
            return select_template(self._env, page)
        except BuildError:
            if page.kind not in _OPTIONAL_KINDS or page.template:
                raise
        if page.kind not in self._missing_kinds:
            self._missing_kinds.add(page.kind)
            self.log.verbose(
                "the theme has no template for %s pages, leaving them out", page.kind
            )
        return None

    def _dependencies(self, page, template_names: list[str]) -> list[str]:
        deps = [depgraph.node(depgraph.TEMPLATE, name) for name in template_names]
        deps.append(depgraph.CONFIG)
        if page.source_path:
            deps.append(depgraph.node(depgraph.SOURCE, page.source_path))
        first = getattr(page, "first_page", None)
        if first is not None and first.source_path:
            deps.append(depgraph.node(depgraph.SOURCE, first.source_path))
        paginator = page.extra_context.get("paginator")
        for member in getattr(paginator, "items", ()):
            if getattr(member, "source_path", None):
                deps.append(depgraph.node(depgraph.SOURCE, member.source_path))
        return deps

    def _assets_current(self, entry: dict) -> bool:
        """Do the asset URLs baked into a cached page still hold?"""
        for ref, answer in (entry.get("assets") or {}).items():
            kind, _, logical = ref.partition(":")
            if kind == "asset":
                output = self.asset_output(logical) or logical
                current = self._helpers.url_for("/" + output)
            else:
                current = self.asset_integrity(logical) or ""
            if current != answer:
                return False
        return True

    def _render_templates(self, writer: OutputWriter, report: BuildReport) -> list:
        site = self.site
        cache = self.cache
        keys.freeze_metadata(site.all_pages)
        global_key = self._global_key()
        shared: dict[str, str] = {}

        def pages_key() -> str:
            if "pages" not in shared:
                shared["pages"] = keys.site_pages_key(site)
            return shared["pages"]

        def taxonomies_key() -> str:
            if "taxonomies" not in shared:
                shared["taxonomies"] = keys.taxonomies_key(site)
            return shared["taxonomies"]

        jobs = []
        for page in list(site.all_pages):
            output = page.output_path
            if page.kind == "virtual" and page.template is None:
                jobs.append((page, None, stable_hash(["raw", str(page.content)]), []))
                continue
            template = self._template_for(page)
            if template is None:
                site.remove_page(page)
                continue
            page.layout = template.name
            names = self._fingerprints.dependencies(template.name)
            uses_pages, uses_taxonomies = self._template_uses(template.name)
            parts = [
                "page",
                global_key,
                template.name,
                self._fingerprints.fingerprint(template.name),
                keys.page_state(page),
            ]
            if uses_pages:
                parts.append(pages_key())
            if uses_taxonomies or page.kind == "taxonomy":
                parts.append(taxonomies_key())
            key = stable_hash(parts)
            entry = cache.entry(output) if self.incremental else None
            if (
                entry is not None
                and entry["key"] == key
                and writer.exists(output)
                and self._assets_current(entry)
            ):
                writer.keep(output)
                report.pages_skipped += 1
                continue
            jobs.append((page, template, key, self._dependencies(page, names)))

        results = self._map(self._render_page, jobs)
        return list(zip(jobs, results))

    def _render_page(self, job) -> tuple[str, dict]:
        page, template, _key, _deps = job
        if template is None:
            # a virtual page without a template: the content is the file
            return str(page.content), {}
        label = self.source_label(page)
        tracker = self._helpers.tracker
        tracker.start()
        try:
            context = page_context(self, page)
            # XXX whatever a hook adds here is in no cache key: a plugin that
            # injects site-wide numbers shows old ones on pages that are skipped
            self.plugins.call("template_context", page, context)
            html = template.render(context)
            html = str(self.plugins.pipe("page_output", html, page))
            if self.config.build.minify and _is_html(page.output_path):
                from ..assets import minify_html

                html = minify_html(html, path=page.output_path)
        except TemplateError as exc:
            raise BuildError(
                f"{exc.message} (while rendering {label})", path=exc.path, line=exc.line
            ) from exc
        except InkstoneError as exc:
            if exc.path is None or exc.path == page.source_path:
                exc.path = label
            raise
        except Exception as exc:
            raise BuildError(
                f"cannot render the page: {type(exc).__name__}: {exc}", path=label
            ) from exc
        finally:
            assets = tracker.finish()
        return html, assets

    def _write_pages(self, rendered: list, writer: OutputWriter, report) -> None:
        cache = self.cache
        static = self._manifest.outputs() if self._manifest is not None else set()
        for (page, template, key, deps), (html, assets) in rendered:
            output = page.output_path
            if output in static:
                self.warn(
                    f"{self.source_label(page)} is written to {output}, replacing "
                    "the static file of that name"
                )
            wrote = writer.write(output, html)
            cache.record(output, key, kind="page", deps=deps, assets=assets)
            if template is not None:
                report.pages_rendered += 1
            if wrote:
                report.pages_written += 1
            else:
                report.pages_skipped += 1

    def _copy_resources(self, writer: OutputWriter, report) -> None:
        """Files next to a bundle's index.md, and loose files in sections."""
        resources = list(self.site.resources)
        for page in self.site.all_pages:
            resources += page.resources
        for resource in resources:
            if resource.path is None:
                continue
            if writer.copy(resource.path, resource.output_path):
                report.files_written += 1
            source = depgraph.node(depgraph.SOURCE, resource.source_path)
            self.cache.record(resource.output_path, "", kind="resource", deps=[source])

    def _static_wins(self, output: str) -> bool:
        if self._manifest is None or output not in self._manifest.outputs():
            return False
        self.warn(
            f"{output} exists in static/, so the generated one is not written "
            "(turn the generator off in the config to silence this)"
        )
        return True

    def _write_generated(self, writer: OutputWriter, report) -> None:
        site = self.site
        cache = self.cache
        files: dict[str, str] = {}
        files.update(generators.build_feeds(site))
        files.update(generators.build_sitemap(site))
        files.update(generators.build_robots(site))
        # feeds and the sitemap are made from all pages; not worth being
        # more exact about which page ends up in which feed
        sources = [depgraph.CONFIG]
        sources += [
            depgraph.node(depgraph.SOURCE, page.source_path)
            for page in site.pages
            if page.source_path
        ]
        for output, text in files.items():
            if self._static_wins(output):
                continue
            if writer.write(output, text):
                report.files_written += 1
            deps = [depgraph.CONFIG] if output == generators.ROBOTS else sources
            cache.record(output, hash_text(text), kind="file", deps=deps)

    def _write_plugin_files(self, writer: OutputWriter, report) -> None:
        for item in self.plugins.collect("extra_files", self.site):
            try:
                output, data = item
            except (TypeError, ValueError):
                output, data = None, None
            if not isinstance(output, str) or not isinstance(data, (str, bytes)):
                raise BuildError(
                    f"a plugin's extra_files() gave {item!r}; expected "
                    "(output_path, text_or_bytes) pairs"
                )
            if writer.write(output, data):
                report.files_written += 1
            digest = hash_text(data) if isinstance(data, str) else stable_hash(data)
            self.cache.record(normalise_output_path(output), digest, kind="extra")
