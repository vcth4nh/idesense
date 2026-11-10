# Production half of the scope-discrimination fixtures; a twin in the test
# root adds the test-side caller and subclass. Scoped caller queries on
# target must discriminate: production keeps same_class_caller plus
# free_prod_caller, test keeps only the test-side caller, class scope only
# same_class_caller. Module scope does NOT narrow (the test caller still
# appears), and type-hierarchy scope is a no-op: both subclasses always show.
class Probe:
    def target(self):
        return 42

    def same_class_caller(self):
        return self.target() + 1


# Module-level production caller of target.
def free_prod_caller():
    return Probe().target()


# Production-side subclass.
class ProbeProdChild(Probe):
    pass
