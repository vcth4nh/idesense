// Companion-hosted super resolution: overrides that live inside a companion
// object must still resolve to the interfaces the companion implements —
// a function (make) and a property (KIND).
package demo

interface CompFactory {
    fun make(): String
}

interface KindBearer {
    val KIND: String
}

// CompParent and CompChild each declare their own companion implementing the
// same two interfaces. Companions are not inherited, so the child companion's
// overrides resolve to CompFactory / KindBearer, not to the parent companion.
abstract class CompParent {
    companion object : CompFactory, KindBearer {
        override fun make(): String = "parent"
        override val KIND: String = "parent"
    }
}

class CompChild : CompParent() {
    companion object : CompFactory, KindBearer {
        override fun make(): String = "child"
        override val KIND: String = "child"
    }
}
