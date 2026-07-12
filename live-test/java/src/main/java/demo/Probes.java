// Scope-discrimination fixture, production side: Probe.target() has callers
// and a subtype in production sources here, with counterparts in the test
// source root, so scoped queries split results by production, test, or class.
package demo;

class Probe {
    int target() {
        return 42;
    }

    int sameClassCaller() {
        return target() + 1;
    }
}

// A caller outside Probe, separating same-class callers from the rest of
// production.
class ProbeAux {
    static int freeProdCaller() {
        return new Probe().target();
    }
}

// Production-side subtype; its counterpart lives in the test source root.
class ProbeProdChild extends Probe {
}
