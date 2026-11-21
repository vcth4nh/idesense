package mod

import "fmt"

// Celsius implements fmt.Stringer of the standard library.
type Celsius float64

func (c Celsius) String() string { return "celsius" }

// Label has a method of the same name with another signature.
type Label struct{}

func (Label) String(prefix string) string { return prefix }

func show(s fmt.Stringer, l Label) string {
	a := s.String()
	b := l.String("x")
	return a + b
}
