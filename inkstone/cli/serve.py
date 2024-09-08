from __future__ import annotations

import argparse
import io

from ..errors import InkstoneError
from ..server import DEFAULT_IGNORE, DevServer
from ..utils import log
from .build import add_content_options, content_overrides


def _port(text: str) -> int:
    try:
        port = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a port number: {text!r}") from None
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("ports go from 0 to 65535")
    return port


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "serve",
        parents=[shared],
        help="build, serve and rebuild on changes",
        description=(
            "Build the site, serve it locally and rebuild when a source file "
            "changes. base_url is replaced by the address of the server."
        ),
    )
    parser.add_argument("--host", metavar="H", help="address to listen on")
    parser.add_argument("--port", metavar="N", type=_port, help="port to listen on")
    parser.add_argument(
        "--no-livereload", action="store_true", help="do not reload the browser"
    )
    parser.add_argument(
        "--open", action="store_true", help="open the site in a browser"
    )
    add_content_options(parser)
    parser.set_defaults(run=run)


def watch_paths(config) -> list:
    """Everything a change to which should cause a rebuild."""
    paths = [
        config.content_path,
        config.templates_path,
        config.static_path,
        config.data_path,
        config.themes_path,
        config.plugins_path,
    ]
    try:
        from ..build import theme_chain

        # built-in themes live inside the package, not below themes_dir
        paths += [theme.path for theme in theme_chain(config)]
    except InkstoneError:
        # a theme that does not exist; the build says so in a moment
        pass
    if config.path is not None:
        paths.append(config.path)
    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def server_settings(app, args):
    """The config as the site has it, read only for the [server] table.

    Loaded with the log switched off: the real load, with base_url replaced,
    comes right after and would repeat every warning about the file.
    """
    sink = io.StringIO()
    log.set_stream(sink)
    try:
        return app.config(content_overrides(args))
    finally:
        log.set_stream(None)


class Session:
    """One `inkstone serve`: a builder that is built again as files change."""

    def __init__(self, app, args):
        self.app = app
        self.args = args
        self.builder = None
        self.failed = False

    def configure(self, base_url: str) -> None:
        from ..build import Builder

        overrides = content_overrides(self.args)
        overrides["base_url"] = base_url
        self.builder = Builder(self.app.config(overrides))

    def first_build(self) -> None:
        """Build before serving; a broken site still gets a server."""
        try:
            report = self.builder.build()
        except InkstoneError as exc:
            # keep going: the fix is one save away, and the browser shows
            # the error once the server is up
            self.failed = True
            log.error("%s", exc)
        else:
            self.failed = False
            log.info(report.summary())

    def rebuild(self, changes):
        """Called by the dev server; what it returns decides what reloads."""
        report = self.builder.build(changed=changes)
        self.failed = False
        if report.files_removed:
            # something went away: no telling which pages linked to it
            return None
        return list(report.output_paths)


def run(app, args) -> int:
    session = Session(app, args)
    config = server_settings(app, args)
    server = DevServer(
        config.output_path,
        host=args.host or config.server.host,
        port=config.server.port if args.port is None else args.port,
        watch=watch_paths(config),
        ignore=[*DEFAULT_IGNORE, *config.ignore],
        rebuild=session.rebuild,
        livereload=bool(config.server.livereload) and not args.no_livereload,
        open_browser=bool(args.open or config.server.open),
        log=log.info,
    )
    url = server.url
    session.configure(url)
    session.first_build()
    try:
        server.start()
        if server.url != url:
            # the port was taken and the server moved to another one, so
            # every absolute URL we just wrote points at the wrong place
            url = server.url
            session.configure(url)
            session.first_build()
        if session.failed:
            # once more through the server, which shows the error in the browser
            server.request_rebuild()
        app.say(f"Serving on {url} (Ctrl-C to stop)")
        server.serve_forever()
    finally:
        server.stop()
    log.info("stopped")
    return 0
