// Accessor-pair fixture: Derived overrides both halves of value, pinning
// that super lookup matches accessor kind (setter resolves to Base's
// setter, getter to Base's getter). writeProbe below is deliberate.
'use strict';

class Base {
    set value(v) { this._v = v; }
    get value() { return this._v; }
}

class Derived extends Base {
    set value(v) { this._v = v.toUpperCase(); }
    get value() { return this._v; }
}

module.exports = { Base, Derived };

// Deliberately appended below module.exports so the lines above kept their
// positions -- not a leftover. The d.value assignment pins ground truth:
// find-usages anchored on the setter resolves only this write site (the
// read on the next line belongs to the getter) and reports it as a plain
// REFERENCE -- WebStorm emits no separate WRITE usage kind here.
function writeProbe() {
    const d = new Derived();
    d.value = 'w';
    return d.value;
}
