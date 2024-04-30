from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Any

from inkstone.errors import InkstoneError

from . import nodes
from .errors import (
    TemplateError,
    TemplateNotFound,
    TemplateRuntimeError,
    UndefinedError,
)
from .markup import Markup, escape
from .runtime import (
    BlockReference,
    Context,
    LoopContext,
    Macro,
    Namespace,
    TemplateModule,
    TemplateReference,
    Undefined,
    invoke,
    missing,
    type_name,
)

if TYPE_CHECKING:
    from .environment import Environment, Template

# Legitimately recursive includes (rendering a tree, say) stay far below this;
# a template that includes itself unconditionally hits it quickly.
MAX_INCLUDE_DEPTH = 50

_BINARY_OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
}

_COMPARE_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "in": lambda a, b: a in b,
    "not in": lambda a, b: a not in b,
}


class _LoopControl(BaseException):
    # Not an Exception on purpose: break and continue have to get past the
    # error handling of every statement between them and their loop.
    pass


class _Break(_LoopControl):
    pass


class _Continue(_LoopControl):
    pass


def _same_template(a: Template, b: Template) -> bool:
    return a is b or (a.name is not None and a.name == b.name)


def _label(template: Template) -> str:
    return template.name or "<string>"


class Interpreter:
    """Walks the AST of a template and produces its output.

    It keeps no state of its own between calls, everything that belongs to
    one render lives in the Context.
    """

    def __init__(self, env: Environment):
        self.env = env
        self._exec = {}
        self._eval = {}
        for name in dir(self):
            if name.startswith("_exec_"):
                self._exec[getattr(nodes, name[6:])] = getattr(self, name)
            elif name.startswith("_eval_"):
                self._eval[getattr(nodes, name[6:])] = getattr(self, name)

    def render(self, template: Template, variables: dict[str, Any]) -> str:
        ctx = Context(self.env, template, [variables])
        out: list[str] = []
        self.render_template(template, ctx, out)
        return "".join(out)

    def render_template(self, template: Template, ctx: Context, out: list[str]):
        """Run `template` and then, if it extends something, its parents."""
        while True:
            ctx.template = template
            ctx.lineage.append(template)
            for name, block in template.blocks.items():
                ctx.blocks.setdefault(name, []).append((block, template))
            ctx.parent = None
            buf: list[str] = []
            self.execute(template.root.body, ctx, buf)
            if ctx.parent is None:
                out.extend(buf)
                return
            # like Jinja: what comes before the extends tag is printed,
            # everything after it only counts for its blocks and assignments
            template, cut = ctx.parent
            out.extend(buf[:cut])

    def make_module(
        self, template: Template, ctx: Context, with_context: bool
    ) -> TemplateModule:
        imports = ctx.state.imports
        if any(_same_template(template, other) for other in imports):
            chain = " -> ".join(_label(t) for t in imports + [template])
            raise TemplateRuntimeError(f"circular import: {chain}")
        scope = ctx.flatten() if with_context else {}
        inner = Context(self.env, template, [scope], ctx.state)
        buf: list[str] = []
        imports.append(template)
        try:
            self.render_template(template, inner, buf)
        finally:
            imports.pop()
        exports = {name: scope[name] for name in inner.exported if name in scope}
        return TemplateModule(template.name, exports, "".join(buf))

    def execute(self, body: list[nodes.Node], ctx: Context, out: list[str]) -> None:
        table = self._exec
        for node in body:
            try:
                table[type(node)](node, ctx, out)
            except Exception as exc:
                self._fail(exc, node, ctx)

    def evaluate(self, node: nodes.Expr, ctx: Context) -> Any:
        try:
            return self._eval[type(node)](node, ctx)
        except Exception as exc:
            self._fail(exc, node, ctx)

    def _fail(self, exc: Exception, node: nodes.Node, ctx: Context):
        """Re-raise `exc` so that it says where in which template it happened.

        The innermost node gets here first, so errors that know their place
        already are passed on untouched.
        """
        if isinstance(exc, TemplateError):
            if exc.line is None and exc.path is None:
                exc.line = node.lineno
                exc.path = ctx.template.path
            raise exc
        if isinstance(exc, InkstoneError):
            # raised on purpose by a function from some other part of
            # inkstone, it knows better than us what to say
            raise exc
        if isinstance(exc, RecursionError):
            message = "maximum recursion depth exceeded"
        else:
            message = f"{type(exc).__name__}: {exc}"
        error = TemplateRuntimeError(message, path=ctx.template.path, line=node.lineno)
        raise error from exc

    def _truth(self, node: nodes.Expr, ctx: Context) -> bool:
        value = self.evaluate(node, ctx)
        try:
            return bool(value)
        except Exception as exc:
            self._fail(exc, node, ctx)

    def _to_text(self, value: Any, ctx: Context) -> str:
        # none prints as nothing, which is what one wants in HTML
        if value is None:
            return ""
        if ctx.autoescape:
            return escape(value)
        return str(value)

    def _capture(self, body: list[nodes.Node], ctx: Context) -> str:
        buf: list[str] = []
        ctx.scopes.append({})
        try:
            self.execute(body, ctx, buf)
        finally:
            ctx.scopes.pop()
        return ctx.mark("".join(buf))

    def _load(self, node: nodes.Expr, ctx: Context) -> Template:
        target = self.evaluate(node, ctx)
        if isinstance(target, Undefined):
            raise UndefinedError(f"can't load a template: {target._message}")
        if isinstance(target, (list, tuple)):
            return self.env.select_template(target)
        return self.env.get_template(target)

    def _assign(self, target: nodes.Expr, value: Any, ctx: Context) -> None:
        if isinstance(target, nodes.Name):
            ctx.set(target.name, value)
        elif isinstance(target, nodes.NSRef):
            namespace = ctx.resolve(target.name)
            if not isinstance(namespace, Namespace):
                raise TemplateRuntimeError(
                    f"can't set {target.name}.{target.attr}: {target.name!r} is not"
                    " a namespace() object"
                )
            setattr(namespace, target.attr, value)
        else:
            names = target.items
            try:
                values = list(value)
            except TypeError:
                raise TemplateRuntimeError(
                    f"can't unpack {type_name(value)} into {len(names)} names"
                ) from None
            if len(values) != len(names):
                raise TemplateRuntimeError(
                    f"expected {len(names)} values to unpack, got {len(values)}"
                )
            for name, item in zip(names, values):
                self._assign(name, item, ctx)

    def _exec_Data(self, node: nodes.Data, ctx: Context, out: list[str]) -> None:
        out.append(node.text)

    def _exec_Output(self, node: nodes.Output, ctx: Context, out: list[str]) -> None:
        out.append(self._to_text(self.evaluate(node.expr, ctx), ctx))

    def _exec_If(self, node: nodes.If, ctx: Context, out: list[str]) -> None:
        for test, body in node.branches:
            if self._truth(test, ctx):
                self.execute(body, ctx, out)
                return
        self.execute(node.orelse, ctx, out)

    def _exec_For(self, node: nodes.For, ctx: Context, out: list[str]) -> None:
        self._run_loop(node, self.evaluate(node.iter, ctx), ctx, out, 0)

    def _run_loop(
        self, node: nodes.For, iterable: Any, ctx: Context, out: list[str], depth: int
    ) -> None:
        items = self._loop_items(node, iterable, ctx)
        if not items:
            self.execute(node.orelse, ctx, out)
            return

        recurse = None
        if node.recursive:

            def recurse(children: Any, level: int) -> str:
                buf: list[str] = []
                self._run_loop(node, children, ctx, buf, level)
                return ctx.mark("".join(buf))

        loop = LoopContext(items, self.env.undefined, depth, recurse)
        scopes = ctx.scopes
        for item in loop:
            # a fresh scope per iteration: what the body sets is gone on the
            # next round, and closures made in the body keep their own values
            scopes.append({"loop": loop})
            try:
                self._assign(node.target, item, ctx)
                self.execute(node.body, ctx, out)
            except _Continue:
                continue
            except _Break:
                break
            finally:
                scopes.pop()

    def _loop_items(self, node: nodes.For, iterable: Any, ctx: Context) -> list:
        # Everything is pulled into a list up front, that makes loop.length,
        # loop.last and loop.nextitem trivial. Templates don't loop over
        # anything big enough for this to matter.
        try:
            iterator = iter(iterable)
        except TypeError:
            raise TemplateRuntimeError(
                f"can't loop over {type_name(iterable)}, it is not iterable"
            ) from None
        if node.test is None:
            return list(iterator)
        kept = []
        ctx.scopes.append({})
        try:
            for item in iterator:
                self._assign(node.target, item, ctx)
                if self._truth(node.test, ctx):
                    kept.append(item)
        finally:
            ctx.scopes.pop()
        return kept

    def _exec_Break(self, node: nodes.Break, ctx: Context, out: list[str]) -> None:
        raise _Break()

    def _exec_Continue(self, node: nodes.Continue, ctx: Context, out: list[str]):
        raise _Continue()

    def _exec_Set(self, node: nodes.Set, ctx: Context, out: list[str]) -> None:
        self._assign(node.target, self.evaluate(node.value, ctx), ctx)

    def _exec_SetBlock(self, node: nodes.SetBlock, ctx: Context, out: list[str]):
        value = self._capture(node.body, ctx)
        if node.filter is not None:
            value = self._apply_filters(node.filter, value, ctx)
        self._assign(node.target, value, ctx)

    def _exec_With(self, node: nodes.With, ctx: Context, out: list[str]) -> None:
        # the values are computed before the new scope exists, so that
        # `with a = 1, b = a` reads the outer a
        values = [self.evaluate(value, ctx) for value in node.values]
        ctx.scopes.append({})
        try:
            for target, value in zip(node.targets, values):
                self._assign(target, value, ctx)
            self.execute(node.body, ctx, out)
        finally:
            ctx.scopes.pop()

    def _exec_Do(self, node: nodes.Do, ctx: Context, out: list[str]) -> None:
        self.evaluate(node.expr, ctx)

    def _exec_FilterBlock(self, node: nodes.FilterBlock, ctx: Context, out: list[str]):
        value = self._apply_filters(node.filter, self._capture(node.body, ctx), ctx)
        out.append(self._to_text(value, ctx))

    def _exec_Autoescape(self, node: nodes.Autoescape, ctx: Context, out: list[str]):
        saved = ctx.autoescape
        ctx.autoescape = self._truth(node.enabled, ctx)
        try:
            self.execute(node.body, ctx, out)
        finally:
            ctx.autoescape = saved

    def _exec_Extends(self, node: nodes.Extends, ctx: Context, out: list[str]) -> None:
        parent = self._load(node.template, ctx)
        if any(_same_template(parent, seen) for seen in ctx.lineage):
            chain = " -> ".join(_label(t) for t in ctx.lineage + [parent])
            raise TemplateRuntimeError(f"circular extends: {chain}")
        ctx.parent = (parent, len(out))

    def _exec_Block(self, node: nodes.Block, ctx: Context, out: list[str]) -> None:
        if ctx.parent is not None:
            # we are past the extends tag of a child template: its blocks get
            # rendered where the parent places them, not here
            return
        chain = ctx.blocks.get(node.name)
        if not chain:
            # a block in a macro that got imported somewhere else
            chain = [(node, ctx.template)]
        if chain[0][0].required:
            raise TemplateRuntimeError(
                f"block {node.name!r} is required, but no template overrides it"
            )
        # an unscoped block only sees the template's top-level variables,
        # not e.g. the variable of a loop it happens to sit in
        scopes = list(ctx.scopes) if node.scoped else ctx.scopes[:1]
        self._run_block(node.name, chain, 0, ctx, scopes, out)

    def _run_block(
        self,
        name: str,
        chain: list,
        index: int,
        ctx: Context,
        scopes: list[dict[str, Any]],
        out: list[str],
    ) -> None:
        block, owner = chain[index]

        def render(at: int) -> str:
            buf: list[str] = []
            self._run_block(name, chain, at, ctx, scopes, buf)
            return ctx.mark("".join(buf))

        parent: Any
        if index + 1 < len(chain):
            parent = BlockReference(
                name, render, index + 1, len(chain), self.env.undefined
            )
        else:
            parent = self.env.undefined(
                hint=f"block {name!r} has no parent block to call super() on"
            )
        inner = ctx.derive(scopes + [{"super": parent}], owner)
        self.execute(block.body, inner, out)

    def _render_block(self, name: str, ctx: Context) -> str:
        buf: list[str] = []
        self._run_block(name, ctx.blocks[name], 0, ctx, ctx.scopes[:1], buf)
        return ctx.mark("".join(buf))

    def _exec_Include(self, node: nodes.Include, ctx: Context, out: list[str]) -> None:
        try:
            template = self._load(node.template, ctx)
        except TemplateNotFound:
            if node.ignore_missing:
                return
            raise
        stack = ctx.state.includes
        if len(stack) >= MAX_INCLUDE_DEPTH:
            tail = " -> ".join(stack[-3:] + [_label(template)])
            raise TemplateRuntimeError(
                f"includes are nested more than {MAX_INCLUDE_DEPTH} levels deep,"
                f" this looks like a circular include (... -> {tail})"
            )
        scope = ctx.flatten() if node.with_context else {}
        inner = Context(self.env, template, [scope], ctx.state)
        stack.append(_label(template))
        try:
            self.render_template(template, inner, out)
        finally:
            stack.pop()

    def _exec_Import(self, node: nodes.Import, ctx: Context, out: list[str]) -> None:
        template = self._load(node.template, ctx)
        ctx.set(node.target, self.make_module(template, ctx, node.with_context))

    def _exec_FromImport(self, node: nodes.FromImport, ctx: Context, out: list[str]):
        template = self._load(node.template, ctx)
        module = self.make_module(template, ctx, node.with_context)
        for name, alias in node.names:
            value = module.__dict__.get(name, missing)
            if value is missing:
                value = self.env.undefined(
                    hint=f"the template {_label(template)!r} does not export {name!r}"
                )
            ctx.set(alias, value)

    def _exec_Macro(self, node: nodes.Macro, ctx: Context, out: list[str]) -> None:
        macro = Macro(
            self,
            node.name,
            node.params,
            node.defaults,
            node.body,
            ctx.snapshot(),
            node.catch_varargs,
            node.catch_kwargs,
            node.uses_caller,
        )
        ctx.set(node.name, macro)

    def _exec_CallBlock(self, node: nodes.CallBlock, ctx: Context, out: list[str]):
        caller = Macro(
            self, "caller", node.params, node.defaults, node.body, ctx.snapshot()
        )
        call = node.call
        func = self._callee(call, ctx)
        args, kwargs = self._call_args(call, ctx)
        kwargs["caller"] = caller
        out.append(self._to_text(self._call(func, args, kwargs, ctx), ctx))

    def call_macro(self, macro: Macro, args: tuple, kwargs: dict[str, Any]) -> str:
        env = self.env
        params = macro.params
        closure = macro.closure
        ctx = closure.derive(closure.scopes + [{}])
        scope = ctx.scopes[-1]
        caller = kwargs.pop("caller", None)

        if len(args) > len(params) and not macro.catch_varargs:
            raise TemplateRuntimeError(
                f"macro {macro.name!r} takes at most {len(params)} positional"
                f" argument(s), got {len(args)}"
            )
        first_default = len(params) - len(macro.defaults)
        for index, name in enumerate(params):
            if index < len(args):
                if name in kwargs:
                    raise TemplateRuntimeError(
                        f"macro {macro.name!r} got two values for argument {name!r}"
                    )
                scope[name] = args[index]
            elif name in kwargs:
                scope[name] = kwargs.pop(name)
            elif index >= first_default:
                # evaluated per call, and may refer to the arguments before it
                default = macro.defaults[index - first_default]
                scope[name] = self.evaluate(default, ctx)
            else:
                scope[name] = env.undefined(
                    hint=f"macro {macro.name!r} was called without its argument"
                    f" {name!r}"
                )

        if caller is not None and not macro.uses_caller:
            raise TemplateRuntimeError(
                f"macro {macro.name!r} was used in a call block, but it never"
                " calls caller()"
            )
        if kwargs and not macro.catch_kwargs:
            unexpected = next(iter(kwargs))
            raise TemplateRuntimeError(
                f"macro {macro.name!r} got an unexpected keyword argument"
                f" {unexpected!r}"
            )
        if macro.uses_caller:
            if caller is None:
                caller = env.undefined(
                    hint=f"macro {macro.name!r} was not used in a call block, so"
                    " there is no caller"
                )
            scope["caller"] = caller
        if macro.catch_varargs:
            scope["varargs"] = tuple(args[len(params) :])
        if macro.catch_kwargs:
            scope["kwargs"] = kwargs

        out: list[str] = []
        self.execute(macro.body, ctx, out)
        return ctx.mark("".join(out))

    def _eval_Const(self, node: nodes.Const, ctx: Context) -> Any:
        return node.value

    def _eval_Name(self, node: nodes.Name, ctx: Context) -> Any:
        value = ctx.lookup(node.name)
        if value is missing:
            if node.name == "self":
                return TemplateReference(
                    ctx.blocks, lambda name: self._render_block(name, ctx)
                )
            return self.env.undefined(name=node.name)
        return value

    def _eval_TupleLit(self, node: nodes.TupleLit, ctx: Context) -> tuple:
        return tuple(self.evaluate(item, ctx) for item in node.items)

    def _eval_ListLit(self, node: nodes.ListLit, ctx: Context) -> list:
        return [self.evaluate(item, ctx) for item in node.items]

    def _eval_DictLit(self, node: nodes.DictLit, ctx: Context) -> dict:
        return {
            self.evaluate(key, ctx): self.evaluate(value, ctx)
            for key, value in node.items
        }

    def _eval_BinOp(self, node: nodes.BinOp, ctx: Context) -> Any:
        left = self.evaluate(node.left, ctx)
        right = self.evaluate(node.right, ctx)
        return _BINARY_OPS[node.op](left, right)

    def _eval_Neg(self, node: nodes.Neg, ctx: Context) -> Any:
        return -self.evaluate(node.operand, ctx)

    def _eval_Pos(self, node: nodes.Pos, ctx: Context) -> Any:
        return +self.evaluate(node.operand, ctx)

    def _eval_Not(self, node: nodes.Not, ctx: Context) -> bool:
        return not self._truth(node.operand, ctx)

    def _eval_And(self, node: nodes.And, ctx: Context) -> Any:
        left = self.evaluate(node.left, ctx)
        return self.evaluate(node.right, ctx) if left else left

    def _eval_Or(self, node: nodes.Or, ctx: Context) -> Any:
        left = self.evaluate(node.left, ctx)
        return left if left else self.evaluate(node.right, ctx)

    def _eval_Compare(self, node: nodes.Compare, ctx: Context) -> bool:
        left = self.evaluate(node.left, ctx)
        for op, operand in node.ops:
            right = self.evaluate(operand, ctx)
            if not _COMPARE_OPS[op](left, right):
                return False
            left = right
        return True

    def _eval_Concat(self, node: nodes.Concat, ctx: Context) -> str:
        parts = [self.evaluate(item, ctx) for item in node.items]
        parts = ["" if part is None else part for part in parts]
        if ctx.autoescape and any(hasattr(part, "__html__") for part in parts):
            return Markup("").join(parts)
        return "".join(str(part) for part in parts)

    def _eval_CondExpr(self, node: nodes.CondExpr, ctx: Context) -> Any:
        if self._truth(node.test, ctx):
            return self.evaluate(node.then, ctx)
        if node.orelse is None:
            return self.env.undefined(
                hint="the inline if was false and it has no else part"
            )
        return self.evaluate(node.orelse, ctx)

    def _eval_Getattr(self, node: nodes.Getattr, ctx: Context) -> Any:
        return self.env.getattr(self.evaluate(node.obj, ctx), node.attr)

    def _eval_Getitem(self, node: nodes.Getitem, ctx: Context) -> Any:
        obj = self.evaluate(node.obj, ctx)
        return self.env.getitem(obj, self.evaluate(node.index, ctx))

    def _eval_Slice(self, node: nodes.Slice, ctx: Context) -> slice:
        parts = (node.start, node.stop, node.step)
        return slice(*(None if p is None else self.evaluate(p, ctx) for p in parts))

    def _call_args(self, node: Any, ctx: Context) -> tuple[list, dict[str, Any]]:
        """Evaluate the arguments of a Call, Filter or Test node."""
        args = [self.evaluate(arg, ctx) for arg in node.args]
        if node.dyn_args is not None:
            args.extend(self.evaluate(node.dyn_args, ctx))
        kwargs = {name: self.evaluate(value, ctx) for name, value in node.kwargs}
        if node.dyn_kwargs is not None:
            for key, value in self.evaluate(node.dyn_kwargs, ctx).items():
                if key in kwargs:
                    raise TemplateRuntimeError(
                        f"got more than one value for the keyword argument {key!r}"
                    )
                kwargs[key] = value
        return args, kwargs

    def _callee(self, node: nodes.Call, ctx: Context) -> Any:
        func = node.func
        attr = None
        if isinstance(func, nodes.Getattr):
            attr = func.attr
        elif isinstance(func, nodes.Getitem) and isinstance(func.index, nodes.Const):
            attr = func.index.value
        if isinstance(attr, str) and attr.startswith("_"):
            # XXX this is no sandbox. It keeps templates away from the obvious
            # foot guns (obj.__class__, obj._internal()), but something like
            # "{0.__class__}".format(obj) still gets through.
            raise TemplateRuntimeError(
                f"refusing to call {attr!r}: private and dunder attributes can't"
                " be called from templates"
            )
        return self.evaluate(func, ctx)

    def _call(self, func: Any, args: list, kwargs: dict[str, Any], ctx: Context):
        if not callable(func):
            raise TemplateRuntimeError(f"{type_name(func)} is not callable")
        return invoke(func, ctx, args, kwargs)

    def _eval_Call(self, node: nodes.Call, ctx: Context) -> Any:
        func = self._callee(node, ctx)
        args, kwargs = self._call_args(node, ctx)
        return self._call(func, args, kwargs, ctx)

    def _apply_filters(self, node: nodes.Filter, value: Any, ctx: Context) -> Any:
        """Run the body of a filter block or block set through its filters."""
        if node.node is not None:
            value = self._apply_filters(node.node, value, ctx)
        args, kwargs = self._call_args(node, ctx)
        return self.env.call_filter(node.name, value, args, kwargs, ctx)

    def _eval_Filter(self, node: nodes.Filter, ctx: Context) -> Any:
        value = self.evaluate(node.node, ctx)
        args, kwargs = self._call_args(node, ctx)
        return self.env.call_filter(node.name, value, args, kwargs, ctx)

    def _eval_Test(self, node: nodes.Test, ctx: Context) -> bool:
        value = self.evaluate(node.node, ctx)
        args, kwargs = self._call_args(node, ctx)
        result = self.env.call_test(node.name, value, args, kwargs, ctx)
        return not result if node.negated else result
