# Negative fixture: Standalone has no base class, so super lookup on compute
# must return the method with an empty super list — not an error.
"""Standalone class with method that has no super — expected empty hierarchy."""


class Standalone:
    def compute(self) -> str:
        return "standalone"
