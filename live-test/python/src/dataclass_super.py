# Super/usage fixtures on @dataclass classes: ChildDC.__post_init__ must
# resolve its super in ParentDC, and navigation must see through the
# decorator-generated code.
"""Dataclass __post_init__ override across base/derived."""
from dataclasses import dataclass


# Usages of the name field include the annotation line itself plus both
# sides of the assignment in __post_init__ — all reported as plain references.
@dataclass
class ParentDC:
    name: str

    def __post_init__(self) -> None:
        self.name = self.name.lower()


@dataclass
class ChildDC(ParentDC):
    extra: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.extra = self.extra.upper()
