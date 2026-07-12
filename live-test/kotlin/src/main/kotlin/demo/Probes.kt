// Production side of the scope-discrimination pair: callers of target() and
// subtypes of Probe are probed under production, test, this-class and
// this-module scopes; the test-only hits live in the test source tree.
package demo

open class Probe {
    fun target(): Int = 42

    // Same-class caller: what a this-class-scoped caller search can see.
    fun sameClassCaller(): Int = target() + 1
}

// Top-level production caller: outside the class, inside production sources.
fun freeProdCaller(): Int = Probe().target()

// Production-side subtype; the test tree adds another so subtype results can
// differ by scope.
class ProbeProdChild : Probe()
