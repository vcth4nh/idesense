package mod

// Shape is a figure with an area.
type Shape interface {
	Area() float64
	Name() string
}

type Square struct{ side float64 }

func (s Square) Area() float64 { return s.side * s.side }

func (s Square) Name() string { return "square" }

// Base gives an area to the types that embed it.
type Base struct{ r float64 }

func (b Base) Area() float64 { return 3 * b.r * b.r }

// Circle implements Shape through the embedded Base.
type Circle struct {
	Base
}

func (c *Circle) Name() string { return "circle" }

func total(shapes []Shape) float64 {
	sum := 0.0
	for _, s := range shapes {
		sum += s.Area()
	}
	return sum
}

func circleArea(c Circle) float64 {
	return c.Area()
}

func baseOf(c Circle) Base {
	return c.Base
}
