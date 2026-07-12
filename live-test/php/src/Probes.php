<?php
// Production half of the scope fixtures: Probe::target() has callers here
// and in the test tree, so production/test scope filters return different
// caller sets. Ground truth: subtype queries ignore the scope filter.
namespace Demo;

class Probe
{
    public function target(): int
    {
        return 42;
    }

    // Caller inside the class itself: visible even at the narrowest scope.
    public function sameClassCaller(): int
    {
        return $this->target() + 1;
    }
}

// Production-scope caller outside the class.
function freeProdCaller(): int
{
    return (new Probe())->target();
}

// Production-scope subtype.
class ProbeProdChild extends Probe
{
}
