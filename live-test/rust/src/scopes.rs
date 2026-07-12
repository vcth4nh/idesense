// Scope fixtures: callers of Probe::target() sit in three places — the same
// impl block, a free production function, and a #[cfg(test)] module — giving
// scope-filtered queries material to include or drop.
pub struct Probe;

impl Probe {
    // Ground truth: every caller-scope variant on target() returns the same
    // three callers — RustRover ignores the call-hierarchy scope parameter
    // (pinned deliberately).
    pub fn target(&self) -> i32 {
        42
    }

    pub fn same_class_caller(&self) -> i32 {
        self.target() + 1
    }
}

pub fn free_prod_caller() -> i32 {
    Probe.target()
}

// Ground truth: a #[cfg(test)] module in src/ is still production-classified —
// usages of target() restricted to the test-files scope come back empty,
// because test-ness keys off Cargo source roots, not cfg attributes.
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_caller() {
        assert_eq!(Probe.target(), 42);
    }
}
