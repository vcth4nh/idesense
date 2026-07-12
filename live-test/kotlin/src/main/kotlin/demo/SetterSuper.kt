// Custom-accessor super resolution: WithSetter.value has hand-written get/set
// and must still resolve to the var declared in WithProp.
package demo

interface WithProp {
    var value: String
}

class WithSetter : WithProp {
    override var value: String = "init"
        get() = field
        set(v) { field = v.uppercase() }
}
