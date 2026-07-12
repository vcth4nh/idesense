<?php
// Trait-based super fixture: RequiresImpl declares an abstract method that
// Implementer pulls in via `use` and overrides. Super resolution must see
// through trait flattening back to the trait's own declaration.
namespace Demo;

trait RequiresImpl {
    abstract public function required(): string;
}

class Implementer {
    use RequiresImpl;

    public function required(): string {
        return "impl";
    }
}
