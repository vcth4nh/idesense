<?php
// Super-method fixtures where one member has several direct parents at once:
// base class + interfaces, deep chains, a diamond, traits with conflict
// resolution, and overridden constants.
namespace Demo;

// Abstract base + 2 interfaces all declaring name(); Triple overrides all 3.
interface IRender {
    public function name(): string;
}

interface IDisplay {
    public function name(): string;
}

abstract class Base {
    abstract public function name(): string;
}

class Triple extends Base implements IRender, IDisplay {
    public function name(): string {
        return "triple";
    }
}

// Deep override chain (abstract -> concrete -> override -> override)
// Mid2 has 2 direct supers: Mid1 + IComputable.
// Leaf has 2 direct supers: Mid2 + IOperable.
abstract class Animal {
    abstract public function m(): string;
}

class Mid1 extends Animal {
    public function m(): string {
        return "mid1";
    }
}

interface IComputable {
    public function m(): string;
}

class Mid2 extends Mid1 implements IComputable {
    public function m(): string {
        return "mid2";
    }
}

interface IOperable {
    public function m(): string;
}

class Leaf extends Mid2 implements IOperable {
    public function m(): string {
        return "leaf";
    }
}

// Diamond (abstract base + interface inheritance) — 3 declared paths for m.
abstract class AbstractMethodHolder {
    abstract public function m(): string;
}

interface Top {
    public function m(): string;
}

interface LeftI extends Top {}

interface RightI extends Top {}

class Bottom extends AbstractMethodHolder implements LeftI, RightI {
    public function m(): string {
        return "bottom";
    }
}

// Trait usage with override — 3 sources for log.
// AbstractLogger declares abstract log(); two traits both provide log().
// Use `insteadof` so ExtraLoggingTrait's impl wins; alias LoggingTrait's
// version so it still participates as a declared source.
trait LoggingTrait {
    public function log(string $msg): void {
        // default trait impl
    }
}

trait ExtraLoggingTrait {
    public function log(string $msg): void {
        // extra trait impl
    }
}

abstract class AbstractLogger {
    abstract public function log(string $msg): void;
}

class WithTrait extends AbstractLogger {
    use LoggingTrait, ExtraLoggingTrait {
        ExtraLoggingTrait::log insteadof LoggingTrait;
        LoggingTrait::log as logFromBase;
    }

    public function log(string $msg): void {
        // override
    }
}

// Constant override (PHP 8.1+) — 3 direct sources for KIND.
abstract class KindBase {
    const KIND = "base";
}

interface IKindBearer {
    const KIND = "iface";
}

interface IKindLabel {
    const KIND = "label";
}

class KindLeaf extends KindBase implements IKindBearer, IKindLabel {
    const KIND = "leaf";
}

// Multiple-interface signature merge — 3 interfaces declare run().
interface IA {
    public function run(): void;
}

interface IB {
    public function run(): void;
}

interface IC {
    public function run(): void;
}

class Runner implements IA, IB, IC {
    public function run(): void {
        // unified
    }
}

// Interface default-via-trait — 2 interfaces declare greet(); 2 traits provide it.
// Resolve trait conflict: DefaultGreet2's impl wins via `insteadof`; alias the other.
interface IGreet {
    public function greet(): string;
}

interface IGreet2 {
    public function greet(): string;
}

trait DefaultGreet {
    public function greet(): string {
        return "hi";
    }
}

trait DefaultGreet2 {
    public function greet(): string {
        return "hi2";
    }
}

class UsesDefault implements IGreet, IGreet2 {
    use DefaultGreet, DefaultGreet2 {
        DefaultGreet2::greet insteadof DefaultGreet;
        DefaultGreet::greet as greetFromDefault;
    }
}
