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

function writeProbe() {
    const d = new Derived();
    d.value = 'w';
    return d.value;
}
