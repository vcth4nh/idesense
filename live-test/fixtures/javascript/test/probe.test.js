// Test-side half of the scope fixture: ProbeTest.testCaller() calls into
// the required Probe from test scope, and ProbeTestChild extends it across
// the CommonJS module boundary (see the ground-truth note below).
'use strict';

const { Probe } = require('../src/probes');

class ProbeTest {
    testCaller() {
        return new Probe().target();
    }
}

// ProbeTestChild's `extends Probe` resolves (Supertypes of ProbeTestChild -> Probe), but
// WebStorm's stub-based inheritors index does not surface a cross-file child that extends a
// require()-imported base, so it is absent from Subtypes of Probe -- verified against
// WebStorm's own Type Hierarchy widget. Faithful IDE behaviour, not a fixture bug; this is
// why subtype queries on the base bless to 1 subtype (vs 2 for Python/PHP/TS).
class ProbeTestChild extends Probe {
}

module.exports = { ProbeTest, ProbeTestChild };
