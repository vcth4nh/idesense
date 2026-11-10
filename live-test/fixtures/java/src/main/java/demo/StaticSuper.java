// Static-hiding fixture: StaticDerived.factory hides StaticBase.factory
// rather than overriding it, so the super probe reports no super method —
// hiding is not overriding.
package demo;

class StaticBase {
    static String factory() {
        return "base";
    }
}

class StaticDerived extends StaticBase {
    static String factory() {
        return "child";
    }
}
