package demo

class Counter {
    private var n = 0
    fun increment() { n++ }
    fun value(): Int = n

    companion object {
        const val DEFAULT_LIMIT = 100
        fun create(): Counter = Counter()
    }
}

suspend fun fetchValue(): Int = 42

suspend fun computeTotal(): Int {
    val a = fetchValue()
    val b = fetchValue()
    return a + b
}

fun useCounter(): Int {
    val c = Counter.create()
    c.increment()
    return Counter.DEFAULT_LIMIT + c.value()
}

interface Printer {
    fun print(): String
}

class RealPrinter : Printer {
    override fun print(): String = "real"
}

class DelegatingPrinter(private val p: Printer) : Printer by p

enum class Channel { ALPHA, BETA }

class Plain {
    override fun toString(): String = "plain"
}
