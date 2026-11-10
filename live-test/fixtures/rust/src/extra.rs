// Auxiliary navigation targets: a nested module for cross-module definition
// lookups, plus a function whose body resolves into a sibling file of this
// crate for the cross-file case.
pub mod inner {
    pub fn nested_helper() -> i32 { 42 }
    // Marker exists only to be found by class search; it has no uses.
    pub struct Marker;
}

// Symbol-search target; its body is the cross-module definition anchor.
pub fn extra_function(s: &str) -> i32 {
    inner::nested_helper() + s.len() as i32
}

// Cross-file anchor: the struct literal here is declared in a sibling module,
// so definition lookup must leave this file.
pub fn use_quirks_circle() -> f64 {
    crate::normal::Circle { radius: 1.0 }.radius
}
