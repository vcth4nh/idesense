// Baseline navigation fixture: the Shape hierarchy (Circle, Rectangle,
// Square) plus Drawable and ShapeCollection, probed by most tools. Member
// qualified names render as demo.Shape#area — the IDE's Copy Reference form.
package demo

// Drawable gives Circle and Rectangle a second, interface-side parent, so
// draw() supers and implementer lookups run beside the Shape class chain.
interface Drawable {
    fun draw(): String
}

abstract class Shape {
    abstract fun area(): Double

    // Calls area(), so the base class itself appears among area's callers.
    open fun describe(): String = "${this::class.simpleName} with area ${area()}"
}

class Circle(val radius: Double) : Shape(), Drawable {
    override fun area(): Double = 3.14159 * radius * radius
    override fun draw(): String = "circle r=$radius"
}

open class Rectangle(val width: Double, val height: Double) : Shape(), Drawable {
    override fun area(): Double = width * height
    override fun draw(): String = "rect ${width}x$height"
}

// Depth-2 link with no members of its own: Square -> Rectangle -> Shape is
// pure supertype-chain material.
class Square(side: Double) : Rectangle(side, side)

// Caller side of the call hierarchy: totalArea and largest reach area()
// through the shapes list.
class ShapeCollection {
    val shapes: MutableList<Shape> = mutableListOf()

    fun add(shape: Shape) {
        shapes.add(shape)
    }

    fun totalArea(): Double = shapes.sumOf { it.area() }

    fun largest(): Shape? = shapes.maxByOrNull { it.area() }
}

// Ground truth: callees of makeDefaultShapes are empty — Kotlin constructor
// invocations (Circle(...) etc.) do not surface as call-hierarchy callees.
fun makeDefaultShapes(): List<Shape> = listOf(Circle(1.0), Rectangle(2.0, 3.0), Square(4.0))
