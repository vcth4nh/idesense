<?php
// Constructor super fixture: ChildCtor::__construct overrides ParentCtor's,
// pinning that constructor supers resolve like ordinary method supers.
namespace Demo;

class ParentCtor {
    public function __construct(public string $name) {}
}

class ChildCtor extends ParentCtor {
    public function __construct(string $name, public int $extra) {
        parent::__construct($name);
    }
}
