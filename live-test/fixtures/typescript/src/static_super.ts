// Static super fixture: Child.factory shadows StaticBase.factory. Ground truth:
// static methods resolve supers like instance methods — the base static comes
// back rather than an empty result.
export class StaticBase {
    static factory(): string { return "base"; }
}

export class Child extends StaticBase {
    static factory(): string { return "child"; }
}
