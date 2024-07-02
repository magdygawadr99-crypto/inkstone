from __future__ import annotations

import re
from typing import Callable, Iterable, Iterator

from .errors import HighlightError
from .token import Error, Text, TokenType, Whitespace

# (offset into the text, token type, matched text)
Scan = Iterator[tuple[int, TokenType, str]]


class include(str):
    """Splice another state's rules in at this point."""


class default:
    """Change state without consuming anything. Only makes sense as a last rule."""

    def __init__(self, state: str | tuple[str, ...]):
        self.state = state


class _Marker:
    def __init__(self, name: str):
        self._name = name

    def __repr__(self) -> str:
        return self._name


# In a subclass's state, marks where the parent's rules for that state go.
inherit = _Marker("inherit")
# using(this) re-enters the lexer that is currently running.
this = _Marker("this")


def words(items: Iterable[str], prefix: str = "", suffix: str = "") -> str:
    """Regex alternation for a word list, longest first so "in" can't shadow "int"."""
    ordered = sorted(set(items), key=lambda w: (-len(w), w))
    return prefix + "(?:" + "|".join(re.escape(w) for w in ordered) + ")" + suffix


class _GroupMatch:
    """Just enough of a match object to hand one group to a nested action."""

    def __init__(self, start: int, text: str):
        self._start = start
        self._text = text

    def start(self, group: int = 0) -> int:
        return self._start

    def end(self, group: int = 0) -> int:
        return self._start + len(self._text)

    def group(self, group: int = 0) -> str:
        return self._text


def bygroups(*actions):
    """Give each regex group its own token type (or action).

    Text the groups don't cover, and groups paired with None, come out as
    Text rather than vanishing, so a sloppy pattern can't lose input.
    """

    def callback(lexer: Lexer, match) -> Scan:
        pos = match.start()
        for number, action in enumerate(actions, 1):
            text = match.group(number)
            if not text:
                continue
            start = match.start(number)
            if start < pos:
                # nested inside a group we've already emitted
                continue
            if start > pos:
                yield pos, Text, match.string[pos:start]
            if action is None:
                yield start, Text, text
            elif type(action) is TokenType:
                yield start, action, text
            else:
                yield from action(lexer, _GroupMatch(start, text))
            pos = start + len(text)
        if pos < match.end():
            yield pos, Text, match.string[pos : match.end()]

    return callback


def using(other, state: str | None = None):
    """Lex the matched text with another lexer.

    ``other`` is a lexer class, a registered language name (looked up
    lazily, which sidesteps import cycles between lexer modules) or ``this``.
    With ``state`` the sub-lexer starts in that state on top of root.
    """
    stack = ("root", state) if state else ("root",)

    def callback(lexer: Lexer, match) -> Scan:
        sub = lexer if other is this else lexer._sublexer(other)
        offset = match.start()
        for pos, ttype, value in sub.scan(match.group(), stack):
            yield offset + pos, ttype, value

    return callback


class Lexer:
    name = ""
    aliases: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    # whole-filename globs for things without a useful extension (Makefile...)
    filenames: tuple[str, ...] = ()
    # regexes matched against the interpreter name of a #! line
    shebangs: tuple[str, ...] = ()

    def __init__(self):
        self._sublexers: dict[object, Lexer] = {}

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r}>"

    @staticmethod
    def analyse(code: str) -> float:
        """How much ``code`` looks like this language, 0 to 1. Used for guessing."""
        return 0.0

    def tokenize(self, code: str) -> Iterator[tuple[TokenType, str]]:
        """Split ``code`` into (token type, text) pairs.

        The texts always concatenate back to exactly ``code``.
        """
        for _, ttype, value in self.scan(code):
            if value:
                yield ttype, value

    def scan(self, code: str, stack: tuple[str, ...] = ("root",)) -> Scan:
        raise NotImplementedError

    def _sublexer(self, other) -> Lexer:
        try:
            return self._sublexers[other]
        except KeyError:
            pass
        if isinstance(other, str):
            from .registry import get_lexer

            sub = get_lexer(other)
        else:
            sub = other()
        self._sublexers[other] = sub
        return sub


class TextLexer(Lexer):
    name = "text"
    aliases = ("txt", "plain", "plaintext")
    extensions = (".txt",)

    def scan(self, code: str, stack: tuple[str, ...] = ("root",)) -> Scan:
        if code:
            yield 0, Text, code


_Rule = tuple[Callable, object, "tuple[str, ...] | None"]

# An empty match that only switches state is fine, but two states bouncing
# off each other that way would never terminate. Past this many in a row we
# give up on the character.
_MAX_STALLED = 64


class RegexLexer(Lexer):
    """Lexer driven by a table of regex rules grouped into states.

    ``tokens`` maps a state name to a list of rules. A rule is
    ``(pattern, action)`` or ``(pattern, action, new_state)``; ``include`` and
    ``default`` entries are also allowed. ``action`` is a token type or a
    callable such as ``bygroups(...)``. ``new_state`` is a state name to push,
    ``"#pop"``, ``"#pop:2"``, ``"#push"``, or a tuple of those applied in order.

    Subclasses inherit states they don't define, and can extend one by
    putting ``inherit`` in their own list for it.
    """

    flags = re.MULTILINE
    tokens: dict[str, list] = {}

    @classmethod
    def _rules(cls) -> dict[str, list[_Rule]]:
        compiled = cls.__dict__.get("_compiled")
        if compiled is None:
            compiled = _compile(cls)
            cls._compiled = compiled
        return compiled

    def scan(self, code: str, stack: tuple[str, ...] = ("root",)) -> Scan:
        rules = self._rules()
        states = list(stack)
        current = rules[states[-1]]
        pos = 0
        end = len(code)
        stalled = 0
        while pos < end:
            for matcher, action, transition in current:
                match = matcher(code, pos)
                if match is None:
                    continue
                if match.end() == pos:
                    if transition is None or stalled >= _MAX_STALLED:
                        continue
                    stalled += 1
                else:
                    stalled = 0
                if action is not None:
                    if type(action) is TokenType:
                        yield pos, action, match.group()
                    else:
                        yield from action(self, match)
                pos = match.end()
                if transition is not None:
                    _apply(states, transition)
                    current = rules[states[-1]]
                break
            else:
                if code[pos] == "\n":
                    # Nothing in this state wants the newline, which usually
                    # means an unterminated string. Start over on the next
                    # line instead of mis-lexing the rest of the file.
                    states = ["root"]
                    current = rules["root"]
                    yield pos, Whitespace, "\n"
                else:
                    yield pos, Error, code[pos]
                pos += 1
                stalled = 0


def _apply(states: list[str], transition: tuple[str, ...]) -> None:
    for step in transition:
        if step == "#push":
            states.append(states[-1])
        elif step.startswith("#pop"):
            count = int(step[5:]) if len(step) > 4 else 1
            # never pop root itself, however unbalanced the input is
            del states[max(1, len(states) - count) :]
        else:
            states.append(step)


def _merged_tokens(cls: type[RegexLexer]) -> dict[str, list]:
    merged: dict[str, list] = {}
    for klass in reversed(cls.__mro__):
        for state, rules in klass.__dict__.get("tokens", {}).items():
            if inherit in rules:
                at = rules.index(inherit)
                rules = rules[:at] + merged.get(state, []) + rules[at + 1 :]
            merged[state] = rules
    return merged


def _compile(cls: type[RegexLexer]) -> dict[str, list[_Rule]]:
    definitions = _merged_tokens(cls)
    if "root" not in definitions:
        raise HighlightError(f"{cls.__name__} has no root state")

    def transition_for(state, where: str) -> tuple[str, ...] | None:
        if state is None:
            return None
        steps = (state,) if isinstance(state, str) else tuple(state)
        for step in steps:
            if step == "#push" or re.fullmatch(r"#pop(:\d+)?", step):
                continue
            if step not in definitions:
                raise HighlightError(
                    f"{cls.__name__}: state {where!r} refers to unknown state {step!r}"
                )
        return steps

    def expand(state: str, seen: tuple[str, ...]) -> list[_Rule]:
        if state in seen:
            chain = " -> ".join(seen + (state,))
            raise HighlightError(f"{cls.__name__}: circular include ({chain})")
        result: list[_Rule] = []
        for rule in definitions[state]:
            if isinstance(rule, include):
                if rule not in definitions:
                    raise HighlightError(
                        f"{cls.__name__}: state {state!r} includes "
                        f"unknown state {str(rule)!r}"
                    )
                result.extend(expand(str(rule), seen + (state,)))
                continue
            if isinstance(rule, default):
                result.append((_EMPTY, None, transition_for(rule.state, state)))
                continue
            pattern, action = rule[0], rule[1]
            try:
                matcher = re.compile(pattern, cls.flags).match
            except re.error as exc:
                raise HighlightError(
                    f"{cls.__name__}: bad pattern {pattern!r} in state {state!r}: {exc}"
                ) from None
            new_state = rule[2] if len(rule) > 2 else None
            result.append((matcher, action, transition_for(new_state, state)))
        return result

    return {state: expand(state, ()) for state in definitions}


_EMPTY = re.compile("").match
