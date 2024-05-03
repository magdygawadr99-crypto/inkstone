from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any, Callable, Iterable

from . import nodes
from .errors import TemplateNotFound, TemplateRuntimeError
from .filters import FILTERS
from .interpreter import Interpreter
from .lexer import Token, tokenize
from .loaders import BaseLoader
from .parser import parse
from .runtime import (
    Context,
    Cycler,
    Joiner,
    Namespace,
    StrictUndefined,
    TemplateModule,
    Undefined,
    invoke,
)
from .tests_builtin import TESTS

_DEFAULT_GLOBALS: dict[str, Any] = {
    "range": range,
    "dict": dict,
    "namespace": Namespace,
    "cycler": Cycler,
    "joiner": Joiner,
}


def select_autoescape(
    extensions: Iterable[str] = ("html", "htm", "xml"),
    default: bool = False,
    default_for_string: bool = True,
) -> Callable[[str | None], bool]:
    """For Environment(autoescape=...): escape depending on the file name.

    Templates whose name ends in one of `extensions` are escaped, others get
    `default`, and templates made with from_string get `default_for_string`.
    """
    suffixes = tuple("." + ext.lstrip(".").lower() for ext in extensions)

    def autoescape(name: str | None) -> bool:
        if name is None:
            return default_for_string
        if name.lower().endswith(suffixes):
            return True
        return default

    return autoescape


def _unknown(kind: str, name: str, known: Iterable[str]) -> str:
    message = f"no {kind} named {name!r}"
    close = difflib.get_close_matches(str(name), list(known), n=1)
    if close:
        message += f", did you mean {close[0]!r}?"
    return message


def _static_names(expr: nodes.Expr | None) -> list[str]:
    """The template names that can be read straight off an expression."""
    if isinstance(expr, nodes.Const):
        return [expr.value] if isinstance(expr.value, str) else []
    if isinstance(expr, (nodes.ListLit, nodes.TupleLit)):
        return [name for item in expr.items for name in _static_names(item)]
    if isinstance(expr, nodes.CondExpr):
        return _static_names(expr.then) + _static_names(expr.orelse)
    return []


class Template:
    """A parsed template. Get one from Environment.get_template/from_string."""

    def __init__(
        self,
        env: Environment,
        root: nodes.Template,
        name: str | None = None,
        filename: str | None = None,
        uptodate: Callable[[], bool] | None = None,
    ):
        self.env = env
        self.root = root
        self.name = name
        self.filename = filename
        # what error messages call this template
        self.path = filename or name or "<string>"
        self.autoescape = env.autoescape_for(name)
        self.blocks = {block.name: block for block in root.find_all(nodes.Block)}
        self._uptodate = uptodate

        # TODO: names that are only known at render time, as in
        # {% include page.layout %}, are not in here. Recording what a render
        # actually loaded would catch those too.
        references = (nodes.Extends, nodes.Include, nodes.Import, nodes.FromImport)
        found: list[str] = []
        for node in root.find_all(references):
            for dependency in _static_names(node.template):
                if dependency not in found:
                    found.append(dependency)
        self.dependencies: tuple[str, ...] = tuple(found)

    def __repr__(self) -> str:
        return f"<Template {self.name or '<string>'!r}>"

    def render(self, context: Mapping[str, Any] | None = None, /, **kwargs: Any) -> str:
        """Render with the variables of `context` and/or keyword arguments."""
        variables = dict(context) if context else {}
        variables.update(kwargs)
        return self.env._interpreter.render(self, variables)

    def make_module(self, variables: Mapping[str, Any] | None = None) -> TemplateModule:
        """The template as `{% import %}` sees it, to call its macros from Python."""
        ctx = Context(self.env, self, [dict(variables or {})])
        return self.env._interpreter.make_module(self, ctx, True)

    @property
    def module(self) -> TemplateModule:
        return self.make_module()

    def is_up_to_date(self) -> bool:
        if self._uptodate is None:
            return True
        try:
            return self._uptodate()
        except OSError:
            return False

    def all_dependencies(self) -> set[str]:
        """`dependencies`, and theirs, and so on.

        Templates that don't exist stay in the result, they just can't be
        followed any further.
        """
        seen: set[str] = set()
        todo = list(self.dependencies)
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            try:
                todo.extend(self.env.get_template(name).dependencies)
            except TemplateNotFound:
                pass
        return seen


class Environment:
    """Configuration, loader and template cache in one place."""

    def __init__(
        self,
        loader: BaseLoader | None = None,
        *,
        autoescape: bool | Callable[[str | None], bool] = True,
        trim_blocks: bool = False,
        lstrip_blocks: bool = False,
        strict_undefined: bool = False,
        keep_trailing_newline: bool = False,
        auto_reload: bool = True,
    ):
        self.loader = loader
        self.autoescape = autoescape
        self.trim_blocks = trim_blocks
        self.lstrip_blocks = lstrip_blocks
        self.strict_undefined = strict_undefined
        self.keep_trailing_newline = keep_trailing_newline
        self.auto_reload = auto_reload
        self.undefined: type[Undefined] = (
            StrictUndefined if strict_undefined else Undefined
        )
        self.filters: dict[str, Callable] = dict(FILTERS)
        self.tests: dict[str, Callable] = dict(TESTS)
        self.globals: dict[str, Any] = dict(_DEFAULT_GLOBALS)
        self._cache: dict[str, Template] = {}
        self._interpreter = Interpreter(self)

    def autoescape_for(self, name: str | None) -> bool:
        if callable(self.autoescape):
            return bool(self.autoescape(name))
        return bool(self.autoescape)

    def _lexer_options(self) -> dict[str, bool]:
        return {
            "trim_blocks": self.trim_blocks,
            "lstrip_blocks": self.lstrip_blocks,
            "keep_trailing_newline": self.keep_trailing_newline,
        }

    def tokenize(self, source: str, name: str | None = None) -> list[Token]:
        return tokenize(source, name, **self._lexer_options())

    def parse(self, source: str, name: str | None = None) -> nodes.Template:
        return parse(source, name, **self._lexer_options())

    def from_string(self, source: str, name: str | None = None) -> Template:
        """A template straight from source; it is not cached."""
        root = parse(source, name or "<string>", **self._lexer_options())
        return Template(self, root, name)

    def get_template(self, name: str | Template) -> Template:
        """Load a template by name.

        Templates are parsed once and then served from the cache, until the
        loader says the source has changed.
        """
        if isinstance(name, Template):
            return name
        if not isinstance(name, str):
            raise TemplateRuntimeError(
                f"a template name has to be a string, not {type(name).__name__}"
            )
        cached = self._cache.get(name)
        if cached is not None:
            if not self.auto_reload or cached.is_up_to_date():
                return cached
        if self.loader is None:
            raise TemplateNotFound(
                name, f"can't load {name!r}, this environment has no loader"
            )
        source, filename, uptodate = self.loader.get_source(name)
        root = parse(source, filename or name, **self._lexer_options())
        template = Template(self, root, name, filename, uptodate)
        self._cache[name] = template
        return template

    def select_template(self, names: Iterable[str | Template]) -> Template:
        """The first of `names` that exists."""
        names = list(names)
        for name in names:
            try:
                return self.get_template(name)
            except TemplateNotFound:
                continue
        if not names:
            raise TemplateNotFound(None, "no template names to choose from")
        tried = ", ".join(repr(name) for name in names)
        raise TemplateNotFound(names[-1], f"none of the templates {tried} was found")

    def list_templates(self) -> list[str]:
        if self.loader is None:
            return []
        return sorted(self.loader.list_templates())

    def clear_cache(self) -> None:
        self._cache.clear()

    def private_attribute(self, name: str) -> Undefined:
        return self.undefined(
            hint=f"{name!r} is private, templates can't get at attributes that"
            " start with an underscore"
        )

    def getattr(self, obj: Any, name: str) -> Any:
        """`obj.name` the way templates see it: attribute first, then item."""
        if isinstance(obj, Undefined):
            return obj._lookup(name)
        if name[:1] == "_":
            # plain data with such keys is harmless, real attributes are not
            if isinstance(obj, Mapping) and name in obj:
                return obj[name]
            return self.private_attribute(name)
        try:
            return getattr(obj, name)
        except AttributeError:
            pass
        try:
            return obj[name]
        except (TypeError, LookupError, AttributeError):
            return self.undefined(obj=obj, name=name)

    def getitem(self, obj: Any, key: Any) -> Any:
        """`obj[key]` the way templates see it: item first, then attribute."""
        if isinstance(obj, Undefined):
            return obj._lookup(key)
        try:
            return obj[key]
        except (TypeError, LookupError, AttributeError):
            pass
        if isinstance(key, str) and key[:1] != "_":
            try:
                return getattr(obj, key)
            except AttributeError:
                pass
        return self.undefined(obj=obj, name=key)

    def _context(self, ctx: Context | None) -> Context:
        # filters and tests called from Python code have no render going on
        return ctx if ctx is not None else Context(self, None, [{}])

    def call_filter(
        self,
        name: str,
        value: Any,
        args: Iterable[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> Any:
        func = self.filters.get(name)
        if func is None:
            raise TemplateRuntimeError(_unknown("filter", name, self.filters))
        return invoke(func, self._context(ctx), (value, *args), kwargs or {})

    def call_test(
        self,
        name: str,
        value: Any,
        args: Iterable[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> bool:
        func = self.tests.get(name)
        if func is None:
            raise TemplateRuntimeError(_unknown("test", name, self.tests))
        return bool(invoke(func, self._context(ctx), (value, *args), kwargs or {}))
