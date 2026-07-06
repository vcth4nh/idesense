import { Service } from './decorators';

export function useService(): string {
    const s = new Service();
    return s.greet('dev');
}
