// Trait diamond — Sub: SuperA + SuperB. Both supertraits declare `method`.
pub trait SuperA {
    fn method(&self) -> String;
}

pub trait SuperB {
    fn method(&self) -> String;
}

pub trait Sub: SuperA + SuperB {}

pub struct SubImpl;

impl SuperA for SubImpl {
    fn method(&self) -> String { "via-a".to_string() }
}

impl SuperB for SubImpl {
    fn method(&self) -> String { "via-b".to_string() }
}

impl Sub for SubImpl {}

// Single-level supertrait control case.
pub trait SingleParent {
    fn child(&self) -> String;
}

pub trait SingleDerived: SingleParent {}

pub struct SingleImpl;

impl SingleParent for SingleImpl {
    fn child(&self) -> String { "child".to_string() }
}

impl SingleDerived for SingleImpl {}
