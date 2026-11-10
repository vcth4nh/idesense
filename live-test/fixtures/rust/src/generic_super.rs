// Generic trait with type parameter — IntStore satisfies Storage<i32>.
pub trait Storage<T> {
    fn get(&self, key: &str) -> T;
}

pub struct IntStore;

// Super on get() resolves through the Storage<i32> instantiation back to the
// generic declaration.
impl Storage<i32> for IntStore {
    fn get(&self, _key: &str) -> i32 {
        0
    }
}
