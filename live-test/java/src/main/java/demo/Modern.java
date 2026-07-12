// Newer language constructs: record Point plus sealed interface Animal with
// its two permitted classes — record components, canonical-constructor
// resolution, and a closed sealed hierarchy.
package demo;

public class Modern {
    // The record header declares each component and its accessor in one
    // place; sum() reads the components directly.
    public record Point(int x, int y) {
        public int sum() { return x + y; }
    }

    // Sealed interface: Cat and Dog are the only permitted implementations,
    // so the hierarchy is closed with exactly two subtypes.
    public sealed interface Animal permits Cat, Dog {
        String name();
    }

    public static final class Cat implements Animal {
        @Override public String name() { return "cat"; }
    }

    public static final class Dog implements Animal {
        @Override public String name() { return "dog"; }
    }

    // Call site for Point's canonical constructor: resolving new Point(...)
    // lands on the record declaration itself, since no constructor is written.
    public static int probe() {
        Point p = new Point(3, 4);
        return p.sum();
    }
}
