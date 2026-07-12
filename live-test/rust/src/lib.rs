// Crate root of the Rust live-test fixture: wires every fixture module into
// one library crate so the IDE indexes them together.
pub mod normal;
pub mod quirks;
pub mod extra;
pub mod multisuper;
pub mod negative_super;
pub mod supertrait_super;
pub mod default_super;
pub mod generic_super;
pub mod macros;
pub mod scopes;
