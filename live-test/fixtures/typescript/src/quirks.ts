// Definition-resolution quirks: each q* function wraps the same library parse
// call in a different TypeScript shape so navigation can be probed per construct.
// Lambda behind an explicitly typed variable; find-definition on the fn(x) call
// resolves to the local fn binding, not through it to the library.
export function qLambda(x: string): number {
    const fn: (s: string) => number = (s) => Number.parseInt(s, 10);
    return fn(x);
}

// The library function rebound to a local name
export function qFunctionRef(x: string): number {
    const fn = Number.parseInt;
    return fn(x, 10);
}

// Lambda whose parameter type is a generic bound
export function qGenericLambda<T extends string>(x: T): number {
    const fn = (s: T): number => Number.parseInt(s, 10);
    return fn(x);
}

// Conditional type plus as-cast selecting between two parsers
export function qConditionalType<T extends "int" | "float">(mode: T, x: string): number {
    type Fn = T extends "int" ? typeof Number.parseInt : typeof Number.parseFloat;
    const fn = (mode === "int" ? Number.parseInt : Number.parseFloat) as Fn;
    return fn(x, 10);
}

// String-keyed dispatch map of lambdas
export function qDispatchMap(key: string, x: string): number {
    const dispatch: Record<string, (s: string) => number> = {
        int: (s) => Number.parseInt(s, 10),
        abs: (s) => Math.abs(Number.parseInt(s, 10)),
    };
    return dispatch[key](x);
}

// Optional parameter guarded by optional chaining
export function qOptional(x?: string): number {
    return x?.length ? Number.parseInt(x, 10) : 0;
}

// Non-null assertion on a possibly-undefined argument
export function qNonNullAssertion(x: string | undefined): number {
    return Number.parseInt(x!, 10);
}

// as-cast on an unknown argument; the parse call is a definition anchor
export function qAsCast(x: unknown): number {
    return Number.parseInt(x as string, 10);
}

// Interface dispatch. Ground truth: find-implementations of Coercer is empty —
// intCoercer satisfies it only via a type annotation on an object literal, and
// structural satisfaction without an implements clause is not surfaced.
export interface Coercer { coerce(x: string): number; }

export const intCoercer: Coercer = {
    coerce(x: string) { return Number.parseInt(x, 10); }
};

export function qInterfaceDispatch(c: Coercer, x: string): number {
    return c.coerce(x);
}

// Generic class dispatch; the type parameter T is itself a definition target.
export class TypedCoercer<T extends string> {
    coerce(x: T): number { return Number.parseInt(x, 10); }
}

export function qGenericClass(x: string): number {
    return new TypedCoercer<string>().coerce(x);
}

// Function-type alias dispatch; aliasedCoerce is read through the alias. Ground
// truth: a type alias resolves in type hierarchy as its own element, with empty
// supertypes and subtypes.
export type Coerce = (s: string) => number;

export const aliasedCoerce: Coerce = (s) => Number.parseInt(s, 10);

export function qTypeAlias(x: string): number {
    return aliasedCoerce(x);
}
