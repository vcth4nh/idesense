// Generic super fixture: Repo<T>.find overrides abstract BaseRepo<T>.find —
// super resolution must see through the generic base.
export abstract class BaseRepo<T> {
    abstract find(id: number): T;
}

export class Repo<T> extends BaseRepo<T> {
    find(id: number): T {
        throw new Error("not implemented");
    }
}
