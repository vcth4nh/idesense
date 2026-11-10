// Operator-function super resolution: Caller's operator invoke must resolve
// to the operator fun declared in Invokable.
package demo

interface Invokable {
    operator fun invoke(): String
}

class Caller : Invokable {
    override operator fun invoke(): String = "called"
}
