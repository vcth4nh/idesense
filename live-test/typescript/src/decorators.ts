// Decorator fixture: traced is applied to Service methods. Pins that the @-sites
// count as usages of traced, that an @-site resolves back to the function, and
// that decorating a method does not break caller resolution.
export function traced(target: Function, context: any): void {
    void target;
    void context;
}

// greet has a cross-file caller in a sibling fixture, so its call hierarchy must
// still surface callers despite the decorator; farewell is the second usage site
// for traced.
export class Service {
    @traced
    greet(name: string): string {
        return `hello ${name}`;
    }

    @traced
    farewell(name: string): string {
        return `bye ${name}`;
    }
}
