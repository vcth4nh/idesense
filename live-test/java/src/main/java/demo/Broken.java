// This file is broken on purpose: both compile errors below are planted so
// error diagnostics always have a stable, known pair of problems to report.
package demo;

class Broken {
    int planted() {
        // Planted error: a string assigned to an integer variable.
        int mismatch = "notAnInt";
        // Planted error: a call to a method that does not exist.
        undefinedSymbol();
        return mismatch;
    }
}
