// Enum fixtures: numeric Direction and string-valued Color; opposite and isWarm
// give the enums and their members reference sites for navigation probes.
// Ground truth: a numeric enum's type hierarchy is NOT empty — the standard
// library's number wrapper shows up as its supertype. The IDE's combined
// hierarchy widget hides this for enums; its Supertypes view shows it.
export enum Direction {
    North,
    East,
    South,
    West,
}

export enum Color {
    Red = "red",
    Green = "green",
    Blue = "blue",
}

export function opposite(d: Direction): Direction {
    if (d === Direction.North) return Direction.South;
    if (d === Direction.South) return Direction.North;
    if (d === Direction.East) return Direction.West;
    return Direction.East;
}

export function isWarm(c: Color): boolean {
    return c === Color.Red || c === Color.Green;
}
