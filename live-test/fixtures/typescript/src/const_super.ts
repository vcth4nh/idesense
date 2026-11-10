// Static readonly field super fixture: ConstChild.KIND shadows ConstBase.KIND.
// Ground truth: a super query on the field resolves the overridden base field and
// reports it as a readonly field, mirroring the IDE's overriding gutter.
export class ConstBase {
    static readonly KIND = "base";
}

export class ConstChild extends ConstBase {
    static readonly KIND = "child";
}
