// Negative super fixture: Standalone extends and implements nothing, so a super
// query on compute returns the method with an empty super list (not an error).
export class Standalone {
    compute(): string { return "standalone"; }
}

// Free-function counterpart of the class-based negative case; not probed.
export function standaloneFn(): string { return "standalone"; }
