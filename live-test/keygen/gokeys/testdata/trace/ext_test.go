package trace_test

import (
	"testing"

	"example.com/trace"
)

// TestCommented calls Commented from the external test package.
func TestCommented(t *testing.T) {
	if got := trace.Commented(); got != 5 { // call of Commented
		t.Fatal(got)
	}
}
