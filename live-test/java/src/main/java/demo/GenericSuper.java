// Super-method fixture, generic case: Repo.find overrides BaseRepo.find,
// whose signature is declared with the type parameter T — the super must
// resolve across the generic signature.
package demo;

abstract class BaseRepo<T> {
    abstract T find(int id);
}

class Repo<T> extends BaseRepo<T> {
    @Override
    T find(int id) {
        return null;
    }
}
