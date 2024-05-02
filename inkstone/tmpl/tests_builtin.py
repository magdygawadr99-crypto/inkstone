from __future__ import annotations

import operator
import re
from collections.abc import Mapping
from typing import Any, Callable

from .runtime import Undefined, pass_environment

# The functions behind `x is something`. Not called test_* so that nobody's
# pytest run tries to collect them.


def is_defined(value: Any) -> bool:
    return not isinstance(value, Undefined)


def is_undefined(value: Any) -> bool:
    return isinstance(value, Undefined)


def is_none(value: Any) -> bool:
    return value is None


def is_boolean(value: Any) -> bool:
    return value is True or value is False


def is_true(value: Any) -> bool:
    return value is True


def is_false(value: Any) -> bool:
    return value is False


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_float(value: Any) -> bool:
    return isinstance(value, float)


def is_number(value: Any) -> bool:
    # bool is an int to Python, but `true is number` would surprise people
    return isinstance(value, (int, float, complex)) and not isinstance(value, bool)


def is_string(value: Any) -> bool:
    return isinstance(value, str)


def is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def is_sequence(value: Any) -> bool:
    """Something with a length and indexes; strings count, like in Jinja."""
    if isinstance(value, Undefined):
        return False
    try:
        len(value)
        value.__getitem__
    except Exception:
        return False
    return True


def is_iterable(value: Any) -> bool:
    if isinstance(value, Undefined):
        return False
    try:
        iter(value)
    except TypeError:
        return False
    return True


def is_callable(value: Any) -> bool:
    # Undefined has a __call__, but only to complain
    return callable(value) and not isinstance(value, Undefined)


def is_sameas(value: Any, other: Any) -> bool:
    return value is other


def is_escaped(value: Any) -> bool:
    return hasattr(value, "__html__")


def is_even(value: int) -> bool:
    return value % 2 == 0


def is_odd(value: int) -> bool:
    return value % 2 == 1


def is_divisibleby(value: int, num: int) -> bool:
    return value % num == 0


def is_lower(value: Any) -> bool:
    return str(value).islower()


def is_upper(value: Any) -> bool:
    return str(value).isupper()


def is_in(value: Any, container: Any) -> bool:
    return value in container


def is_startingwith(value: Any, prefix: str | tuple[str, ...]) -> bool:
    return str(value).startswith(prefix)


def is_endingwith(value: Any, suffix: str | tuple[str, ...]) -> bool:
    return str(value).endswith(suffix)


def is_containing(value: Any, item: Any) -> bool:
    return item in value


def is_matching(value: Any, pattern: str) -> bool:
    """True if the regular expression matches anywhere in the value."""
    return re.search(pattern, str(value)) is not None


@pass_environment
def is_filter(env, value: Any) -> bool:
    return value in env.filters


@pass_environment
def is_test(env, value: Any) -> bool:
    return value in env.tests


TESTS: dict[str, Callable[..., bool]] = {
    "defined": is_defined,
    "undefined": is_undefined,
    "none": is_none,
    "boolean": is_boolean,
    "true": is_true,
    "false": is_false,
    "integer": is_integer,
    "float": is_float,
    "number": is_number,
    "string": is_string,
    "mapping": is_mapping,
    "sequence": is_sequence,
    "iterable": is_iterable,
    "callable": is_callable,
    "sameas": is_sameas,
    "escaped": is_escaped,
    "even": is_even,
    "odd": is_odd,
    "divisibleby": is_divisibleby,
    "lower": is_lower,
    "upper": is_upper,
    "in": is_in,
    "startingwith": is_startingwith,
    "endingwith": is_endingwith,
    "containing": is_containing,
    "matching": is_matching,
    "filter": is_filter,
    "test": is_test,
    "eq": operator.eq,
    "==": operator.eq,
    "equalto": operator.eq,
    "ne": operator.ne,
    "!=": operator.ne,
    "lt": operator.lt,
    "<": operator.lt,
    "lessthan": operator.lt,
    "le": operator.le,
    "<=": operator.le,
    "gt": operator.gt,
    ">": operator.gt,
    "greaterthan": operator.gt,
    "ge": operator.ge,
    ">=": operator.ge,
}
