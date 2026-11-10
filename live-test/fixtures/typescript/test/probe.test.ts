// Scope fixture, test side: ProbeTest.testCaller calls the probed method from
// test scope — caller queries list it only when their scope includes tests.
// ProbeTestChild is the test-side subclass (listed under any scope filter).
import { Probe } from '../src/probes';

export class ProbeTest {
    testCaller(): number {
        return new Probe().target();
    }
}

export class ProbeTestChild extends Probe {
}
