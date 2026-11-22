# Fixture of the Python key tests: the uses of the names that models.py defines.
from shop import models
from shop.models import format_receipt_line


def price_twice(leaf):
    # compute_total_price runs two times here.
    first = leaf.compute_total_price(3)
    second = (leaf
              .compute_total_price(4))
    return first + second


def bound(leaf):
    return leaf.compute_total_price


def receipt(items):
    return [format_receipt_line(item) for item in items]


def register(handler):
    return handler


HANDLER = register(handler=format_receipt_line)


def summary(other):
    return getattr(other, "render_summary_text")()


def checkout(**options):
    return options


DISCOUNT = checkout(apply_discount_rate=0.5)


def ship(order, shipping_estimate):
    return order


class Cache:
    def __init__(self):
        self.cache_lookup_key = "fixed"


def weight(leaf):
    return leaf.total_weight + leaf.total_price() + len(leaf.describe())


def stripped(leaf):
    return leaf.removeprefix("x") + str(models.Leaf)
