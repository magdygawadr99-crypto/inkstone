from __future__ import annotations

from . import nodes
from .errors import TemplateSyntaxError
from .lexer import (
    BLOCK_BEGIN,
    BLOCK_END,
    DATA,
    EOF,
    FLOAT,
    INTEGER,
    NAME,
    OP,
    STRING,
    VARIABLE_BEGIN,
    VARIABLE_END,
    Token,
    TokenStream,
    describe,
    tokenize,
)

_CONSTANTS = {
    "true": True,
    "True": True,
    "false": False,
    "False": False,
    "none": None,
    "None": None,
}
_COMPARE_OPS = ("==", "!=", "<", "<=", ">", ">=")

# tags that only make sense inside some other block; used to tell "you forgot
# to close something" apart from a plain typo in a tag name
_CLOSERS = frozenset(
    "elif else endif endfor endset endwith endblock endmacro endcall endfilter "
    "endautoescape endraw".split()
)

# a name after `x is sometest` is the test's argument, unless it is one of
# these, which carry on the surrounding expression
_NOT_A_TEST_ARG = ("and", "or", "not", "if", "else", "in")


def _any_of(names: tuple[str, ...]) -> str:
    quoted = [repr(name) for name in names]
    if len(quoted) == 1:
        return quoted[0]
    return ", ".join(quoted[:-1]) + " or " + quoted[-1]


class Parser:
    """Recursive descent parser, tokens in, nodes.Template out."""

    def __init__(self, tokens: list[Token], path: str | None = None):
        self.stream = TokenStream(tokens, path)
        self.path = path
        # (tag, line, tags that may end it) for every block we are inside of
        self._open: list[tuple[str, int, tuple[str, ...]]] = []
        self._block_lines: dict[str, int] = {}
        self._extends_line: int | None = None
        self._loop_depth = 0

    def parse(self) -> nodes.Template:
        try:
            body = self._parse_body()
        except RecursionError:
            self.fail("this is nested too deeply to parse")
        return nodes.Template(body, lineno=1)

    def fail(self, message: str, lineno: int | None = None):
        if lineno is None:
            lineno = self.stream.current.lineno
        raise TemplateSyntaxError(message, path=self.path, line=lineno)

    def _parse_body(self, end_tags: tuple[str, ...] = ()) -> list[nodes.Node]:
        """Parse until one of `end_tags` and stop right at its name."""
        stream = self.stream
        body: list[nodes.Node] = []
        while True:
            token = stream.current
            if token.type == DATA:
                stream.next()
                body.append(nodes.Data(token.value, lineno=token.lineno))
            elif token.type == VARIABLE_BEGIN:
                stream.next()
                expr = self._parse_tuple()
                stream.expect(VARIABLE_END)
                body.append(nodes.Output(expr, lineno=token.lineno))
            elif token.type == BLOCK_BEGIN:
                stream.next()
                if stream.current.type == NAME and stream.current.value in end_tags:
                    return body
                body.append(self._parse_statement())
                stream.expect(BLOCK_END)
            else:
                if end_tags:
                    tag, lineno, _ = self._open[-1]
                    self.fail(
                        f"unexpected end of template, the {tag!r} block opened on"
                        f" line {lineno} is never closed (expected"
                        f" {_any_of(end_tags)})"
                    )
                return body

    def _block_body(
        self, tag: str, lineno: int, end_tags: tuple[str, ...]
    ) -> list[nodes.Node]:
        self.stream.expect(BLOCK_END)
        self._open.append((tag, lineno, end_tags))
        body = self._parse_body(end_tags)
        self._open.pop()
        return body

    def _isolated_body(
        self, tag: str, lineno: int, end_tags: tuple[str, ...]
    ) -> list[nodes.Node]:
        # break/continue must not reach through a macro or block into a loop
        # around it
        saved, self._loop_depth = self._loop_depth, 0
        try:
            return self._block_body(tag, lineno, end_tags)
        finally:
            self._loop_depth = saved

    def _parse_statement(self) -> nodes.Node:
        token = self.stream.current
        if token.type != NAME:
            self.fail(f"expected a tag name, got {describe(token)}")
        handler = self._tags.get(token.value)
        if handler is None:
            self._fail_unknown_tag(token)
        return handler(self)

    def _fail_unknown_tag(self, token: Token):
        name = token.value
        if name in _CLOSERS:
            if self._open:
                tag, lineno, end_tags = self._open[-1]
                self.fail(
                    f"unexpected {name!r}, the {tag!r} block opened on line"
                    f" {lineno} needs {_any_of(end_tags)}",
                    token.lineno,
                )
            self.fail(f"unexpected {name!r}, there is no open block", token.lineno)
        self.fail(f"unknown tag {name!r}", token.lineno)

    def _stmt_if(self) -> nodes.If:
        token = self.stream.next()
        branches = []
        orelse: list[nodes.Node] = []
        while True:
            test = self.parse_expression()
            body = self._block_body("if", token.lineno, ("elif", "else", "endif"))
            branches.append((test, body))
            tag = self.stream.next().value
            if tag == "elif":
                continue
            if tag == "else":
                orelse = self._block_body("if", token.lineno, ("endif",))
                self.stream.next()
            break
        return nodes.If(branches, orelse, lineno=token.lineno)

    def _stmt_for(self) -> nodes.For:
        token = self.stream.next()
        target = self._parse_assign_target(extra_end=("in",))
        self.stream.expect_name("in")
        iterable = self._parse_tuple(with_condexpr=False, extra_end=("recursive",))
        test = None
        if self.stream.skip_name("if"):
            test = self.parse_expression()
        recursive = self.stream.skip_name("recursive")
        self._loop_depth += 1
        body = self._block_body("for", token.lineno, ("else", "endfor"))
        self._loop_depth -= 1
        orelse: list[nodes.Node] = []
        if self.stream.next().value == "else":
            orelse = self._block_body("for", token.lineno, ("endfor",))
            self.stream.next()
        return nodes.For(
            target, iterable, body, orelse, test, recursive, lineno=token.lineno
        )

    def _stmt_set(self) -> nodes.Node:
        token = self.stream.next()
        target: nodes.Expr
        if self.stream.current.type == NAME and self.stream.look().test(OP, "."):
            name = self.stream.next()
            self.stream.next()
            attr = self.stream.expect_name()
            target = nodes.NSRef(name.value, attr.value, lineno=name.lineno)
        else:
            target = self._parse_assign_target()
        if self.stream.skip_op("="):
            value = self._parse_tuple()
            return nodes.Set(target, value, lineno=token.lineno)
        if isinstance(target, nodes.TupleLit):
            self.fail("a block set needs a single name to assign to", token.lineno)
        filters = None
        if self.stream.at_op("|"):
            filters = self._parse_filter(None)
        body = self._block_body("set", token.lineno, ("endset",))
        self.stream.next()
        return nodes.SetBlock(target, filters, body, lineno=token.lineno)

    def _stmt_with(self) -> nodes.With:
        token = self.stream.next()
        targets: list[nodes.Expr] = []
        values: list[nodes.Expr] = []
        while self.stream.current.type != BLOCK_END:
            if targets:
                self.stream.expect_op(",")
            target = self._parse_primary()
            self._check_target(target)
            self.stream.expect_op("=")
            targets.append(target)
            values.append(self.parse_expression())
        body = self._block_body("with", token.lineno, ("endwith",))
        self.stream.next()
        return nodes.With(targets, values, body, lineno=token.lineno)

    def _stmt_block(self) -> nodes.Block:
        token = self.stream.next()
        if self.stream.current.type != NAME:
            self.fail(f"expected a block name, got {describe(self.stream.current)}")
        name = self.stream.next().value
        if name in self._block_lines:
            self.fail(
                f"block {name!r} is defined twice, first on line"
                f" {self._block_lines[name]}",
                token.lineno,
            )
        self._block_lines[name] = token.lineno
        if self.stream.at_op("-"):
            self.fail("block names can't contain hyphens, use an underscore")
        scoped = required = False
        while self.stream.at_name("scoped", "required"):
            if self.stream.next().value == "scoped":
                scoped = True
            else:
                required = True
        body = self._isolated_body("block", token.lineno, ("endblock",))
        self.stream.next()
        if self.stream.current.type == NAME:
            closing = self.stream.next()
            if closing.value != name:
                self.fail(
                    f"'endblock {closing.value}' doesn't match the block {name!r}"
                    f" opened on line {token.lineno}",
                    closing.lineno,
                )
        if required:
            for node in body:
                if not isinstance(node, nodes.Data) or node.text.strip():
                    self.fail(
                        "a required block can only contain whitespace and comments",
                        node.lineno,
                    )
        return nodes.Block(name, body, scoped, required, lineno=token.lineno)

    def _stmt_extends(self) -> nodes.Extends:
        token = self.stream.next()
        if self._open:
            self.fail(
                f"'extends' has to be at the top level, not inside a"
                f" {self._open[-1][0]!r} block",
                token.lineno,
            )
        if self._extends_line is not None:
            self.fail(
                f"a template can only extend one parent, there already is an"
                f" 'extends' on line {self._extends_line}",
                token.lineno,
            )
        self._extends_line = token.lineno
        return nodes.Extends(self.parse_expression(), lineno=token.lineno)

    def _at_context_modifier(self) -> bool:
        if not self.stream.at_name("with", "without"):
            return False
        return self.stream.look().test(NAME, "context")

    def _parse_context_modifier(self, default: bool) -> bool:
        """`with context` or `without context` after an include or import."""
        if not self._at_context_modifier():
            return default
        with_context = self.stream.next().value == "with"
        self.stream.next()
        return with_context

    def _stmt_include(self) -> nodes.Include:
        token = self.stream.next()
        template = self.parse_expression()
        ignore_missing = False
        if self.stream.at_name("ignore") and self.stream.look().test(NAME, "missing"):
            self.stream.skip(2)
            ignore_missing = True
        with_context = self._parse_context_modifier(True)
        return nodes.Include(
            template, with_context, ignore_missing, lineno=token.lineno
        )

    def _stmt_import(self) -> nodes.Import:
        token = self.stream.next()
        template = self.parse_expression()
        self.stream.expect_name("as")
        target = self._parse_plain_name()
        with_context = self._parse_context_modifier(False)
        return nodes.Import(template, target, with_context, lineno=token.lineno)

    def _stmt_from(self) -> nodes.FromImport:
        token = self.stream.next()
        template = self.parse_expression()
        self.stream.expect_name("import")
        names: list[tuple[str, str]] = []
        while self.stream.current.type != BLOCK_END:
            # a macro may well be called `with`, so look one token further
            if self._at_context_modifier():
                break
            name = self.stream.expect_name()
            if name.value.startswith("_"):
                self.fail(
                    "names starting with an underscore are private to their"
                    " template and can't be imported",
                    name.lineno,
                )
            alias = name.value
            if self.stream.skip_name("as"):
                alias = self._parse_plain_name()
            names.append((name.value, alias))
            if not self.stream.skip_op(","):
                break
        if not names:
            self.fail("expected the names to import", token.lineno)
        with_context = self._parse_context_modifier(False)
        return nodes.FromImport(template, names, with_context, lineno=token.lineno)

    def _parse_signature(self) -> tuple[list[str], list[nodes.Expr]]:
        params: list[str] = []
        defaults: list[nodes.Expr] = []
        self.stream.expect_op("(")
        while not self.stream.at_op(")"):
            if params:
                self.stream.expect_op(",")
                if self.stream.at_op(")"):
                    break
            token = self.stream.current
            name = self._parse_plain_name()
            if name in params:
                self.fail(f"duplicate parameter {name!r}", token.lineno)
            if self.stream.skip_op("="):
                defaults.append(self.parse_expression())
            elif defaults:
                self.fail(
                    f"parameter {name!r} without a default follows parameters"
                    " with defaults",
                    token.lineno,
                )
            params.append(name)
        self.stream.expect_op(")")
        return params, defaults

    def _stmt_macro(self) -> nodes.Macro:
        token = self.stream.next()
        name = self._parse_plain_name()
        params, defaults = self._parse_signature()
        body = self._isolated_body("macro", token.lineno, ("endmacro",))
        self.stream.next()
        # varargs, kwargs and caller only exist in macros that mention them,
        # so that passing too much to the others is an error
        used = {n.name for stmt in body for n in stmt.find_all(nodes.Name)}
        return nodes.Macro(
            name,
            params,
            defaults,
            body,
            catch_varargs="varargs" in used,
            catch_kwargs="kwargs" in used,
            uses_caller="caller" in used,
            lineno=token.lineno,
        )

    def _stmt_call(self) -> nodes.CallBlock:
        token = self.stream.next()
        params: list[str] = []
        defaults: list[nodes.Expr] = []
        if self.stream.at_op("("):
            params, defaults = self._parse_signature()
        call = self.parse_expression()
        if not isinstance(call, nodes.Call):
            self.fail("'call' needs a macro call, like {% call name() %}", token.lineno)
        body = self._isolated_body("call", token.lineno, ("endcall",))
        self.stream.next()
        return nodes.CallBlock(call, params, defaults, body, lineno=token.lineno)

    def _stmt_filter(self) -> nodes.FilterBlock:
        token = self.stream.next()
        filters = self._parse_filter(None, start_inline=True)
        body = self._block_body("filter", token.lineno, ("endfilter",))
        self.stream.next()
        return nodes.FilterBlock(filters, body, lineno=token.lineno)

    def _stmt_autoescape(self) -> nodes.Autoescape:
        token = self.stream.next()
        enabled = self.parse_expression()
        body = self._block_body("autoescape", token.lineno, ("endautoescape",))
        self.stream.next()
        return nodes.Autoescape(enabled, body, lineno=token.lineno)

    def _stmt_do(self) -> nodes.Do:
        token = self.stream.next()
        return nodes.Do(self._parse_tuple(), lineno=token.lineno)

    def _stmt_loop_control(self) -> nodes.Node:
        token = self.stream.next()
        if not self._loop_depth:
            self.fail(f"{token.value!r} outside of a for loop", token.lineno)
        if token.value == "break":
            return nodes.Break(lineno=token.lineno)
        return nodes.Continue(lineno=token.lineno)

    _tags = {
        "if": _stmt_if,
        "for": _stmt_for,
        "set": _stmt_set,
        "with": _stmt_with,
        "block": _stmt_block,
        "extends": _stmt_extends,
        "include": _stmt_include,
        "import": _stmt_import,
        "from": _stmt_from,
        "macro": _stmt_macro,
        "call": _stmt_call,
        "filter": _stmt_filter,
        "autoescape": _stmt_autoescape,
        "do": _stmt_do,
        "break": _stmt_loop_control,
        "continue": _stmt_loop_control,
    }

    def _parse_plain_name(self) -> str:
        token = self.stream.current
        if token.type != NAME:
            self.fail(f"expected a name, got {describe(token)}")
        if token.value in _CONSTANTS:
            self.fail(f"{token.value!r} can't be used as a name")
        return self.stream.next().value

    def _parse_assign_target(self, extra_end: tuple[str, ...] = ()) -> nodes.Expr:
        target = self._parse_tuple(simplified=True, extra_end=extra_end)
        self._check_target(target)
        return target

    def _check_target(self, node: nodes.Expr) -> None:
        if isinstance(node, nodes.Name):
            return
        if isinstance(node, nodes.TupleLit) and node.items:
            for item in node.items:
                self._check_target(item)
            return
        if isinstance(node, nodes.Const):
            what = "a literal"
        elif isinstance(node, nodes.TupleLit):
            what = "an empty tuple"
        else:
            what = "this expression"
        self.fail(f"can't assign to {what}", node.lineno)

    def parse_expression(self, with_condexpr: bool = True) -> nodes.Expr:
        if with_condexpr:
            return self._parse_condexpr()
        return self._parse_or()

    def _parse_condexpr(self) -> nodes.Expr:
        lineno = self.stream.current.lineno
        expr = self._parse_or()
        while self.stream.skip_name("if"):
            test = self._parse_or()
            orelse = None
            if self.stream.skip_name("else"):
                orelse = self._parse_condexpr()
            expr = nodes.CondExpr(test, expr, orelse, lineno=lineno)
            lineno = self.stream.current.lineno
        return expr

    def _parse_or(self) -> nodes.Expr:
        left = self._parse_and()
        while self.stream.at_name("or"):
            token = self.stream.next()
            left = nodes.Or(left, self._parse_and(), lineno=token.lineno)
        return left

    def _parse_and(self) -> nodes.Expr:
        left = self._parse_not()
        while self.stream.at_name("and"):
            token = self.stream.next()
            left = nodes.And(left, self._parse_not(), lineno=token.lineno)
        return left

    def _parse_not(self) -> nodes.Expr:
        if self.stream.at_name("not"):
            token = self.stream.next()
            return nodes.Not(self._parse_not(), lineno=token.lineno)
        return self._parse_compare()

    def _parse_compare(self) -> nodes.Expr:
        stream = self.stream
        lineno = stream.current.lineno
        left = self._parse_additive()
        ops: list[tuple[str, nodes.Expr]] = []
        while True:
            token = stream.current
            if token.type == OP and token.value in _COMPARE_OPS:
                stream.next()
                ops.append((token.value, self._parse_additive()))
            elif stream.skip_name("in"):
                ops.append(("in", self._parse_additive()))
            elif token.test(NAME, "not") and stream.look().test(NAME, "in"):
                stream.skip(2)
                ops.append(("not in", self._parse_additive()))
            else:
                break
        if not ops:
            return left
        return nodes.Compare(left, ops, lineno=lineno)

    def _parse_additive(self) -> nodes.Expr:
        left = self._parse_concat()
        while self.stream.at_op("+", "-"):
            token = self.stream.next()
            right = self._parse_concat()
            left = nodes.BinOp(token.value, left, right, lineno=token.lineno)
        return left

    def _parse_concat(self) -> nodes.Expr:
        # `~` sits between additive and multiplicative, as in Jinja
        lineno = self.stream.current.lineno
        items = [self._parse_term()]
        while self.stream.skip_op("~"):
            items.append(self._parse_term())
        if len(items) == 1:
            return items[0]
        return nodes.Concat(items, lineno=lineno)

    def _parse_term(self) -> nodes.Expr:
        left = self._parse_pow()
        while self.stream.at_op("*", "/", "//", "%"):
            token = self.stream.next()
            right = self._parse_pow()
            left = nodes.BinOp(token.value, left, right, lineno=token.lineno)
        return left

    def _parse_pow(self) -> nodes.Expr:
        # Jinja quirks, kept on purpose: `**` is left associative and a unary
        # minus binds tighter than it, so 2**3**2 is 64 and -2**2 is 4
        left = self._parse_unary()
        while self.stream.at_op("**"):
            token = self.stream.next()
            right = self._parse_unary()
            left = nodes.BinOp("**", left, right, lineno=token.lineno)
        return left

    def _parse_unary(self, with_filter: bool = True) -> nodes.Expr:
        token = self.stream.current
        node: nodes.Expr
        if token.test(OP, "-"):
            self.stream.next()
            node = nodes.Neg(self._parse_unary(False), lineno=token.lineno)
        elif token.test(OP, "+"):
            self.stream.next()
            node = nodes.Pos(self._parse_unary(False), lineno=token.lineno)
        else:
            node = self._parse_primary()
        node = self._parse_postfix(node)
        if with_filter:
            node = self._parse_filter_expr(node)
        return node

    def _parse_primary(self) -> nodes.Expr:
        token = self.stream.current
        if token.type == NAME:
            self.stream.next()
            if token.value in _CONSTANTS:
                return nodes.Const(_CONSTANTS[token.value], lineno=token.lineno)
            return nodes.Name(token.value, lineno=token.lineno)
        if token.type == STRING:
            # adjacent string literals are glued together, like in Python
            parts = []
            while self.stream.current.type == STRING:
                parts.append(self.stream.next().value)
            return nodes.Const("".join(parts), lineno=token.lineno)
        if token.type in (INTEGER, FLOAT):
            self.stream.next()
            return nodes.Const(token.value, lineno=token.lineno)
        if token.test(OP, "("):
            self.stream.next()
            node = self._parse_tuple(explicit_parentheses=True)
            self.stream.expect_op(")")
            return node
        if token.test(OP, "["):
            return self._parse_list()
        if token.test(OP, "{"):
            return self._parse_dict()
        self.fail(f"expected an expression, got {describe(token)}", token.lineno)

    def _parse_tuple(
        self,
        simplified: bool = False,
        with_condexpr: bool = True,
        extra_end: tuple[str, ...] = (),
        explicit_parentheses: bool = False,
    ) -> nodes.Expr:
        """Parse `a` or `a, b, c`; the latter comes back as a TupleLit.

        `simplified` only allows names and literals (assignment targets),
        `extra_end` lists names that end the tuple, like the `in` of a for.
        """
        lineno = self.stream.current.lineno
        if simplified:
            parse = self._parse_primary
        elif with_condexpr:
            parse = self.parse_expression
        else:
            parse = self._parse_or
        items: list[nodes.Expr] = []
        is_tuple = False
        while True:
            if items:
                self.stream.expect_op(",")
            if self._at_tuple_end(extra_end):
                break
            items.append(parse())
            if not self.stream.at_op(","):
                break
            is_tuple = True
        if not is_tuple:
            if items:
                return items[0]
            if not explicit_parentheses:
                token = self.stream.current
                self.fail(f"expected an expression, got {describe(token)}")
        return nodes.TupleLit(items, lineno=lineno)

    def _at_tuple_end(self, extra_end: tuple[str, ...]) -> bool:
        token = self.stream.current
        if token.type in (VARIABLE_END, BLOCK_END, EOF) or token.test(OP, ")"):
            return True
        return token.type == NAME and token.value in extra_end

    def _parse_list(self) -> nodes.ListLit:
        token = self.stream.expect_op("[")
        items: list[nodes.Expr] = []
        while not self.stream.at_op("]"):
            if items:
                self.stream.expect_op(",")
                if self.stream.at_op("]"):
                    break
            items.append(self.parse_expression())
        self.stream.expect_op("]")
        return nodes.ListLit(items, lineno=token.lineno)

    def _parse_dict(self) -> nodes.DictLit:
        token = self.stream.expect_op("{")
        items: list[tuple[nodes.Expr, nodes.Expr]] = []
        while not self.stream.at_op("}"):
            if items:
                self.stream.expect_op(",")
                if self.stream.at_op("}"):
                    break
            key = self.parse_expression()
            self.stream.expect_op(":")
            items.append((key, self.parse_expression()))
        self.stream.expect_op("}")
        return nodes.DictLit(items, lineno=token.lineno)

    def _parse_postfix(self, node: nodes.Expr) -> nodes.Expr:
        while True:
            if self.stream.at_op(".", "["):
                node = self._parse_subscript(node)
            elif self.stream.at_op("("):
                node = self._parse_call(node)
            else:
                return node

    def _parse_filter_expr(self, node: nodes.Expr) -> nodes.Expr:
        while True:
            if self.stream.at_op("|"):
                node = self._parse_filter(node)
            elif self.stream.at_name("is"):
                node = self._parse_test(node)
            elif self.stream.at_op("("):
                # the result of a filter can be called as well
                node = self._parse_call(node)
            else:
                return node

    def _parse_subscript(self, node: nodes.Expr) -> nodes.Expr:
        token = self.stream.next()
        if token.value == ".":
            attr = self.stream.next()
            if attr.type == NAME:
                return nodes.Getattr(node, attr.value, lineno=token.lineno)
            if attr.type != INTEGER:
                self.fail(
                    f"expected a name or number after '.', got {describe(attr)}",
                    attr.lineno,
                )
            # `rows.0` is the same as `rows[0]`
            index = nodes.Const(attr.value, lineno=attr.lineno)
            return nodes.Getitem(node, index, lineno=token.lineno)
        if self.stream.at_op("]"):
            self.fail("expected an index or a slice between '[' and ']'")
        parts = [self._parse_subscribed()]
        while self.stream.skip_op(","):
            parts.append(self._parse_subscribed())
        self.stream.expect_op("]")
        if len(parts) == 1:
            arg = parts[0]
        else:
            arg = nodes.TupleLit(parts, lineno=token.lineno)
        return nodes.Getitem(node, arg, lineno=token.lineno)

    def _parse_subscribed(self) -> nodes.Expr:
        """One item between brackets: an index or a `start:stop:step` slice."""
        stream = self.stream
        lineno = stream.current.lineno
        start = stop = step = None
        if not stream.at_op(":"):
            start = self.parse_expression()
            if not stream.at_op(":"):
                return start
        stream.next()
        if not stream.at_op(":", "]", ","):
            stop = self.parse_expression()
        if stream.skip_op(":") and not stream.at_op("]", ","):
            step = self.parse_expression()
        return nodes.Slice(start, stop, step, lineno=lineno)

    def _parse_call_args(self):
        token = self.stream.expect_op("(")
        args: list[nodes.Expr] = []
        kwargs: list[tuple[str, nodes.Expr]] = []
        dyn_args = dyn_kwargs = None

        def ensure(ok: bool) -> None:
            if not ok:
                self.fail("invalid order of arguments in call", token.lineno)

        first = True
        while not self.stream.at_op(")"):
            if not first:
                self.stream.expect_op(",")
                if self.stream.at_op(")"):
                    break
            first = False
            if self.stream.skip_op("*"):
                ensure(dyn_args is None and dyn_kwargs is None)
                dyn_args = self.parse_expression()
            elif self.stream.skip_op("**"):
                ensure(dyn_kwargs is None)
                dyn_kwargs = self.parse_expression()
            elif self.stream.current.type == NAME and self.stream.look().test(OP, "="):
                ensure(dyn_kwargs is None)
                key = self.stream.next()
                self.stream.next()
                if any(key.value == name for name, _ in kwargs):
                    self.fail(f"keyword argument {key.value!r} repeated", key.lineno)
                kwargs.append((key.value, self.parse_expression()))
            else:
                ensure(dyn_args is None and dyn_kwargs is None and not kwargs)
                args.append(self.parse_expression())
        self.stream.expect_op(")")
        return args, kwargs, dyn_args, dyn_kwargs

    def _parse_call(self, node: nodes.Expr) -> nodes.Call:
        lineno = self.stream.current.lineno
        args, kwargs, dyn_args, dyn_kwargs = self._parse_call_args()
        return nodes.Call(node, args, kwargs, dyn_args, dyn_kwargs, lineno=lineno)

    def _parse_dotted_name(self, what: str) -> tuple[str, int]:
        token = self.stream.current
        if token.type != NAME:
            self.fail(f"expected a {what} name, got {describe(token)}")
        name = self.stream.next().value
        while self.stream.skip_op("."):
            name += "." + self.stream.expect_name().value
        return name, token.lineno

    def _parse_filter(
        self, node: nodes.Expr | None, start_inline: bool = False
    ) -> nodes.Filter:
        """Parse `| name(args) | name ...` applied to `node`.

        With `start_inline` the first pipe is left out, as in `{% filter x %}`.
        """
        while self.stream.at_op("|") or start_inline:
            if not start_inline:
                self.stream.next()
            start_inline = False
            name, lineno = self._parse_dotted_name("filter")
            args, kwargs, dyn_args, dyn_kwargs = [], [], None, None
            if self.stream.at_op("("):
                args, kwargs, dyn_args, dyn_kwargs = self._parse_call_args()
            node = nodes.Filter(
                node, name, args, kwargs, dyn_args, dyn_kwargs, lineno=lineno
            )
        return node

    def _parse_test(self, node: nodes.Expr) -> nodes.Test:
        self.stream.next()
        negated = self.stream.skip_name("not")
        name, lineno = self._parse_dotted_name("test")
        args, kwargs, dyn_args, dyn_kwargs = [], [], None, None
        token = self.stream.current
        if token.test(OP, "("):
            args, kwargs, dyn_args, dyn_kwargs = self._parse_call_args()
        elif token.test(NAME, "is"):
            self.fail("tests can't be chained, use 'and' between them")
        elif (
            token.type in (STRING, INTEGER, FLOAT)
            or (token.type == NAME and token.value not in _NOT_A_TEST_ARG)
            or (token.type == OP and token.value in ("[", "{"))
        ):
            # `x is divisibleby 3`: a single argument doesn't need parentheses
            args = [self._parse_postfix(self._parse_primary())]
        return nodes.Test(
            node, name, args, kwargs, dyn_args, dyn_kwargs, negated, lineno=lineno
        )


def parse(source: str, path: str | None = None, **options) -> nodes.Template:
    """Lex and parse in one go; `options` are those of the Lexer."""
    return Parser(tokenize(source, path, **options), path).parse()
