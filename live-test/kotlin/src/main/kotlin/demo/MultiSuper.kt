// Super-method resolution stress file: nine override shapes mixing class-side
// and interface-side supers that declare the same member.
package demo

// Three-way direct supers: Triple overrides name(), which is declared by the
// Base class and by both IRender and IDisplay.
interface IRender {
    fun name(): String
}

interface IDisplay {
    fun name(): String
}

abstract class Base {
    abstract fun name(): String
}

class Triple : Base(), IRender, IDisplay {
    override fun name(): String = "triple"
}

// Deep override chain: Base2 -> Mid1 -> Mid2 -> Leaf.
// Mid2 also implements IComputable so Mid2.m has 2 direct supers (Mid1 + IComputable).
abstract class Base2 {
    abstract fun m(): String
}

interface IComputable {
    fun m(): String
}

open class Mid1 : Base2() {
    override fun m(): String = "mid1"
}

open class Mid2 : Mid1(), IComputable {
    override fun m(): String = "mid2"
}

class Leaf : Mid2() {
    override fun m(): String = "leaf"
}

// Diamond + abstract base: AbstractMethodHolder + Left + Right -> Bottom
abstract class AbstractMethodHolder {
    abstract fun m(): String
}

interface Top {
    fun m(): String
}

interface Left : Top

interface Right : Top

class Bottom : AbstractMethodHolder(), Left, Right {
    override fun m(): String = "bottom"
}

// Default interface method + abstract base + extra interface.
interface Greeter {
    fun greet(): String = "default"
}

interface FriendlyGreeter {
    fun greet(): String = "hi"
}

abstract class AbstractGreeter {
    abstract fun greet(): String
}

class LoudGreeter : AbstractGreeter(), Greeter, FriendlyGreeter {
    override fun greet(): String = "LOUD"
}

// Property override (val) across abstract class + 2 interfaces.
interface Labeled {
    val label: String
}

interface Marked {
    val label: String
}

abstract class AbstractTagged {
    abstract val label: String
}

class Tagged : AbstractTagged(), Labeled, Marked {
    override val label: String = "tag"
}

// Property override (var) across open class + interface.
open class MutableHolder {
    open var holder: String = "init"
}

interface IHolder {
    var holder: String
}

class CustomHolder : MutableHolder(), IHolder {
    override var holder: String = "custom"
        get() = field.uppercase()
        set(value) { field = value.lowercase() }
}

// Sealed class + 2 interfaces declaring the same method.
sealed class Status {
    abstract fun status(): String
}

interface IStatus {
    fun status(): String
}

interface IStateBearer {
    fun status(): String
}

class Active : Status(), IStatus, IStateBearer {
    override fun status(): String = "active"
}

class Inactive : Status(), IStatus, IStateBearer {
    override fun status(): String = "inactive"
}

// Data class implementing 3 interfaces that all declare `name`.
interface Named {
    val name: String
}

interface Identifiable {
    val name: String
}

interface Labelable {
    val name: String
}

data class Point(override val name: String) : Named, Identifiable, Labelable

// Object declaration implementing the same 3 interfaces.
object Singleton : Named, Identifiable, Labelable {
    override val name: String = "singleton"
}
