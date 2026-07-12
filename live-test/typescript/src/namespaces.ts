// Namespace fixture: Geometry is declared twice (declaration merging) and hosts
// Point, origin and unit; span calls in from outside, so navigation must resolve
// through the namespace qualifier and across the merged blocks.
export namespace Geometry {
    export class Point {
        constructor(public readonly x: number, public readonly y: number) {}

        distanceTo(other: Point): number {
            return Math.hypot(this.x - other.x, this.y - other.y);
        }
    }

    export function origin(): Point {
        return new Point(0, 0);
    }
}

// declaration merging augments Geometry
export namespace Geometry {
    export function unit(): Point {
        return new Point(1, 0);
    }
}

// span: qualified calls into both namespace blocks (origin from the first, unit
// from the merged one). Ground truth: these two qualifier mentions are the only
// counted usages of Geometry — the merged redeclaration is not itself a usage.
export function span(): number {
    return Geometry.origin().distanceTo(Geometry.unit());
}
