// Negative super-method fixture: Standalone.compute() overrides nothing, so
// the probe finds the method but returns an empty super hierarchy.
package demo;

class Standalone {
    String compute() {
        return "standalone";
    }
}
