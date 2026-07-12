// Multi-trait super fixtures: MyStruct implements three unrelated traits so
// go-to-super can be probed on a method, an associated const, and an
// associated type, each resolving to its own declaring trait.
pub trait MyTrait {
    fn m(&self) -> String;
}

pub struct MyStruct;

impl MyTrait for MyStruct {
    fn m(&self) -> String {
        "impl".to_string()
    }
}

// Associated-const and associated-type flavors: KIND and Output in the impls
// below resolve their supers to these trait declarations.
pub trait MyConst {
    const KIND: &'static str;
}

pub trait MyTypeAlias {
    type Output;
}

impl MyConst for MyStruct {
    const KIND: &'static str = "impl";
}

impl MyTypeAlias for MyStruct {
    type Output = String;
}
