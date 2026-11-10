// Indirect-dispatch fixture: each quirk* function turns a string into an int
// through a different Kotlin idiom, probing navigation through lambdas,
// scope blocks, extensions, sealed dispatch and stored function values.
package demo

// Conversion through a lambda held in a local.
fun quirkLambda(x: String): Int {
    val coerce: (String) -> Int = { it.toInt() }
    return coerce(x)
}

// Conversion through a stored function reference.
fun quirkFunctionRef(x: String): Int {
    val coerce: (String) -> Int = String::toInt
    return coerce(x)
}

// Callees reached through an apply block.
fun quirkApply(x: String): Int {
    return StringBuilder().apply { append(x) }.toString().toInt()
}

// A let block behind a safe call: ground truth — no callees surface.
fun quirkLet(x: String?): Int {
    return x?.let { it.toInt() } ?: 0
}

// A with block: ground truth — no callees surface here either.
fun quirkWith(x: String): Int {
    return with(x) { toInt() }
}

// Conversion through a run block.
fun quirkRun(x: String): Int = x.run { toInt() }

// Extension function: quirkExtensionFn's call site must resolve here.
fun String.coerceTo(default: Int): Int = this.toIntOrNull() ?: default

fun quirkExtensionFn(x: String): Int = x.coerceTo(0)

// Branching dispatch inside a when expression.
fun quirkWhen(mode: String, x: String): Int = when (mode) {
    "int" -> x.toInt()
    "abs" -> Math.abs(x.toInt())
    else -> 0
}

// Sealed hierarchy whose implementers are nested objects: IntCoerce and
// AbsCoerce override apply and are Coercion's only implementations.
sealed class Coercion {
    abstract fun apply(x: String): Int
    object IntCoerce : Coercion() { override fun apply(x: String): Int = x.toInt() }
    object AbsCoerce : Coercion() { override fun apply(x: String): Int = Math.abs(x.toInt()) }
}

// Dynamic dispatch through the sealed base.
fun quirkSealed(c: Coercion, x: String): Int = c.apply(x)

// Data class hosting coerce, the target of qualified symbol lookups.
data class Coercer(val prefix: String) {
    fun coerce(x: String): Int = x.removePrefix(prefix).toInt()
}

// Conversion through a data-class method.
fun quirkDataClass(x: String): Int = Coercer("+").coerce(x)

// Map-of-lambdas dispatch. Ground truth: the callee walk sees inside the
// stored lambda, whose absolute-value call resolves into the JDK.
fun quirkDispatchMap(key: String, x: String): Int {
    val dispatch: Map<String, (String) -> Int> = mapOf(
        "int" to String::toInt,
        "abs" to { s -> Math.abs(s.toInt()) }
    )
    return dispatch[key]?.invoke(x) ?: 0
}

// Infix call site: coerceFirst's definition must resolve from here.
fun quirkInfix(x: String): Int = (x to 0).coerceFirst()

// Infix extension on a pair; its usage is the quirkInfix call above.
infix fun Pair<String, Int>.coerceFirst(): Int = this.first.toIntOrNull() ?: this.second
