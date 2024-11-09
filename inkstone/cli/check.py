from __future__ import annotations

from ..errors import InkstoneError
from ..utils import log, term
from ..utils.text import pluralize

# Problems that are worth knowing about but do not mean the site is broken.
# Everything else fails the check; these only do with --strict.
WARNING_KINDS = frozenset(
    {"missing-anchor", "external-link", "missing-title", "orphan-alias"}
)


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "check",
        parents=[shared],
        help="look for broken links and front matter problems",
        description=(
            "Build the site and report broken internal links, missing images, "
            "front matter problems and pages that share a URL."
        ),
    )
    parser.add_argument(
        "--external",
        action="store_true",
        help="also request every link to other sites (slow)",
    )
    parser.add_argument(
        "--strict", action="store_true", help="exit non-zero for warnings too"
    )
    parser.set_defaults(run=run)


def is_warning(problem) -> bool:
    severity = getattr(problem, "severity", None)
    if severity is not None:
        return str(severity).lower().startswith("warn")
    return problem.kind in WARNING_KINDS


def describe(problem) -> str:
    """One line for a problem, the kind coloured by how bad it is."""
    text = str(problem)
    colour = "yellow" if is_warning(problem) else "red"
    kind = f": {problem.kind}: "
    if kind in text:
        before, _, after = text.partition(kind)
        return f"{before}: {term.style(problem.kind, colour)}: {after}"
    return text


def _below(config, directory, problems: list) -> list:
    """Name sources from the site root, so the paths can be opened as printed.

    The validator talks about files in the content directory and the link
    checker about files in the output; without the directory in front the
    two are easy to mix up.
    """
    try:
        prefix = directory.relative_to(config.root).as_posix()
    except ValueError:
        prefix = directory.as_posix()
    for problem in problems:
        source = problem.source
        # "generated taxonomy page" and the like are not files
        if source and not source.startswith("generated "):
            problem.source = f"{prefix}/{source}"
    return problems


def source_problems(config) -> list:
    """What can be seen without building: front matter, dates, clashing URLs."""
    from ..content import load_site, validate_site

    # lenient: a file that cannot be read becomes a problem in the list
    # instead of ending the check at the first one
    site = load_site(config, strict=False)
    return _below(config, config.content_path, validate_site(site))


def run(app, args) -> int:
    from ..build import Builder, LinkChecker

    config = app.config()
    problems = source_problems(config)

    build_error = None
    build_warnings = 0
    checked = None
    try:
        report = Builder(config).build()
    except InkstoneError as exc:
        # no output to look at, but what was found so far is still worth
        # printing; it is likely to be the reason
        build_error = exc
    else:
        build_warnings = len(report.warnings)
        checker = LinkChecker(
            config.output_path, base_url=config.base_url, external=args.external
        )
        problems += _below(config, config.output_path, checker.run())
        checked = getattr(checker, "checked", None)

    for problem in problems:
        app.out(describe(problem))
    if build_error is not None:
        log.error("the site does not build: %s", build_error)

    warnings = sum(1 for problem in problems if is_warning(problem))
    errors = len(problems) - warnings
    warnings += build_warnings
    if build_error is not None:
        errors += 1
    if not errors and not warnings:
        links = f" ({pluralize(checked, 'link')} checked)" if checked else ""
        app.say(f"no problems found{links}")
        return 0
    app.say(f"{pluralize(errors, 'error')}, {pluralize(warnings, 'warning')}")
    return 1 if errors or args.strict else 0
