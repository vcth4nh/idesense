// Dynamic-mixin fixture: a class extending the class expression returned
// by the Amplifier mixin factory instead of a statically named base.
'use strict';

const Amplifier = (Base) => class extends Base {
    shout() { return "SHOUT"; }
};

class Plain {
    shout() { return "plain"; }
}

// Ground truth: WebStorm cannot statically resolve Amplifier(Plain) as a
// base class, so super lookup on this shout() returns an empty hierarchy;
// the editor gutter shows no override marker either. Expected, not a gap.
class WithMixin extends Amplifier(Plain) {
    shout() { return "with-mixin"; }
}

module.exports = { Amplifier, Plain, WithMixin };
