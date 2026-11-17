# Fixture of the Python key tests: a class tree, and one name for each rule of the unique-name scan.
import functools


def logged(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


class Base:
    def describe(self):
        return "base"


class Middle(Base):
    pass


class Leaf(Middle):
    def compute_total_price(self, amount):
        return amount * 2

    def removeprefix(self, text):
        return text

    @property
    def total_weight(self):
        return 3

    def total_price(self):
        return 1

    def __fixture_hook__(self):
        return 0


class Other(Base):
    def render_summary_text(self):
        return "summary"

    def apply_discount_rate(self, rate):
        return rate

    def shipping_estimate(self):
        return 5

    def cache_lookup_key(self):
        return "key"


Dynamic = type("Dynamic", (Base,), {})


@logged
def format_receipt_line(item):
    return str(item)


def make_helper():
    def nested_helper_function():
        return 1
    return nested_helper_function()


class Lazy:
    @functools.cached_property
    def lazy_total_amount(self):
        return 7


def make_local_leaf():
    class LocalLeaf(Middle):
        pass

    class LocalTwig(LocalLeaf):
        pass
    return LocalTwig


# At run time each TypedDict class has the bases (dict,); its declared bases are in __orig_bases__.
from typing import Generic, NamedTuple, TypedDict, TypeVar


class BaseRecord(TypedDict):
    key: str


class ChildRecord(BaseRecord):
    size: int


class GrandRecord(ChildRecord, total=False):
    note: str


class ExtraRecord(TypedDict):
    flag: bool


class MergedRecord(BaseRecord, ExtraRecord):
    pass


# A NamedTuple subclass and a Generic subclass are subclasses at run time too.
class Pair(NamedTuple):
    left: int
    right: int


class LabeledPair(Pair):
    pass


Slot = TypeVar("Slot")


class Box(Generic[Slot]):
    pass


class IntBox(Box[int]):
    pass
