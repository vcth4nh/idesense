# Fixture of the Python key tests: tests that call the methods of the shop package.
from shop.models import Leaf, format_receipt_line
from shop.service import price_twice, receipt


def test_price_direct():
    assert Leaf().compute_total_price(2) == 4


def test_price_through_service():
    assert price_twice(Leaf()) == 14


def test_receipt():
    assert format_receipt_line(5) == "5"
    assert receipt([1]) == ["1"]


def test_price_with_windows_paths():
    # A test of a product can replace os.path; the trace plugin must keep its own path functions.
    import ntpath
    import os
    saved = os.path
    os.path = ntpath
    try:
        assert Leaf().compute_total_price(1) == 2
    finally:
        os.path = saved


def test_lazy_property():
    from shop.models import Lazy
    assert Lazy().lazy_total_amount == 7
