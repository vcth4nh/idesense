// Scope fixture: callers and subtypes of one class, split across the
// production, test, this-class and this-module search scopes. A test file
// requires Probe and calls/extends it from the test side of the boundary.
'use strict';

// target() is the probed method; sameClassCaller() is its only caller
// inside the class (what "this class" scope returns). Ground truth: the
// "this module" scope spans src and test together, so it filters nothing.
class Probe {
    target() {
        return 42;
    }

    sameClassCaller() {
        return this.target() + 1;
    }
}

// Free-function caller on the production side. Ground truth: its only
// reference is the export list below, which the caller tree reports as a
// single file-level call.
function freeProdCaller() {
    return new Probe().target();
}

// Ground truth: this same-file child is the only subtype ever listed for
// Probe, under every scope -- a test-file class extending the require()d
// Probe never enters WebStorm's stub-based inheritors index.
class ProbeProdChild extends Probe {
}

module.exports = { Probe, freeProdCaller, ProbeProdChild };
