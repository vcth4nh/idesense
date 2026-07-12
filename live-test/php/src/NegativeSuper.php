<?php
// Negative super fixture: Standalone extends and implements nothing, so
// compute() must yield an empty super chain rather than an error.
namespace Demo;

class Standalone {
    public function compute(): string {
        return "standalone";
    }
}
