// Scope-discrimination fixture, test side: hosts a test-source caller and a
// test-source subtype of the production probe class, so test-scoped results
// differ from production-scoped ones.
package demo;

class ProbeTest {
    void testCaller() {
        new Probe().target();
    }
}

// Test-side subtype: listed only when hierarchy scope includes test sources.
class ProbeTestChild extends Probe {
}
