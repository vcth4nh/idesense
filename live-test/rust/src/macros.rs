// Macro and derive fixtures: a macro_rules! definition with expansion sites,
// and a struct whose trait impls are synthesized by #[derive].
// Declarative macro — demo() expands it twice on one line; pins macro-aware
// resolution from use site back to this definition and usages from the
// definition out to the expansion sites.
macro_rules! square {
    ($x:expr) => {
        $x * $x
    };
}

// Ground truth: the derives synthesize Point's impls, so navigation on the
// derived clone() call in demo() resolves into the stdlib trait that declares
// it (snapshotted as a library basename), not into anything in this file.
#[derive(Debug, Clone, PartialEq)]
pub struct Point {
    pub x: i32,
    pub y: i32,
}

impl Point {
    pub fn origin() -> Self {
        Point { x: 0, y: 0 }
    }
}

// Drives the macro and the derived methods so each has in-file use sites.
pub fn demo() -> i32 {
    let p = Point::origin();
    let q = p.clone();
    let _eq = p == q;
    square!(p.x) + square!(q.y)
}
