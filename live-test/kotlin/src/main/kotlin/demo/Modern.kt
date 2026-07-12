// Multi-family host — five unrelated probe families share this file:
// Counter companion members, the fetchValue/computeTotal suspend pair,
// Printer delegation, the Channel enum, and Plain's toString override.
package demo

// Companion-member definition resolution: create() and DEFAULT_LIMIT live in
// Counter's companion object; useCounter below holds their call sites.
class Counter {
    private var n = 0
    fun increment() { n++ }
    fun value(): Int = n

    companion object {
        const val DEFAULT_LIMIT = 100
        fun create(): Counter = Counter()
    }
}

// Suspend pair: computeTotal calls fetchValue twice, so callee walks and
// definition lookups both get exercised on suspend functions.
suspend fun fetchValue(): Int = 42

suspend fun computeTotal(): Int {
    val a = fetchValue()
    val b = fetchValue()
    return a + b
}

// Call sites for the companion members above: definition lookups on
// Counter.create() and Counter.DEFAULT_LIMIT must land inside the companion.
fun useCounter(): Int {
    val c = Counter.create()
    c.increment()
    return Counter.DEFAULT_LIMIT + c.value()
}

// Implementation via delegation: DelegatingPrinter implements Printer by
// delegating to p, and must still show up as an implementer / subtype of
// Printer alongside RealPrinter.
interface Printer {
    fun print(): String
}

class RealPrinter : Printer {
    override fun print(): String = "real"
}

class DelegatingPrinter(private val p: Printer) : Printer by p

// Enum supertype resolution: Channel's supertypes live in the Kotlin standard
// library, so hierarchy walks land in library stubs, not project files.
enum class Channel { ALPHA, BETA }

// Library super: Plain.toString overrides a method whose super lives in the
// standard library — there is no project-side super to find.
class Plain {
    override fun toString(): String = "plain"
}
