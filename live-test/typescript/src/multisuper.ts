// Multi-super fixtures: six patterns give one member several candidate supers.
// Ground truth: super chains are transitive — every ancestor override is
// returned, not just the immediate parent.
export interface IRender {
    name(): string;
}

export interface IDisplay {
    name(): string;
}

export abstract class Base {
    abstract name(): string;
}

// Triple: abstract Base plus two interfaces all declaring name(). Ground truth:
// with both extends and implements, the method's super chain follows the class
// side only (Base.name — IRender/IDisplay are not listed as supers of the
// method); a super query on the class name itself returns all three supertypes.
export class Triple extends Base implements IRender, IDisplay {
    name(): string { return "triple"; }
}

// Pattern 1: Deep override chain (Base -> Mid1 -> Mid2 -> Leaf), Mid2 also implements IComputable
export abstract class DeepBase {
    abstract m(): string;
}

export class DeepMid1 extends DeepBase {
    m(): string { return "mid1"; }
}

export interface IComputable {
    m(): string;
}

export class DeepMid2 extends DeepMid1 implements IComputable {
    m(): string { return "mid2"; }
}

export class DeepLeaf extends DeepMid2 {
    m(): string { return "leaf"; }
}

// Pattern 2: Diamond with abstract base + diamond interfaces
export abstract class AbstractMethodHolder {
    abstract m(): string;
}

// Ground truth: subtypes of DiamondTop list DiamondBottom TWICE — once per
// inheritance edge (via DiamondLeft, via DiamondRight); the IDE does not dedupe.
export interface DiamondTop {
    m(): string;
}

export interface DiamondLeft extends DiamondTop {}

export interface DiamondRight extends DiamondTop {}

export class DiamondBottom extends AbstractMethodHolder implements DiamondLeft, DiamondRight {
    m(): string { return "bottom"; }
}

// Pattern 3: Interface with optional method, plus second interface declaring both
export interface WithOpt {
    req(): string;
    opt?(): string;
}

export interface WithOpt2 {
    req(): string;
    opt?(): string;
}

// No extends here, so both interfaces' declarations are reported as supers —
// the contrast to the class-side-only rule above.
export class OptImpl implements WithOpt, WithOpt2 {
    req(): string { return "req"; }
    opt(): string { return "opt"; }
}

// Pattern 4: Accessor (getter) override with abstract class + interface, both declare getter
export interface IValueProvider {
    get value(): string;
}

export abstract class ValueBase2 {
    abstract get value(): string;
}

export class AccessorImpl extends ValueBase2 implements IValueProvider {
    get value(): string { return "accessor"; }
}

// Pattern 5: Abstract method + abstract readonly property combo, plus two prop-bearing interfaces
export abstract class AbstractCombo {
    abstract m(): string;
    abstract readonly p: string;
}

export interface PropHolder {
    readonly p: string;
}

export interface DataBearer {
    readonly p: string;
}

export class ConcreteCombo extends AbstractCombo implements PropHolder, DataBearer {
    override m(): string { return "combo"; }
    override readonly p = "combo-prop";
}

// Pattern 6: Method override via implements only (no extends), three interfaces
export interface IRunner {
    run(): void;
}

export interface IExecutable {
    run(): void;
}

export interface ITask {
    run(): void;
}

export class Runner implements IRunner, IExecutable, ITask {
    run(): void { /* runs */ }
}
