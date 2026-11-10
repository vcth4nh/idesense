# Every sink below is a builtin (int, abs, float), so definition lookups land
# in the stdlib stubs: the int class from a plain mention, int.__new__ when
# resolving a call through an alias. Usages of int sweep the whole project.
"""Language-quirk patterns for the live MCP test harness.

Each function exercises a Python-specific indirection or rebinding pattern.
The target functions are deliberately neutral — the patterns themselves are
what the navigation tools must resolve.
"""
import functools
import operator


# Name rebinding: fn aliases the builtin; resolving the fn(x) call chases the
# alias into the builtin constructor, not to the assignment line.
def quirk_name_rebinding(x: str) -> int:
    fn = int
    return fn(x)


# getattr dispatch off a module object.
def quirk_getattr_module(name: str) -> int:
    fn = getattr(operator, "abs")
    return fn(int(name))


# functools.partial wrapper.
def quirk_functools_partial(x: str) -> int:
    coerce = functools.partial(int)
    return coerce(x)


# Dict-literal dispatch table.
def quirk_dict_dispatch(key: str, x: str) -> int:
    dispatch = {"int": int, "abs": lambda v: abs(int(v))}
    return dispatch[key](x)


# Lambda wrapper around the sink.
def quirk_lambda_wrap(x: str) -> int:
    coerce = lambda v: int(v)
    return coerce(x)


# List-indexed dispatch.
def quirk_list_indexing(x: str) -> int:
    funcs = [int, str, float]
    return funcs[0](x)


# Conditional-expression selection.
def quirk_conditional_expr(x: str, use_int: bool) -> int | float:
    fn = int if use_int else float
    return fn(x)


# Import alias: usages of a count the import line itself (as an import-type
# usage) plus the call site.
def quirk_star_import_simulation(x: str) -> int:
    from operator import abs as a
    return a(int(x))


# Decorator wrapping: the sink goes through a locally defined decorator.
def quirk_decorator_wrap(x: str) -> int:
    def with_logging(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper
    wrapped = with_logging(int)
    return wrapped(x)


# Function-local class: Coercer and its coerce method exist only inside this
# function, pinning resolution and usages of local-scope symbols.
def quirk_class_method(x: str) -> int:
    class Coercer:
        def coerce(self, raw: str) -> int:
            return int(raw)
    return Coercer().coerce(x)


# Walrus operator: result is bound inside the condition it is tested in.
def quirk_walrus(x: str) -> int:
    if (result := int(x)):
        return result
    return 0


# Starred-unpacking rebind.
def quirk_unpacking(x: str) -> int:
    fn, *_ = [int, float]
    return fn(x)


# Nested function returning the sink; get_coercer resolves to the local def.
def quirk_nested_return(x: str) -> int:
    def get_coercer():
        return int
    return get_coercer()(x)


# Higher-order map.
def quirk_map_filter(items: list[str]) -> list[int]:
    return list(map(int, items))


# functools.reduce with a lambda.
def quirk_reduce(values: list[str]) -> int:
    return functools.reduce(lambda acc, v: acc + int(v), values, 0)


# Chained getattr through __call__.
def quirk_chained_getattr(x: str) -> int:
    fn = getattr(getattr(operator, "abs"), "__call__")
    return fn(int(x))


# Chained assignment: a and b bind the same builtin; resolving the b(x) call
# also lands in the builtin constructor.
def quirk_multiple_assignment(x: str) -> int:
    a = b = int
    return a(x) + b(x)


# Branch-bound variable: kind resolves to the first branch assignment, and
# its usages gather all three assignments plus the return read.
def classify_shape(s):
    """Issue #11: variable-assign in if/else for find_usages coverage."""
    from .normal import Circle, Rectangle
    if isinstance(s, Circle):
        kind = 1
    elif isinstance(s, Rectangle):
        kind = 2
    else:
        kind = 0
    return kind
