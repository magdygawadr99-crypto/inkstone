from __future__ import annotations

import argparse
import functools
import http.server
import socketserver

from ..errors import InkstoneError
from ..server.watcher import Watcher
from ..utils import log
from .build import add_content_options, content_overrides


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # browsers hold on to the css otherwise
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        log.verbose(fmt, *args)


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
    if config.path is not None:
        paths.append(config.path)
    return [path for path in paths if path.exists()]


def run(app, args) -> int:
    from ..build import Builder

    config = app.config(content_overrides(args))
    host = args.host or config.server.host
    port = config.server.port if args.port is None else args.port
    url = f"http://{host}:{port}/"

    overrides = content_overrides(args)
    overrides["base_url"] = url
    builder = Builder(app.config(overrides))

    def rebuild(changes=None):
        try:
            report = builder.build(changed=changes)
        except InkstoneError as exc:
            # keep serving: the fix is one save away
            log.error("%s", exc)
        else:
            log.info(report.summary())

    rebuild()
    # TODO: tell the browser. For now it is save, alt-tab, F5.
    watcher = Watcher(
        watch_paths(config),
        ignore=config.ignore,
        exclude=[config.output_path, config.cache_path],
        callback=rebuild,
        debounce=0.3,
    )
    watcher.start()

    handler = functools.partial(_Handler, directory=str(config.output_path))
    httpd = _Server((host, port), handler)
    app.say(f"Serving on {url} (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        httpd.server_close()
    return 0
