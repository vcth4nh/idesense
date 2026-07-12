// Three-level override chain: LeafMix -> MidMix -> BaseMix, all overriding
// greet(). Ground truth: super lookup returns the full transitive chain --
// both ancestors, matching the gutter -- not just the immediate parent.
'use strict';

class BaseMix {
    greet() { return "base"; }
}

class MidMix extends BaseMix {
    greet() { return "mid"; }
}

class LeafMix extends MidMix {
    greet() { return "leaf"; }
}

module.exports = { BaseMix, MidMix, LeafMix };
