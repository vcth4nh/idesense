// Generic super resolution: Repo<T>.find must resolve to BaseRepo<T>.find
// through the type-parameter substitution.
package demo

abstract class BaseRepo<T> {
    abstract fun find(id: Int): T
}

class Repo<T> : BaseRepo<T>() {
    override fun find(id: Int): T {
        throw NotImplementedError()
    }
}
