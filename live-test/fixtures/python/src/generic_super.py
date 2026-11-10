# Super-method fixture: Repo.find must resolve to BaseRepo.find through the
# parameterized base BaseRepo[T] — generics must not hide the override edge.
"""Generic[T] class with overridden method."""
from typing import Generic, TypeVar

T = TypeVar("T")


class BaseRepo(Generic[T]):
    def find(self, id: int) -> T:
        raise NotImplementedError


class Repo(BaseRepo[T], Generic[T]):
    def find(self, id: int) -> T:
        raise NotImplementedError
