// Integration test crate: lives under tests/, which Cargo's standard layout
// marks as a test-source root (intellij-rust: CargoConstants.ProjectLayout.tests).
// TestShape implements the library crate's Shape trait, so it appears as a
// Shape subtype under the default, "all", and "test" hierarchy scopes —
// production is the one scope that filters it out, per the pinned snapshots.
// Type hierarchy honors scope here, unlike call hierarchy (a Rust no-op).
use live_test_rust::normal::Shape;

struct TestShape;

impl Shape for TestShape {
    fn area(&self) -> f64 {
        0.0
    }
}

// Calling TestShape's area() from a test adds a test-file caller to the
// method's call-hierarchy result.
#[test]
fn uses_test_shape() {
    assert_eq!(TestShape.area(), 0.0);
}
