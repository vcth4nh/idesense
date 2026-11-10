<?php
// Backed-enum super fixture: Severity implements Labeled and overrides its
// label(); the enum's cases double as usage targets.
namespace Demo;

interface Labeled {
    public function label(): string;
}

// Ground truth: the type hierarchy of a backed enum reports supertypes — the
// engine's backed-enum interface chain plus Labeled. PhpStorm's combined
// Type Hierarchy widget hides these for enums; its Supertypes view shows
// them, so an empty result here would be a regression, not a fix.
enum Severity: string implements Labeled {
    case Low = "low";
    case High = "high";

    public function label(): string {
        return match ($this) {
            Severity::Low => "Low",
            Severity::High => "High",
        };
    }
}
