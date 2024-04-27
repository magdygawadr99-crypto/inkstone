from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Iterator

from .errors import TemplateRuntimeError, UndefinedError
from .markup import Markup

if TYPE_CHECKING:
    from .environment import Environment, Template

missing: Any = object()


def pass_context(func):
    """Mark a filter, test or global so it gets the active Context first."""
    func._tmpl_pass = "context"
    return func


def pass_environment(func):
    """Mark a filter, test or global so it gets the Environment first."""
    func._tmpl_pass = "environment"
    return func


def invoke(func: Callable, ctx: Context, args, kwargs) -> Any:
    mode = getattr(func, "_tmpl_pass", None)
    if mode == "context":
        return func(ctx, *args, **kwargs)
    if mode == "environment":
        return func(ctx.env, *args, **kwargs)
    return func(*args, **kwargs)


def type_name(obj: Any) -> str:
    if obj is None:
        return "none"
    return f"{type(obj).__name__!r} object"


class Undefined:
    """What a missing variable, attribute or item evaluates to.

    It prints as nothing, is false, has no items, and looking things up on it
    just gives the same Undefined again, so `page.author.name` is fine when
    there is no author. Arithmetic and calls are errors, though: there is no
    sensible answer and it is nearly always a typo.
    """

    __slots__ = ("_hint", "_obj", "_name")

    def __init__(self, hint: str | None = None, obj: Any = missing, name: Any = None):
        self._hint = hint
        self._obj = obj
        self._name = name

    @property
    def _message(self) -> str:
        if self._hint:
            return self._hint
        if self._obj is missing:
            return f"{self._name!r} is undefined"
        kind = "attribute" if isinstance(self._name, str) else "element"
        return f"{type_name(self._obj)} has no {kind} {self._name!r}"

    def _fail(self, *args, **kwargs):
        raise UndefinedError(self._message)

    def _lookup(self, name: Any) -> Undefined:
        return self

    def __getattr__(self, name: str):
        # nothing private or magic here; this also keeps hasattr() checks
        # for things like __html__ honest
        if name[:1] == "_":
            raise AttributeError(name)
        return self._lookup(name)

    def __getitem__(self, key: Any):
        return self._lookup(key)

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return "Undefined"

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __iter__(self) -> Iterator[Any]:
        return iter(())

    def __contains__(self, item: Any) -> bool:
        return False

    def __eq__(self, other: Any) -> bool:
        return type(self) is type(other)

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return id(type(self))

    __call__ = _fail
    __add__ = __radd__ = __sub__ = __rsub__ = _fail
    __mul__ = __rmul__ = __truediv__ = __rtruediv__ = _fail
    __floordiv__ = __rfloordiv__ = __mod__ = __rmod__ = _fail
    __pow__ = __rpow__ = __neg__ = __pos__ = __abs__ = _fail
    __lt__ = __le__ = __gt__ = __ge__ = _fail


class StrictUndefined(Undefined):
    """Undefined that refuses to be used at all.

    Only `is defined` and the `default` filter get away with touching it.
    """

    __slots__ = ()

    _fail = Undefined._fail

    def _lookup(self, name: Any):
        self._fail()

    __str__ = __bool__ = __len__ = __iter__ = __contains__ = _fail
    __eq__ = __ne__ = __hash__ = __int__ = __float__ = __index__ = _fail


class RenderState:
    """Bookkeeping shared by every Context of one top-level render."""

    __slots__ = ("includes", "imports")

    def __init__(self):
        self.includes: list[str] = []
        self.imports: list[Template] = []


class Context:
    """The variables a piece of template sees, innermost scope last.

    Filters and functions marked with pass_context get one of these; for them
    the interesting parts are get()/resolve(), `env` and `autoescape`.
    """

    def __init__(
        self,
        env: Environment,
        template: Template | None,
        scopes: list[dict[str, Any]],
        state: RenderState | None = None,
        autoescape: bool | None = None,
    ):
        self.env = env
        # the template whose nodes are running right now; with inheritance
        # that changes while the context stays the same
        self.template = template
        self.scopes = scopes
        self.state = state if state is not None else RenderState()
        if autoescape is None:
            if template is not None:
                autoescape = template.autoescape
            else:
                autoescape = env.autoescape_for(None)
        self.autoescape = autoescape
        # block name -> [(node, template)], most derived first
        self.blocks: dict[str, list] = {}
        self.lineage: list[Template] = []
        # (parent template, output length at the extends tag) once the
        # template that is running has hit its {% extends %}
        self.parent: tuple[Template, int] | None = None
        self.exported: set[str] = set()

    @property
    def name(self) -> str | None:
        return self.template.name if self.template is not None else None

    def derive(self, scopes: list[dict[str, Any]], template=None) -> Context:
        """A context for the same render with its own stack of scopes."""
        ctx = Context(
            self.env, template or self.template, scopes, self.state, self.autoescape
        )
        ctx.blocks = self.blocks
        ctx.lineage = self.lineage
        return ctx

    def snapshot(self) -> Context:
        # the scope dicts are shared on purpose: a macro sees names that get
        # defined after it, as long as that happens before it is called
        return self.derive(list(self.scopes))

    def lookup(self, name: str) -> Any:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return self.env.globals.get(name, missing)

    def resolve(self, name: str) -> Any:
        value = self.lookup(name)
        if value is missing:
            return self.env.undefined(name=name)
        return value

    def get(self, name: str, default: Any = None) -> Any:
        value = self.lookup(name)
        return default if value is missing else value

    def __getitem__(self, name: str) -> Any:
        value = self.lookup(name)
        if value is missing:
            raise KeyError(name)
        return value

    def __contains__(self, name: str) -> bool:
        return self.lookup(name) is not missing

    def set(self, name: str, value: Any) -> None:
        self.scopes[-1][name] = value
        # top-level names are what `import` gets to see
        if len(self.scopes) == 1 and name[:1] != "_":
            self.exported.add(name)

    def flatten(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for scope in self.scopes:
            merged.update(scope)
        return merged

    def mark(self, text: str) -> str:
        """Rendered output is markup already when autoescaping is on."""
        return Markup(text) if self.autoescape else text


class LoopContext:
    """The `loop` variable of a for block."""

    def __init__(
        self,
        items: list,
        undefined: Callable[..., Undefined],
        depth0: int = 0,
        recurse: Callable[[Any, int], str] | None = None,
    ):
        self._items = items
        self._undefined = undefined
        self._recurse = recurse
        self._last_changed: Any = missing
        self.length = len(items)
        self.index0 = -1
        self.depth0 = depth0

    def __iter__(self) -> Iterator[Any]:
        for index, item in enumerate(self._items):
            self.index0 = index
            yield item

    def __len__(self) -> int:
        return self.length

    def __repr__(self) -> str:
        return f"<LoopContext {self.index}/{self.length}>"

    @property
    def index(self) -> int:
        return self.index0 + 1

    @property
    def revindex(self) -> int:
        return self.length - self.index0

    @property
    def revindex0(self) -> int:
        return self.length - self.index0 - 1

    @property
    def first(self) -> bool:
        return self.index0 == 0

    @property
    def last(self) -> bool:
        return self.index0 == self.length - 1

    @property
    def depth(self) -> int:
        return self.depth0 + 1

    @property
    def previtem(self) -> Any:
        if self.index0 <= 0:
            return self._undefined(hint="there is no previous item")
        return self._items[self.index0 - 1]

    @property
    def nextitem(self) -> Any:
        if self.index0 + 1 >= self.length:
            return self._undefined(hint="there is no next item")
        return self._items[self.index0 + 1]

    def cycle(self, *values: Any) -> Any:
        if not values:
            raise TemplateRuntimeError("loop.cycle() needs at least one value")
        return values[self.index0 % len(values)]

    def changed(self, *value: Any) -> bool:
        """True when called with something else than the last time."""
        if self._last_changed != value:
            self._last_changed = value
            return True
        return False

    def __call__(self, iterable: Any) -> str:
        if self._recurse is None:
            raise TemplateRuntimeError(
                "loop() can only be called in a for loop marked 'recursive'"
            )
        return self._recurse(iterable, self.depth0 + 1)


class Macro:
    def __init__(
        self,
        interpreter,
        name: str,
        params: list[str],
        defaults: list,
        body: list,
        closure: Context,
        catch_varargs: bool = False,
        catch_kwargs: bool = False,
        uses_caller: bool = False,
    ):
        self._interpreter = interpreter
        self.name = name
        self.params = params
        self.defaults = defaults
        self.body = body
        self.closure = closure
        self.catch_varargs = catch_varargs
        self.catch_kwargs = catch_kwargs
        self.uses_caller = uses_caller

    @property
    def arguments(self) -> tuple[str, ...]:
        return tuple(self.params)

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        return self._interpreter.call_macro(self, args, kwargs)

    def __repr__(self) -> str:
        return f"<Macro {self.name!r}>"


class BlockReference:
    """What `super` is inside a block: call it to render the parent block."""

    def __init__(
        self,
        name: str,
        render: Callable[[int], str],
        index: int,
        count: int,
        undefined: Callable[..., Undefined],
    ):
        self._name = name
        self._render = render
        self._index = index
        self._count = count
        self._undefined = undefined

    def __call__(self) -> str:
        return self._render(self._index)

    @property
    def super(self) -> Any:
        if self._index + 1 >= self._count:
            return self._undefined(
                hint=f"there is no block {self._name!r} further up to call super() on"
            )
        return BlockReference(
            self._name, self._render, self._index + 1, self._count, self._undefined
        )

    def __repr__(self) -> str:
        return f"<BlockReference {self._name!r}>"


class TemplateReference:
    """`self` in a template: `self.title()` renders the block `title`."""

    def __init__(self, blocks: dict[str, list], render: Callable[[str], str]):
        self._blocks = blocks
        self._render = render

    def __getattr__(self, name: str):
        if name[:1] == "_" or name not in self._blocks:
            raise AttributeError(name)
        return lambda: self._render(name)

    def __repr__(self) -> str:
        return "<TemplateReference>"


class TemplateModule:
    """What `{% import "x" as y %}` binds: the top-level names of a template."""

    def __init__(self, name: str | None, exports: dict[str, Any], body: str = ""):
        self.__dict__.update(exports)
        self._name = name
        self._body = body

    def __html__(self) -> Markup:
        return Markup(self._body)

    def __str__(self) -> str:
        return self._body

    def __repr__(self) -> str:
        return f"<TemplateModule {self._name!r}>"


class Namespace:
    """namespace(): a bag of attributes that `{% set ns.x = ... %}` can change.

    Assignments inside a for loop don't survive the iteration, this is the
    way to carry something out of one.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        self.__dict__.update(dict(*args, **kwargs))

    def __getitem__(self, key: str) -> Any:
        return self.__dict__[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.__dict__[key] = value

    def __repr__(self) -> str:
        return f"<Namespace {self.__dict__!r}>"


class Cycler:
    """cycler("odd", "even"): like loop.cycle, but not tied to one loop."""

    def __init__(self, *items: Any):
        if not items:
            raise TemplateRuntimeError("cycler() needs at least one value")
        self.items = items
        self.pos = 0

    def reset(self) -> None:
        self.pos = 0

    @property
    def current(self) -> Any:
        return self.items[self.pos]

    def next(self) -> Any:
        value = self.current
        self.pos = (self.pos + 1) % len(self.items)
        return value

    __next__ = next


class Joiner:
    """joiner(", "): returns "" on the first call and the separator after."""

    def __init__(self, sep: str = ", "):
        self.sep = sep
        self.used = False

    def __call__(self) -> str:
        if not self.used:
            self.used = True
            return ""
        return self.sep
