// Getter-over-method fixture: Box extends the required Shape and redefines
// area as a get accessor over the base's plain method. Also pins how the
// require and export bindings and the getter render in file structure.
'use strict';
const { Shape } = require('./normal');

class Box extends Shape {
    constructor(s) {
        super();
        this.s = s;
    }
    get area() {
        return this.s * this.s;
    }
}

module.exports = { Box };
