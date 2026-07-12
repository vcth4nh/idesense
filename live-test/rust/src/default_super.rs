// Trait method with default body. Struct may override or use default.
// Super on the trait's own default compute() is empty — it is the chain root.
pub trait Computable {
    fn compute(&self) -> String {
        "default".to_string()
    }
}

pub struct Overrider;

// Override: its super resolves to Computable's defaulted declaration.
impl Computable for Overrider {
    fn compute(&self) -> String {
        "overridden".to_string()
    }
}
