// Dispatch vehicles: each quirk method funnels the same standard library
// parse call through a different syntactic wrapper, so resolution is probed
// once per wrapper. This file's warning diagnostics are pinned in full.
package demo;

import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public class Quirks {

    // Plain lambda wrapper.
    public static int quirkLambda(String x) {
        Function<String, Integer> fn = s -> Integer.parseInt(s);
        return fn.apply(x);
    }

    // Method reference cast and stored in a local variable.
    public static int quirkVar(String x) {
        var coerce = (Function<String, Integer>) Integer::parseInt;
        return coerce.apply(x);
    }

    // Anonymous class; the nearest super of its apply override lives in the
    // standard library.
    public static int quirkAnonClass(String x) {
        Function<String, Integer> fn = new Function<>() {
            @Override
            public Integer apply(String s) {
                return Integer.parseInt(s);
            }
        };
        return fn.apply(x);
    }

    // Mapped inside an optional container.
    public static Optional<Integer> quirkOptional(String x) {
        return Optional.of(x).map(Integer::parseInt);
    }

    // Ternary picking between a lambda and a method reference.
    public static int quirkTernary(String x, boolean stripPlus) {
        Function<String, Integer> fn = stripPlus
            ? s -> Integer.parseInt(s.replace("+", ""))
            : Integer::parseInt;
        return fn.apply(x);
    }

    // Deferred through an asynchronous future.
    public static CompletableFuture<Integer> quirkCompletableFuture(String x) {
        return CompletableFuture.supplyAsync(() -> Integer.parseInt(x));
    }

    // Stream map over a whole list.
    public static List<Integer> quirkStreamMap(List<String> xs) {
        return xs.stream().map(Integer::parseInt).collect(Collectors.toList());
    }

    // Table dispatch: functions stored in a map and picked by key.
    public static int quirkMapDispatch(String key, String x) {
        Map<String, Function<String, Integer>> dispatch = new HashMap<>();
        dispatch.put("int", Integer::parseInt);
        dispatch.put("abs", s -> Math.abs(Integer.parseInt(s)));
        return dispatch.get(key).apply(x);
    }

    // Small nested class kept as a class-search target.
    static class Coercer {
        private final String prefix;
        Coercer(String prefix) { this.prefix = prefix; }
        int coerce(String x) { return Integer.parseInt(x.replace(prefix, "")); }
    }

    // Functional interface: the method reference assigned to it below is
    // reported as its implementation, rather than any class.
    @FunctionalInterface
    interface Coerce { int run(String s); }

    public static int quirkFunctionalIface(String x) {
        Coerce c = Integer::parseInt;
        return c.run(x);
    }

    // Constant-body dispatch: each constant supplies its own apply body, and
    // both bodies count as implementations of the abstract declaration.
    enum CoerceMode {
        INT { int apply(String s) { return Integer.parseInt(s); } },
        ABS { int apply(String s) { return Math.abs(Integer.parseInt(s)); } };
        abstract int apply(String s);
    }

    // Resolving the apply call on a specific constant lands on the abstract
    // declaration, not on that constant's body.
    public static int quirkEnumDispatch(String x) {
        return CoerceMode.INT.apply(x);
    }

    // Captured in a supplier.
    public static int quirkSupplier(String x) {
        Supplier<Integer> supplier = () -> Integer.parseInt(x);
        return supplier.get();
    }

    // Overload pair: same name, different parameter lists. parseUsage calls
    // both, so resolving each call must land on the matching overload.
    public static int parse(String s) {
        return Integer.parseInt(s);
    }

    public static int parse(String s, int radix) {
        return Integer.parseInt(s, radix);
    }

    public static int parseUsage() {
        return parse("42") + parse("ff", 16);
    }
}
