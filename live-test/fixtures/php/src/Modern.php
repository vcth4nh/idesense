<?php
// Enum fixtures: backed Status (declaration, usages, hierarchy) and pure
// Color, with defaultStatus() referencing a case from outside the enum.
namespace Demo;

enum Status: string {
    case Active = 'A';
    case Inactive = 'I';

    public function label(): string {
        return match($this) {
            Status::Active => 'Active',
            Status::Inactive => 'Inactive',
        };
    }
}

// Pure (unbacked) counterpart to the backed Status above.
enum Color {
    case Red;
    case Green;
}

// The Status::Active read below is a jump-to-definition site for the case.
function defaultStatus(): Status {
    return Status::Active;
}
