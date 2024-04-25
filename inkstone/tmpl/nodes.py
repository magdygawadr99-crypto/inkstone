from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Iterator


def _child_nodes(value: Any) -> Iterator[Node]:
    if isinstance(value, Node):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _child_nodes(item)


@dataclass
class Node:
    # not part of equality, so tests can compare trees without caring where
    # the nodes came from
    lineno: int = field(default=0, kw_only=True, compare=False)

    def iter_child_nodes(self) -> Iterator[Node]:
        for f in fields(self):
            yield from _child_nodes(getattr(self, f.name))

    def find_all(self, node_type) -> Iterator[Any]:
        """All descendants of the given type(s), in source order."""
        # with a stack instead of recursion: `a + b + c + ...` makes a tree
        # that is as deep as the expression is long
        todo = list(self.iter_child_nodes())
        todo.reverse()
        while todo:
            node = todo.pop()
            if isinstance(node, node_type):
                yield node
            children = list(node.iter_child_nodes())
            children.reverse()
            todo.extend(children)


class Stmt(Node):
    pass


class Expr(Node):
    pass


@dataclass
class Template(Node):
    body: list[Node]


@dataclass
class Data(Stmt):
    text: str


@dataclass
class Output(Stmt):
    expr: Expr


@dataclass
class If(Stmt):
    # one (test, body) pair for the `if` and one more per `elif`
    branches: list[tuple[Expr, list[Node]]]
    orelse: list[Node]


@dataclass
class For(Stmt):
    target: Expr
    iter: Expr
    body: list[Node]
    orelse: list[Node]
    test: Expr | None = None
    recursive: bool = False


@dataclass
class Set(Stmt):
    target: Expr
    value: Expr


@dataclass
class SetBlock(Stmt):
    target: Expr
    filter: Filter | None
    body: list[Node]


@dataclass
class With(Stmt):
    targets: list[Expr]
    values: list[Expr]
    body: list[Node]


@dataclass
class Block(Stmt):
    name: str
    body: list[Node]
    scoped: bool = False
    required: bool = False


@dataclass
class Extends(Stmt):
    template: Expr


@dataclass
class Include(Stmt):
    template: Expr
    with_context: bool = True
    ignore_missing: bool = False


@dataclass
class Import(Stmt):
    template: Expr
    target: str
    with_context: bool = False


@dataclass
class FromImport(Stmt):
    template: Expr
    # (name in the imported template, name it gets here)
    names: list[tuple[str, str]]
    with_context: bool = False


@dataclass
class Macro(Stmt):
    name: str
    params: list[str]
    # defaults belong to the last len(defaults) params, like in Python
    defaults: list[Expr]
    body: list[Node]
    catch_varargs: bool = False
    catch_kwargs: bool = False
    uses_caller: bool = False


@dataclass
class CallBlock(Stmt):
    call: Call
    params: list[str]
    defaults: list[Expr]
    body: list[Node]


@dataclass
class FilterBlock(Stmt):
    filter: Filter
    body: list[Node]


@dataclass
class Autoescape(Stmt):
    enabled: Expr
    body: list[Node]


@dataclass
class Do(Stmt):
    expr: Expr


@dataclass
class Break(Stmt):
    pass


@dataclass
class Continue(Stmt):
    pass


@dataclass
class Const(Expr):
    value: Any


@dataclass
class Name(Expr):
    name: str


@dataclass
class NSRef(Expr):
    """`ns.attr` as the target of a set, for namespace() objects."""

    name: str
    attr: str


@dataclass
class TupleLit(Expr):
    items: list[Expr]


@dataclass
class ListLit(Expr):
    items: list[Expr]


@dataclass
class DictLit(Expr):
    items: list[tuple[Expr, Expr]]


@dataclass
class BinOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class Neg(Expr):
    operand: Expr


@dataclass
class Pos(Expr):
    operand: Expr


@dataclass
class Not(Expr):
    operand: Expr


@dataclass
class And(Expr):
    left: Expr
    right: Expr


@dataclass
class Or(Expr):
    left: Expr
    right: Expr


@dataclass
class Compare(Expr):
    # `a < b <= c` is Compare(a, [("<", b), ("<=", c)])
    left: Expr
    ops: list[tuple[str, Expr]]


@dataclass
class Concat(Expr):
    items: list[Expr]


@dataclass
class CondExpr(Expr):
    test: Expr
    then: Expr
    orelse: Expr | None


@dataclass
class Getattr(Expr):
    obj: Expr
    attr: str


@dataclass
class Getitem(Expr):
    obj: Expr
    index: Expr


@dataclass
class Slice(Expr):
    start: Expr | None
    stop: Expr | None
    step: Expr | None


@dataclass
class Call(Expr):
    func: Expr
    args: list[Expr]
    kwargs: list[tuple[str, Expr]]
    dyn_args: Expr | None = None
    dyn_kwargs: Expr | None = None


@dataclass
class Filter(Expr):
    # node is None for the filters of `{% filter %}` and block `{% set %}`,
    # where the value comes from the rendered body
    node: Expr | None
    name: str
    args: list[Expr]
    kwargs: list[tuple[str, Expr]]
    dyn_args: Expr | None = None
    dyn_kwargs: Expr | None = None


@dataclass
class Test(Expr):
    node: Expr
    name: str
    args: list[Expr]
    kwargs: list[tuple[str, Expr]]
    dyn_args: Expr | None = None
    dyn_kwargs: Expr | None = None
    negated: bool = False
