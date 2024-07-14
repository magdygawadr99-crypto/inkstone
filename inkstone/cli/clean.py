from __future__ import annotations


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "clean",
        parents=[shared],
        help="remove the output and cache directories",
        description="Delete what a build wrote: the output directory and the cache.",
    )
    parser.set_defaults(run=run)


def run(app, args) -> int:
    from ..build import Builder

    config = app.config()
    doomed = [path for path in (config.output_path, config.cache_path) if path.exists()]
    Builder(config).clean()
    if doomed:
        app.say("removed " + ", ".join(app.shown(path) for path in doomed))
    else:
        app.say("nothing to clean")
    return 0
