// Hosts Plain, whose toString override's nearest super method lives in the
// standard library. Snapshots reduce such library supers to a bare file name
// plus symbol identity, with no directory and no line numbers.
package demo;

class Plain {
    @Override
    public String toString() {
        return "plain";
    }
}
