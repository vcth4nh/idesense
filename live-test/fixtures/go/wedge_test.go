package main

// wedge is a Shape implementer defined in a test file, so it appears as a
// subtype of Shape only under the "test" hierarchy scope.
type wedge struct {
	span float64
}

func (w wedge) Area() float64    { return w.span * w.span }
func (w wedge) Describe() string { return "wedge" }
