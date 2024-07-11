from __future__ import annotations

# in the order a build calls them
hook_names = (
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

# hooks whose return value is fed to the next plugin
PIPE_HOOKS = frozenset({"page_markdown", "page_html", "page_output"})
# hooks whose return values are gathered into one list
COLLECT_HOOKS = frozenset({"generate_pages", "extra_files"})


class Plugin:
    """Base class for plugins: override the hooks you need.

    Hooks run in the order plugins are listed in the config; `priority`
    (lower runs earlier) overrides that when a plugin has to go first or last.
    """

    name = ""
    priority = 100

    def __init__(self, config, settings=None):
        self.config = config
        self.settings = dict(settings) if settings else {}

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r}>"

    def setup(self, builder) -> None:
        pass

    def content_loaded(self, site) -> None:
        pass

    def page_markdown(self, page, text):
        return text

    def page_html(self, page, html):
        return html

    def generate_pages(self, site):
        return ()

    def template_context(self, page, context) -> None:
        pass

    def page_output(self, page, html):
        return html

    def extra_files(self, site):
        return ()

    def build_finished(self, site, report) -> None:
        pass
