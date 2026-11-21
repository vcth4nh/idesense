package mod_test

import (
	"testing"

	"example.com/mod"
)

func TestExternal(t *testing.T) {
	if mod.Compute(5) != 10 {
		t.Fail()
	}
}
