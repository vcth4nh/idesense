// Negative case for super resolution: Standalone.compute overrides nothing,
// so a super-method lookup must return empty rather than an error.
package demo

class Standalone {
    fun compute(): String = "standalone"
}
