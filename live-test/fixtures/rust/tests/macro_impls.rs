// Trait implementations that a macro_rules! macro writes, next to one that is
// written by hand.
trait Glazed {
    fn glaze(&self) -> i32;
}

struct Tile;
struct Brick;
struct Slate;

// Ground truth: the IDE keeps the expansion of a macro call in a file of its
// own, which no search scope holds. The implementation search reports each
// implementation of this macro at the macro call that wrote it.
macro_rules! glazed_impl {
    ($t:ty) => {
        impl Glazed for $t {
            fn glaze(&self) -> i32 {
                1
            }
        }
    };
}

glazed_impl!(Tile);
glazed_impl!(Brick);

impl Glazed for Slate {
    fn glaze(&self) -> i32 {
        2
    }
}
