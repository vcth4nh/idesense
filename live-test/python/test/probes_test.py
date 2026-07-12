# Test half of the scope-discrimination fixtures: test_caller is the caller
# that production-scoped caller queries must exclude, and ProbeTestChild is
# the test-root subclass (scope does not filter subtype listings).
from probes import Probe


def test_caller():
    Probe().target()


class ProbeTestChild(Probe):
    pass
