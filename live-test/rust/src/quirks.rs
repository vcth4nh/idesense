// Dispatch-shape quirk vehicles: the q_* functions route the same
// parse-a-string job through different calling shapes — closures, fn
// pointers, trait objects, generic bounds, enum variants, iterator chains.
// Closure rebinding of the parse step.
pub fn q_closure(x: &str) -> i32 {
    let coerce = |s: &str| s.parse::<i32>().unwrap_or(0);
    coerce(x)
}

// Function-pointer coercion: parse_or_zero is taken as a value here and
// invoked through the pointer, never called by name.
pub fn q_fn_pointer(x: &str) -> i32 {
    let coerce: fn(&str) -> i32 = parse_or_zero;
    coerce(x)
}

// Ground truth: the coercion site above still surfaces as a caller of
// parse_or_zero in the call hierarchy.
fn parse_or_zero(s: &str) -> i32 {
    s.parse().unwrap_or(0)
}

// Boxed closure behind a dyn trait bound; definition lookup on the bound
// itself resolves into the stdlib.
pub fn q_box_dyn_fn(x: &str) -> i32 {
    let coerce: Box<dyn Fn(&str) -> i32> = Box::new(|s| s.parse().unwrap_or(0));
    coerce(x)
}

// String-keyed match dispatch.
pub fn q_match_dispatch(mode: &str, x: &str) -> i32 {
    match mode {
        "int" => x.parse().unwrap_or(0),
        "len" => x.len() as i32,
        _ => 0,
    }
}

// Trait-dispatch family: Coercer with two implementors, consumed below via
// trait object, generic bound, impl-trait argument, and boxed return.
pub trait Coercer {
    fn coerce(&self, x: &str) -> i32;
}

pub struct IntCoercer;
impl Coercer for IntCoercer {
    fn coerce(&self, x: &str) -> i32 {
        x.parse().unwrap_or(0)
    }
}

pub struct LenCoercer;
impl Coercer for LenCoercer {
    fn coerce(&self, x: &str) -> i32 {
        x.len() as i32
    }
}

// Dynamic call through &dyn — definition lookup lands on the trait's
// declaration of coerce(), not on either impl.
pub fn q_trait_object(c: &dyn Coercer, x: &str) -> i32 {
    c.coerce(x)
}

// Ground truth: implementations queried from the Coercer bound in this
// signature resolve to the trait's implementors — both impl blocks above.
pub fn q_generic_bound<C: Coercer>(c: &C, x: &str) -> i32 {
    c.coerce(x)
}

// Same dispatch via an impl-trait argument.
pub fn q_impl_trait_arg(c: impl Coercer, x: &str) -> i32 {
    c.coerce(x)
}

// Runtime choice of implementor behind a boxed trait object.
pub fn q_impl_trait_return(use_int: bool) -> Box<dyn Coercer> {
    if use_int {
        Box::new(IntCoercer)
    } else {
        Box::new(LenCoercer)
    }
}

// Enum-variant dispatch: apply() matches on the variants, making the arms
// variant-usage sites and definition-lookup anchors.
pub enum CoerceMode {
    Int,
    Len,
}

impl CoerceMode {
    pub fn apply(&self, x: &str) -> i32 {
        match self {
            CoerceMode::Int => x.parse().unwrap_or(0),
            CoerceMode::Len => x.len() as i32,
        }
    }
}

// Entry point driving the enum dispatch.
pub fn q_enum_dispatch(mode: CoerceMode, x: &str) -> i32 {
    mode.apply(x)
}

// Iterator-adapter chains: stdlib method resolution from inside closures.
pub fn q_iter_map(xs: &[&str]) -> Vec<i32> {
    xs.iter().map(|s| s.parse().unwrap_or(0)).collect()
}

pub fn q_iter_filter_map(xs: &[&str]) -> Vec<i32> {
    xs.iter().filter_map(|s| s.parse().ok()).collect()
}

pub fn q_iter_fold(xs: &[&str]) -> i32 {
    xs.iter().fold(0, |acc, s| acc + s.parse::<i32>().unwrap_or(0))
}

// Stdlib method resolution behind the ? operator.
pub fn q_question_mark(x: &str) -> Result<i32, std::num::ParseIntError> {
    let v: i32 = x.parse()?;
    Ok(v)
}

// if-let binding around the parse step.
pub fn q_if_let(x: Option<&str>) -> i32 {
    if let Some(s) = x {
        s.parse().unwrap_or(0)
    } else {
        0
    }
}
