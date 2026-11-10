# Multi-super families: each block below gives one bottom override several
# supers at once, and super lookups return the full transitive set, not just
# the immediate parent.
"""Multi-super fixture: one method overrides three abstract supers at once."""
from abc import ABC, abstractmethod
from typing import Protocol


# Triple inherits three abstract bases that each declare name, so one
# override answers to all three at once. With the caret on the class name
# itself rather than the method, super lookup returns the base classes
# as classes.
class IRender(ABC):
    @abstractmethod
    def name(self) -> str:
        ...


class IDisplay(ABC):
    @abstractmethod
    def name(self) -> str:
        ...


class Base(ABC):
    @abstractmethod
    def name(self) -> str:
        ...


class Triple(Base, IRender, IDisplay):
    def name(self) -> str:
        return "triple"


# Deep override chain: DeepBase -> DeepMid1 -> DeepMid2 -> DeepLeaf, with
# IRunnable joining at DeepMid2. DeepMid2.m has direct supers DeepMid1.m and
# IRunnable.m plus transitive DeepBase.m; DeepLeaf.m pins the whole chain.
class IRunnable(ABC):
    @abstractmethod
    def m(self) -> str:
        ...


class DeepBase(ABC):
    @abstractmethod
    def m(self) -> str:
        ...


class DeepMid1(DeepBase):
    def m(self) -> str:
        return "mid1"


class DeepMid2(DeepMid1, IRunnable):
    def m(self) -> str:
        return "mid2"


class DeepLeaf(DeepMid2):
    def m(self) -> str:
        return "leaf"


# Diamond: DiamondTop fans out to DiamondLeft/DiamondRight/DiamondCenter and
# rejoins at DiamondBottom. Super lookup on DiamondBottom.m lists the shared
# apex once plus all three mid overrides; the supertypes view expands each
# base branch and shows DiamondTop under every one of them.
class DiamondTop(ABC):
    @abstractmethod
    def m(self) -> str:
        ...


class DiamondLeft(DiamondTop):
    def m(self) -> str:
        return "left"


class DiamondRight(DiamondTop):
    def m(self) -> str:
        return "right"


class DiamondCenter(DiamondTop):
    def m(self) -> str:
        return "center"


class DiamondBottom(DiamondLeft, DiamondRight, DiamondCenter):
    def m(self) -> str:
        return "bottom"


# Protocol/ABC mix: ConcreteShape lists CanvasProto as an explicit base, so
# CanvasProto.draw counts as a super alongside AbstractDrawable.draw.
# DrawableProto matches only structurally and must NOT appear.
class DrawableProto(Protocol):
    def draw(self) -> str:
        ...


class CanvasProto(Protocol):
    def draw(self) -> str:
        ...


class AbstractDrawable(ABC):
    @abstractmethod
    def draw(self) -> str:
        ...


class ConcreteShape(AbstractDrawable, CanvasProto):
    def draw(self) -> str:
        return "shape"


# Plain multiple inheritance: MixedClass.log overrides three concrete
# (non-abstract) methods at once.
class LogBase:
    def log(self, x: object) -> None:
        print(x)


class LoggingMixin:
    def log(self, x: object) -> None:
        print(x)


class ExtraLogger:
    def log(self, x: object) -> None:
        print(x)


class MixedClass(LogBase, LoggingMixin, ExtraLogger):
    def log(self, x: object) -> None:
        print(f"mixed: {x}")


# Property variant: PropDerived.value overrides three @property getters.
class PropBase:
    @property
    def value(self) -> int:
        return 0


class ValueA:
    @property
    def value(self) -> int:
        return 1


class ValueB:
    @property
    def value(self) -> int:
        return 2


class PropDerived(PropBase, ValueA, ValueB):
    @property
    def value(self) -> int:
        return 3


# classmethod variant: FactoryDerived.factory overrides three classmethods.
class FactoryBase:
    @classmethod
    def factory(cls) -> "FactoryBase":
        return cls()


class FactoryAlt:
    @classmethod
    def factory(cls) -> "FactoryAlt":
        return cls()


class FactoryExtra:
    @classmethod
    def factory(cls) -> "FactoryExtra":
        return cls()


class FactoryDerived(FactoryBase, FactoryAlt, FactoryExtra):
    @classmethod
    def factory(cls) -> "FactoryBase":
        return cls()


# staticmethod variant: StaticDerived.helper overrides three staticmethods.
class StaticBase:
    @staticmethod
    def helper() -> str:
        return "base"


class StaticAlt:
    @staticmethod
    def helper() -> str:
        return "alt"


class StaticExtra:
    @staticmethod
    def helper() -> str:
        return "extra"


class StaticDerived(StaticBase, StaticAlt, StaticExtra):
    @staticmethod
    def helper() -> str:
        return "derived"
