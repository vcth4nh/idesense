package trace

import "testing"

// TestCalls calls each target of trace.go. The loop calls CallDirect three times from one line.
func TestCalls(t *testing.T) {
	sum := 0
	for range 3 {
		sum += CallDirect()
	}
	sum += Total(Sq{side: 2}) + CallValue() + InLiteral()
	sum += OneLine() // call of OneLine
	sum += Multi(5)  // call of Multi
	if sum != 3+4+2+3+4+5 {
		t.Fatal(sum)
	}
}
