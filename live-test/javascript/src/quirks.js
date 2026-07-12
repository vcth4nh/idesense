// Definition-resolution quirk host: every q* function reaches a built-in
// number-parsing function through a different syntactic indirection, so
// go-to-definition can be probed against each dispatch shape.
'use strict';

// Name rebinding
function qRebind(x) {
    const fn = Number.parseInt;
    return fn(x, 10);
}

// Computed property access
function qComputed(name, x) {
    return Number[name](x, 10);
}

// Object literal dispatch
function qObjLit(x) {
    return ({ parse: Number.parseInt }).parse(x, 10);
}

// Conditional expression
function qCond(flag, x) {
    return (flag ? Number.parseInt : Number.parseFloat)(x, 10);
}

// IIFE returning sink
function qReturned(x) {
    return (() => Number.parseInt)()(x, 10);
}

// Array-indexed dispatch
function qArrayIdx(x) {
    return [Number.parseInt, Number.parseFloat][0](x, 10);
}

// Destructured rebind
function qDestructured(x) {
    const { parseInt: p } = Number;
    return p(x, 10);
}

// Spread/rest unpacking
function qSpread(x) {
    const [fn] = [Number.parseInt];
    return fn(x, 10);
}

// bind/call/apply
function qBind(x) {
    return Number.parseInt.call(null, x, 10);
}

// Higher-order forEach
function qForEach(x) {
    const out = [];
    [Number.parseInt].forEach((fn) => out.push(fn(x, 10)));
    return out[0];
}

// Promise chain
function qPromise(x) {
    return Promise.resolve(Number.parseInt).then((fn) => fn(x, 10));
}

// async/await wrapping
async function qAwait(x) {
    const fn = await (async () => Number.parseInt)();
    return fn(x, 10);
}

// Optional chaining
function qOpt(x) {
    return Number?.parseInt(x, 10);
}

// Nullish-coalesced sink
function qNullish(x) {
    return (Number.parseInt ?? (() => 0))(x, 10);
}

// Re-export proxy
const proxy = { parse: Number.parseInt };
function qProxy(x) {
    return proxy.parse(x, 10);
}

// The shorthand names in this export list are themselves go-to-definition
// anchors (reference back to the declarations above).
module.exports = {
    qRebind, qComputed, qObjLit, qCond, qReturned, qArrayIdx,
    qDestructured, qSpread, qBind, qForEach, qPromise, qAwait,
    qOpt, qNullish, qProxy,
};
