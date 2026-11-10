// Negative fixture: Standalone extends nothing, so super lookup on
// compute() finds the method but returns an empty hierarchy. standaloneFn
// is the free-function counterpart.
'use strict';

class Standalone {
    compute() { return "standalone"; }
}

function standaloneFn() { return "standalone"; }

module.exports = { Standalone, standaloneFn };
