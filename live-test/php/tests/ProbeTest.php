<?php
// Test-tree half of the scope fixtures: a caller and a subclass of the
// production-side class under test live here — test-scope queries include
// them, production-scope queries must exclude them.
namespace Demo\Tests;

use Demo\Probe;

final class ProbeTest
{
    // Test-scope caller.
    public function testCaller(): int
    {
        return (new Probe())->target();
    }
}

// Test-scope subtype.
class ProbeTestChild extends Probe
{
}
