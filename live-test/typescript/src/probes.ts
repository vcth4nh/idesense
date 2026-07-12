// Scope fixture, production side: Probe.target is queried under different scope
// filters; its callers and subclasses are split between this file and the test
// tree so production and test scopes select different sets.
export class Probe {
    target(): number {
        return 42;
    }

    // Same-class caller — the only caller visible under this-class scope.
    sameClassCaller(): number {
        return this.target() + 1;
    }
}

// Free-function caller: completes the production-scope caller set.
export function freeProdCaller(): number {
    return new Probe().target();
}

// Production-side subclass. Ground truth: subtype queries ignore the
// production/test scope filter — the test-side subclass is listed even under
// production scope.
export class ProbeProdChild extends Probe {
}
