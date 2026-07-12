// Super-method fixture, lambda case: probing the arrow of the lambda in
// make() resolves the functional interface's single abstract method in the
// standard library — mirroring the IDE's go-to-super — with no super chain.
package demo;

class LambdaHost {
    Runnable make() {
        return () -> System.out.println("lambda");
    }
}
