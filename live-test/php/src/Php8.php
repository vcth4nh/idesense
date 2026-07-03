<?php

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
    public const VERSION = 8;

    private ?Php8Helper $helper;

    public function __construct(?Php8Helper $helper)
    {
        $this->helper = $helper;
    }

    public function tag(): string
    {
        return $this->helper?->label() ?? 'none';
    }
}

function fccTarget(string $s): int
{
    return strlen($s);
}

function useFcc(): int
{
    $fn = fccTarget(...);
    return $fn('abc');
}
