// Multi-super fixtures: each block below gives one method several direct
// supers (abstract class plus interfaces) in a different shape — flat triple,
// deep chain, diamond, competing defaults, sealed set, record, and enum.
package demo;

// Flat triple: Triple has three direct supers (Base, IRender, IDisplay), all
// declaring name(). Probing the class name itself lists those supertypes.
interface IRender {
    String name();
}

interface IDisplay {
    String name();
}

abstract class Base {
    abstract String name();
}

class Triple extends Base implements IRender, IDisplay {
    @Override
    public String name() {
        return "triple";
    }
}

// Deep override chain: ChainBase -> ChainMid1 -> ChainMid2 -> ChainLeaf, with
// ITaggable joining at ChainMid2. Supers of tag() accumulate transitively —
// ChainLeaf reports the whole chain, not just its immediate parent.
abstract class ChainBase {
    abstract String tag();
}

class ChainMid1 extends ChainBase {
    @Override
    String tag() {
        return "mid1";
    }
}

interface ITaggable {
    String tag();
}

class ChainMid2 extends ChainMid1 implements ITaggable {
    @Override
    public String tag() {
        return "mid2";
    }
}

class ChainLeaf extends ChainMid2 {
    @Override
    public String tag() {
        return "leaf";
    }
}

// Diamond: DiamondLeft and DiamondRight both extend DiamondTop; DiamondBottom
// joins them with the abstract DiamondLegacy. Supers of pick() report
// DiamondTop only once — the two diamond paths are merged.
interface DiamondTop {
    String pick();
}

interface DiamondLeft extends DiamondTop {
}

interface DiamondRight extends DiamondTop {
}

abstract class DiamondLegacy {
    abstract String pick();
}

class DiamondBottom extends DiamondLegacy implements DiamondLeft, DiamondRight {
    @Override
    public String pick() {
        return "bottom";
    }
}

// Competing default methods: Greeter and FriendlyGreeter both provide greet()
// defaults, so LoudGreeter must override; all three supers are reported.
interface Greeter {
    default String greet() {
        return "hello";
    }
}

interface FriendlyGreeter {
    default String greet() {
        return "hi";
    }
}

abstract class AbstractGreeter {
    abstract String greet();
}

class LoudGreeter extends AbstractGreeter implements Greeter, FriendlyGreeter {
    @Override
    public String greet() {
        return "HELLO";
    }
}

// Sealed interface mixed with plain interfaces: SealedSquare.sides() has
// three interface supers, SealedTriangle two.
sealed interface SealedShape permits SealedSquare, SealedTriangle {
    int sides();
}

interface Polygon {
    int sides();
}

interface Quadrilateral {
    int sides();
}

final class SealedSquare implements SealedShape, Polygon, Quadrilateral {
    @Override
    public int sides() {
        return 4;
    }
}

final class SealedTriangle implements SealedShape, Polygon {
    @Override
    public int sides() {
        return 3;
    }
}

// Record implementing three interfaces that all declare label(): the accessor
// generated for the label component satisfies all three at once, and the
// record's supertype chain climbs through the library's record base class.
interface Named {
    String label();
}

interface Tagged {
    String label();
}

interface Identified {
    String label();
}

record LabelPoint(String label, int x, int y) implements Named, Tagged, Identified {
}

// Enum constant bodies: each constant overrides the enum's own abstract
// apply(), which itself implements IntFn and IntOp — a constant's apply()
// reports all three supers.
interface IntFn {
    int apply(int x);
}

interface IntOp {
    int apply(int x);
}

enum Op implements IntFn, IntOp {
    ADD {
        @Override
        public int apply(int x) {
            return x + 1;
        }
    },
    SUB {
        @Override
        public int apply(int x) {
            return x - 1;
        }
    };

    public abstract int apply(int x);
}

class AnonHost {
    Runnable make() {
        // Anonymous classes cannot have multiple direct supers in Java — kept as 1-super negative anchor
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anon");
            }
        };
    }
}
