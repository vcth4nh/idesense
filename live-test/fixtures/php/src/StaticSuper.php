<?php
// Static-method super fixture: StaticDerived::make() overrides the abstract
// static make() on StaticBase — static overrides super-resolve too.
namespace Demo;

abstract class StaticBase {
    abstract public static function make(): string;
}

class StaticDerived extends StaticBase {
    public static function make(): string {
        return "child";
    }
}
