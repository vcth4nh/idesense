// Cross-file consumer: use() constructs a Circle and calls
// makeDefaultShapes, so the required module's symbols have usages and
// callers coming from a second file.
'use strict';
const { Circle, makeDefaultShapes } = require('./normal');

function use() {
    return new Circle(2).area() + makeDefaultShapes().length;
}

module.exports = { use };
