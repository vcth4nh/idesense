package main

// Main shape fixture: Drawable/Shape interfaces, the baseShape embed target,
// Circle/Rectangle/Square implementers, and ShapeCollection — most of this
// package's navigation, hierarchy, and usage anchors point here.
// Ground truth: GoLand's file structure is package-scoped — a structure query
// on this file lists every type in package main (tagged with origin file), so
// appending a declaration in ANY package file drifts this file's snapshot.
// Go qualified names come from a reflection fallback (package.Type.Method
// form); a few positions legitimately have none.
import "fmt"

// Both interfaces are satisfied only structurally (Go has no implements):
// the type hierarchy lists the concrete shapes below as their subtypes and,
// from the structs' side, these interfaces as supertypes.
type Drawable interface {
	Draw() string
}

type Shape interface {
	Area() float64
	Describe() string
}

// baseShape is the unexported embed target: embedding promotes Describe into
// Circle and Rectangle (which override it) and into a cross-file embedder.
// It satisfies neither interface, so its own type hierarchy is empty.
// Ground truth: GoLand's Find Usages on the baseShape type counts the method
// receiver "(b baseShape)" as a usage of the type, on top of the embed sites
// (one cross-file) and the test file's field and composite-literal references.
type baseShape struct{}

func (b baseShape) Describe() string { return "shape with unknown area" }

// Circle and Rectangle embed baseShape but override the promoted Describe;
// each also defines its own area and draw methods, satisfying both interfaces.
type Circle struct {
	baseShape
	Radius float64
}

// The concrete area methods double as scope-filter vehicles for usage and
// caller lookups; in Go the class scope is meaningful (receiver-scoped).
func (c Circle) Area() float64 { return 3.14159 * c.Radius * c.Radius }
func (c Circle) Describe() string {
	return fmt.Sprintf("Circle with area %f", c.Area())
}
func (c Circle) Draw() string { return fmt.Sprintf("circle r=%f", c.Radius) }

type Rectangle struct {
	baseShape
	Width, Height float64
}

func (r Rectangle) Area() float64 { return r.Width * r.Height }
func (r Rectangle) Describe() string {
	return fmt.Sprintf("Rectangle with area %f", r.Area())
}
func (r Rectangle) Draw() string { return fmt.Sprintf("rect %fx%f", r.Width, r.Height) }

// Square declares no methods — it satisfies both interfaces purely through
// the embedded Rectangle; NewSquare is the factory MakeDefaultShapes calls.
type Square struct{ Rectangle }

func NewSquare(side float64) Square {
	return Square{Rectangle: Rectangle{Width: side, Height: side}}
}

// ShapeCollection dispatches through the interface: callee walks on TotalArea
// and Largest surface the interface area method as a callee. The struct
// satisfies no interface, so its own type hierarchy is empty.
type ShapeCollection struct {
	Shapes []Shape
}

func (sc *ShapeCollection) Add(s Shape) {
	sc.Shapes = append(sc.Shapes, s)
}

func (sc *ShapeCollection) TotalArea() float64 {
	sum := 0.0
	for _, s := range sc.Shapes {
		sum += s.Area()
	}
	return sum
}

func (sc *ShapeCollection) Largest() Shape {
	var best Shape
	for _, s := range sc.Shapes {
		if best == nil || s.Area() > best.Area() {
			best = s
		}
	}
	return best
}

// MakeDefaultShapes builds one of each concrete shape — the entry point for
// callee-direction call trees (two composite literals plus a NewSquare call).
func MakeDefaultShapes() []Shape {
	return []Shape{
		Circle{Radius: 1.0},
		Rectangle{Width: 2.0, Height: 3.0},
		NewSquare(4.0),
	}
}
