// Baseline fixture: the Shape trait family (Circle, Rectangle, Square), the
// Drawable side trait, and the ShapeCollection aggregator — main host for
// definition, usages, hierarchy, and implementations probes.
// Drawable is implemented by Circle and Rectangle but never called, so
// caller queries on draw() pin an empty result.
pub trait Drawable {
    fn draw(&self) -> String;
}

// Shape: abstract area() plus describe() with a default body that calls
// area() — so the trait itself contributes a caller of area().
pub trait Shape {
    fn area(&self) -> f64;

    fn describe(&self) -> String {
        format!("Shape with area {}", self.area())
    }
}

// Circle and Rectangle implement both traits and override the defaulted
// describe(); each override calls area() through self.
pub struct Circle {
    pub radius: f64,
}

impl Shape for Circle {
    fn area(&self) -> f64 {
        3.14159 * self.radius * self.radius
    }

    fn describe(&self) -> String {
        format!("Circle with area {}", self.area())
    }
}

impl Drawable for Circle {
    fn draw(&self) -> String {
        format!("circle r={}", self.radius)
    }
}

pub struct Rectangle {
    pub width: f64,
    pub height: f64,
}

impl Shape for Rectangle {
    fn area(&self) -> f64 {
        self.width * self.height
    }

    fn describe(&self) -> String {
        format!("Rectangle with area {}", self.area())
    }
}

impl Drawable for Rectangle {
    fn draw(&self) -> String {
        format!("rect {}x{}", self.width, self.height)
    }
}

// Square implements only Shape, keeps the default describe(), and delegates
// area() to a composed Rectangle.
pub struct Square {
    inner: Rectangle,
}

impl Square {
    pub fn new(side: f64) -> Self {
        Square { inner: Rectangle { width: side, height: side } }
    }
}

impl Shape for Square {
    fn area(&self) -> f64 {
        self.inner.area()
    }
}

// Aggregator over boxed trait objects: total_area() and largest() funnel
// every stored shape through area() via dynamic dispatch.
pub struct ShapeCollection {
    pub shapes: Vec<Box<dyn Shape>>,
}

impl ShapeCollection {
    pub fn new() -> Self {
        ShapeCollection { shapes: Vec::new() }
    }

    pub fn add(&mut self, shape: Box<dyn Shape>) {
        self.shapes.push(shape);
    }

    pub fn total_area(&self) -> f64 {
        self.shapes.iter().map(|s| s.area()).sum()
    }

    pub fn largest(&self) -> Option<&Box<dyn Shape>> {
        self.shapes.iter().max_by(|a, b| {
            a.area().partial_cmp(&b.area()).unwrap()
        })
    }
}

// Free factory building one of each shape — root for callee-direction call
// hierarchy walks.
pub fn make_default_shapes() -> Vec<Box<dyn Shape>> {
    vec![
        Box::new(Circle { radius: 1.0 }),
        Box::new(Rectangle { width: 2.0, height: 3.0 }),
        Box::new(Square::new(4.0)),
    ]
}
