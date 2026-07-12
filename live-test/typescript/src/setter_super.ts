// Accessor super fixture: WithValue declares value as a plain property and
// WithSetter implements it with a get/set pair. Ground truth: a super query on
// the setter resolves the interface property (reported as property kind).
export interface WithValue {
    value: string;
}

export class WithSetter implements WithValue {
    private _v = "";
    set value(v: string) { this._v = v.toUpperCase(); }
    get value(): string { return this._v; }
}
