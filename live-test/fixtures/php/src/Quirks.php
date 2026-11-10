<?php
// Indirect-dispatch quirks: each q* method hides a trivial coercion behind a
// different indirection (string name, closure, callable array, match arm) to
// probe what still resolves. Coercer and its implementers host interface probes.
namespace Demo;

class Quirks {

    // Function-name string rebound to a local, then called. The method is
    // also a usage target: the callable-array and dynamic-class call sites
    // below must count as references to it.
    public static function qNameRebind(string $x): int {
        $fn = 'intval';
        return $fn($x);
    }

    // Variable-function call through a name string.
    public static function qVariableFunction(string $x): int {
        $fname = 'intval';
        return $fname($x);
    }

    // Closure dispatch.
    public static function qClosure(string $x): int {
        $coerce = function (string $s): int { return intval($s); };
        return $coerce($x);
    }

    // Arrow-function dispatch.
    public static function qArrowFn(string $x): int {
        $coerce = fn(string $s): int => intval($s);
        return $coerce($x);
    }

    // Table dispatch: function name selected from an array by key.
    public static function qArrayDispatch(string $key, string $x): int {
        $dispatch = ['int' => 'intval', 'len' => 'strlen'];
        $fn = $dispatch[$key];
        return $fn($x);
    }

    // Callable-array dispatch: the array is one of the counted references to
    // qNameRebind, and `self` in self::class resolves back to Quirks.
    public static function qCallableArray(string $x): int {
        $callable = [self::class, 'qNameRebind'];
        return call_user_func($callable, $x);
    }

    // Dispatch through the builtin call helper.
    public static function qCallUserFunc(string $x): int {
        return call_user_func('intval', $x);
    }

    // Static call through a variable holding the class name.
    public static function qStaticMethodVariable(string $x): int {
        $cls = self::class;
        return $cls::qNameRebind($x);
    }

    // Closure built from a callable name string.
    public static function qFromCallable(string $x): int {
        $coerce = \Closure::fromCallable('intval');
        return $coerce($x);
    }

    // Ternary choosing between two function-name strings.
    public static function qTernary(bool $flag, string $x): int {
        $fn = $flag ? 'intval' : 'strlen';
        return $fn($x);
    }

    // Null-coalescing fallback to a function-name string.
    public static function qNullCoalesce(string $x): int {
        $fn = null ?? 'intval';
        return $fn($x);
    }

    // match-arm dispatch mixing closures and a name string: a callee-direction
    // hierarchy root, and the builtin call in its first arm is a
    // jump-to-definition site.
    public static function qMatch(string $mode, string $x): int {
        $fn = match ($mode) {
            'int' => fn($s) => intval($s),
            'len' => 'strlen',
            default => fn($s) => 0,
        };
        return $fn($x);
    }

    // Interface-typed call site for finding coerce() implementations.
    public static function qCoerceUsage(Coercer $c, string $x): int {
        return $c->coerce($x);
    }

    // Cross-file read of a constructor-promoted property; definition must
    // resolve into the promoted parameter in the other fixture file.
    public static function qPromotedRead(\Demo\Circle $c): float {
        return $c->radius;
    }
}

// Small interface with exactly two implementers, for implementation,
// hierarchy, and super probes.
interface Coercer {
    public function coerce(string $x): int;
}

class IntCoercer implements Coercer {
    public function coerce(string $x): int { return intval($x); }
}

class LenCoercer implements Coercer {
    public function coerce(string $x): int { return strlen($x); }
}
