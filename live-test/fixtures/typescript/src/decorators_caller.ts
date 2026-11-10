// Cross-file caller fixture: useService constructs the imported class and calls
// its decorated method, pinning that decoration does not hide the method from
// cross-file caller resolution.
import { Service } from './decorators';

export function useService(): string {
    const s = new Service();
    return s.greet('dev');
}
