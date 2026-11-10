// Inherent impl (no trait) — fn has no super in any trait.
// Ground truth: the super-method result for foo() is EMPTY — correct, and it
// matches the gutter, which shows no marker on an inherent method. RustRover's
// raw go-to-super action instead jumps to the enclosing module declaration;
// that is module noise the provider filters out, not a missing super.
pub struct Inherent;

impl Inherent {
    pub fn foo(&self) -> String {
        "inherent".to_string()
    }
}
