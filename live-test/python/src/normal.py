# Primary fixture: a small, deliberately unsurprising class family that most
# navigation probes anchor to — definitions, usages, hierarchies,
# implementations, supers, and call trees all have targets here.
"""Vanilla OOP patterns for the live MCP test harness."""
from abc import ABC, abstractmethod
from typing import Protocol


# Drawable is a typing.Protocol: Circle and Rectangle satisfy it structurally,
# never nominally. PyCharm has no nominal implementer set for structural
# protocols, so implementations and usages of Drawable come back EMPTY, its
# type hierarchy is empty, and super lookup on the draw overrides finds
# nothing — all correct, not tool failures.
class Drawable(Protocol):
    def draw(self) -> str: ...


# Root of the nominal hierarchy. Callers of area are polymorphic call sites
# (describe, total_area, largest), and the same three land on the Circle
# override too — caller resolution follows overrides, not just the base.
# describe is deliberately never overridden and never called, pinning empty
# implementation and caller results.
class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        ...

    def describe(self) -> str:
        return f"{type(self).__name__} with area {self.area()}"


class Circle(Shape):
    def __init__(self, radius: float) -> None:
        self.radius = radius

    def area(self) -> float:
        return 3.14159 * self.radius * self.radius

    def draw(self) -> str:
        return f"circle r={self.radius}"


class Rectangle(Shape):
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height

    def area(self) -> float:
        return self.width * self.height

    def draw(self) -> str:
        return f"rect {self.width}x{self.height}"


# Overrides only __init__; its super chain reaches Rectangle.__init__ plus
# the builtin base initializer. Constructor CALLS resolve to __init__ methods:
# Circle(1.0) lands on Circle.__init__, and super() on the builtin super stub.
class Square(Rectangle):
    def __init__(self, side: float) -> None:
        super().__init__(side, side)


# Call-tree host: total_area's callees mix project code (area) with builtin
# stubs (sum); largest attributes only the max overloads, since its area call
# sits in a key lambda. add is deliberately never called: empty caller tree.
class ShapeCollection:
    def __init__(self) -> None:
        self.shapes: list[Shape] = []

    def add(self, shape: Shape) -> None:
        self.shapes.append(shape)

    def total_area(self) -> float:
        return sum(s.area() for s in self.shapes)

    def largest(self) -> Shape | None:
        if not self.shapes:
            return None
        return max(self.shapes, key=lambda s: s.area())


# Free-function anchor: its callees surface the shape constructors as
# __init__ calls; nothing calls it.
def make_default_shapes() -> list[Shape]:
    return [Circle(1.0), Rectangle(2.0, 3.0), Square(4.0)]
