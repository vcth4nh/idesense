// Primary navigation fixture: the Shape hierarchy (Circle, Rectangle,
// Square), an unrelated Drawable root, the ShapeCollection aggregate, and
// the makeDefaultShapes factory. Most probes anchor in this file.
'use strict';

// Deliberately unrelated root: nothing extends Drawable, so a search for
// implementations of its draw() finds none; the like-named draw methods
// further down do not count (WebStorm follows extends edges, not names).
class Drawable {
    draw() { throw new Error('not implemented'); }
}

// Hierarchy root. area() throws as a stand-in for abstract; describe()
// calls this.area(), so the base method has an in-class caller.
class Shape {
    area() { throw new Error('abstract'); }
    describe() { return `${this.constructor.name} with area ${this.area()}`; }
}

// Concrete subclasses. area() overrides Shape.area; draw() is new here --
// no super, despite Drawable's like-named method. Constructor call sites
// live in makeDefaultShapes and, for Circle, in a separate consumer file.
class Circle extends Shape {
    constructor(radius) {
        super();
        this.radius = radius;
    }
    area() { return 3.14159 * this.radius * this.radius; }
    draw() { return `circle r=${this.radius}`; }
}

class Rectangle extends Shape {
    constructor(width, height) {
        super();
        this.width = width;
        this.height = height;
    }
    area() { return this.width * this.height; }
    draw() { return `rect ${this.width}x${this.height}`; }
}

// Grandchild with no overrides of its own: lookups on Square walk up
// through Rectangle to Shape.
class Square extends Rectangle {
    constructor(side) {
        super(side, side);
    }
}

// Aggregate host: totalArea() and largest() iterate this.shapes and call
// area(), providing cross-class callers for the hierarchy above.
class ShapeCollection {
    constructor() {
        this.shapes = [];
    }
    add(shape) { this.shapes.push(shape); }
    totalArea() {
        let sum = 0;
        for (const s of this.shapes) sum += s.area();
        return sum;
    }
    largest() {
        let best = null;
        for (const s of this.shapes) {
            if (best === null || s.area() > best.area()) best = s;
        }
        return best;
    }
}

// Factory whose new-expressions are the shapes' constructor call sites.
// Ground truth: the callee hierarchy lists them as CLASS nodes (Circle,
// Rectangle, Square), not as constructor methods.
function makeDefaultShapes() {
    return [new Circle(1.0), new Rectangle(2.0, 3.0), new Square(4.0)];
}

module.exports = { Drawable, Shape, Circle, Rectangle, Square, ShapeCollection, makeDefaultShapes };
