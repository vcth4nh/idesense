// Async-method override fixture: AsyncChild.fetch overrides AsyncBase.fetch,
// pinning that super-method lookup handles async methods like plain ones.
'use strict';

class AsyncBase {
    async fetch() { return "base"; }
}

class AsyncChild extends AsyncBase {
    async fetch() { return "child"; }
}

module.exports = { AsyncBase, AsyncChild };
