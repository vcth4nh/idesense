<?php
// PHP 8 call constructs the suite pins: nullsafe `?->` resolution and a
// first-class callable, hosted on the Php8/Php8Helper pair.

namespace Demo;

class Php8Helper
{
    public function label(): string
    {
        return 'h';
    }
}

class Php8
{
    // The constant and the private property below feed the file-structure
    // view's constants/properties filters.
    public const VERSION = 8;

    private ?Php8Helper $helper;

    public function __construct(?Php8Helper $helper)
    {
        $this->helper = $helper;
    }

    // Ground truth: definition lookup on label() after the nullsafe `?->`
    // must resolve through the nullable $helper property to Php8Helper's
    // declaration, exactly as with a plain `->`.
    public function tag(): string
    {
        return $this->helper?->label() ?? 'none';
    }
}

// Ground truth: the first-class callable created in useFcc() still resolves —
// its creation site counts as a usage of fccTarget().
function fccTarget(string $s): int
{
    return strlen($s);
}

function useFcc(): int
{
    $fn = fccTarget(...);
    return $fn('abc');
}
