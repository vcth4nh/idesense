# Super-method fixture for property setters: with the anchor on WithSetter's
# value setter, the super resolves to WithSetterBase's setter — the paired
# getter overload is not the answer.
"""Setter override across base/derived class hierarchy."""


class WithSetterBase:
    @property
    def value(self) -> str:
        return "base"

    @value.setter
    def value(self, v: str) -> None:
        pass


class WithSetter(WithSetterBase):
    @property
    def value(self) -> str:
        return "derived"

    @value.setter
    def value(self, v: str) -> None:
        pass
