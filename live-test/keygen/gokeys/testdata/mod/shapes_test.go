package mod

import "testing"

func TestTotal(t *testing.T) {
	if total([]Shape{Square{side: 1}}) != 1 {
		t.Fatal("total")
	}
	if Compute(4) != 8 {
		t.Fatal("Compute")
	}
}
