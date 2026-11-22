# Fixture of the Python key tests: a module that fails to import, because its dependency is absent.
import absent_dependency_of_the_fixture
from shop.models import Base


class ExtraLeaf(Base):
    pass
