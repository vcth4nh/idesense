// Test-source side of the scope-discrimination pair: testCaller and
// ProbeTestChild give the production probe class a caller and a subtype that
// only test-inclusive search scopes should surface.
package demo

class ProbeTest {
    fun testCaller() {
        Probe().target()
    }
}

class ProbeTestChild : Probe()
