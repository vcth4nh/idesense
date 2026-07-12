// Main fixture: the Drawable/Shape hierarchy, a collection and a factory. Most
// navigation probes anchor here, so every declaration, override, call site and
// usage below is a deliberate target.
export interface Drawable {
    draw(): string;
}

// Shape: abstract root; describe() gives the abstract area() a polymorphic call
// site inside the file.
export abstract class Shape {
    abstract area(): number;

    describe(): string {
        return `${this.constructor.name} with area ${this.area()}`;
    }
}

// Circle and Rectangle: area overrides the abstract class side, draw implements
// the interface side; radius, width and height are constructor parameter
// properties, with radius's reads probed.
export class Circle extends Shape implements Drawable {
    constructor(public readonly radius: number) {
        super();
    }
    area(): number { return 3.14159 * this.radius * this.radius; }
    draw(): string { return `circle r=${this.radius}`; }
}

export class Rectangle extends Shape implements Drawable {
    constructor(public readonly width: number, public readonly height: number) {
        super();
    }
    area(): number { return this.width * this.height; }
    draw(): string { return `rect ${this.width}x${this.height}`; }
}

// Square: inherits area rather than overriding — a two-level supertype chain.
// Ground truth: it still counts as an implementation of Drawable via Rectangle.
export class Square extends Rectangle {
    constructor(side: number) {
        super(side, side);
    }
}

// ShapeCollection: totalArea and largest read the shapes field and call area(),
// providing callee chains and field usages.
export class ShapeCollection {
    readonly shapes: Shape[] = [];

    add(shape: Shape): void { this.shapes.push(shape); }

    totalArea(): number {
        let sum = 0;
        for (const s of this.shapes) sum += s.area();
        return sum;
    }

    largest(): Shape | null {
        let best: Shape | null = null;
        for (const s of this.shapes) {
            if (best === null || s.area() > best.area()) best = s;
        }
        return best;
    }
}

// Factory. Ground truth: its call-hierarchy callees are the three constructed
// classes themselves — constructor calls surface as class-kind callees here.
export function makeDefaultShapes(): Shape[] {
    return [new Circle(1.0), new Rectangle(2.0, 3.0), new Square(4.0)];
}
