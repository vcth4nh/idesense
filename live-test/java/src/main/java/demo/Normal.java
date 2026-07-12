// Core fixture: a small shape hierarchy anchoring most definition, usage, and
// hierarchy probes for this language. The warnings this file produces are
// pinned as the warning level diagnostics baseline.
package demo;

import java.util.ArrayList;
import java.util.List;

// Drawable plus the abstract Shape base give each concrete shape two parents:
// an interface method to implement and an abstract method to override.
interface Drawable {
    String draw();
}

abstract class Shape {
    // Symbol search collapses overrides onto this topmost declaration; the
    // subclass versions are not listed separately.
    abstract double area();

    String describe() {
        return getClass().getSimpleName() + " with area " + area();
    }
}

class Circle extends Shape implements Drawable {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return 3.14159 * radius * radius;
    }

    @Override
    public String draw() {
        return "circle r=" + radius;
    }
}

class Rectangle extends Shape implements Drawable {
    protected final double width;
    protected final double height;

    Rectangle(double width, double height) {
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }

    @Override
    public String draw() {
        return "rect " + width + "x" + height;
    }
}

// A second level of extension, so upward hierarchy walks have depth two and
// the base class has both direct and indirect subtypes.
class Square extends Rectangle {
    Square(double side) {
        super(side, side);
    }
}

// Gives the area method a fan of callers: totalArea() and largest() both
// call it through the base type.
class ShapeCollection {
    private final List<Shape> shapes = new ArrayList<>();

    void add(Shape shape) {
        shapes.add(shape);
    }

    double totalArea() {
        double sum = 0;
        for (Shape s : shapes) {
            sum += s.area();
        }
        return sum;
    }

    Shape largest() {
        Shape best = null;
        for (Shape s : shapes) {
            if (best == null || s.area() > best.area()) best = s;
        }
        return best;
    }
}

public class Normal {
    // Builds one of each shape. Ground truth: in Java these constructor calls
    // do surface as outgoing calls in the call tree of this method.
    public static List<Shape> makeDefaultShapes() {
        List<Shape> shapes = new ArrayList<>();
        shapes.add(new Circle(1.0));
        shapes.add(new Rectangle(2.0, 3.0));
        shapes.add(new Square(4.0));
        return shapes;
    }

    /** Issue #11: variable-assign in if/else for find_usages coverage. */
    static int classifyShape(Shape s) {
        int kind;
        if (s instanceof Circle) {
            kind = 1;
        } else if (s instanceof Rectangle) {
            kind = 2;
        } else {
            kind = 0;
        }
        return kind;
    }
}
