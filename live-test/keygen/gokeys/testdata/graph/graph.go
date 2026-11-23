// Package graph has one example of each call step of the graph subcommand.
package graph

import "io"

// Shape is a module interface. Circle, Square, Rect and Holder implement it.
type Shape interface {
	Area() int
	Name() string
}

// Base has the method Area that Square and Outer promote. Base has no Name, so it is no Shape.
type Base struct{}

func (Base) Area() int { return 1 }

// Circle declares each method itself.
type Circle struct{}

func (Circle) Area() int { return 2 }

func (Circle) Name() string { return "circle" }

// Square gets Area from Base.
type Square struct{ Base }

func (Square) Name() string { return "square" }

// Rect has pointer receivers.
type Rect struct{}

func (*Rect) Area() int { return 3 }

func (*Rect) Name() string { return "rect" }

// Holder gets the methods of Shape from its embedded field.
type Holder struct{ Shape }

// Pair is generic, so it is no implementer of Shape.
type Pair[E any] struct{ e E }

func (Pair[E]) Area() int { return 4 }

func (Pair[E]) Name() string { return "pair" }

// Glass has the method of an unnamed interface.
type Glass struct{}

func (Glass) Lens() int { return 5 }

// Outer gets Area from Base.
type Outer struct{ Base }

// T has a method that a method value names.
type T struct{}

func (T) Get() int { return 6 }

func target() int { return 0 }

func apply(f func() int) int { return f() }

func spawned() {}

func deferred() {}

func direct() int { return target() }

func promoted(o Outer) int { return o.Area() }

func viaShape(s Shape) int { return s.Area() }

func viaHolder(h Holder) int { return h.Area() }

func viaUnnamed(x any) int { return x.(interface{ Lens() int }).Lens() }

func methodExpr(s Shape) int { return Shape.Area(s) }

func use[V Shape](v V) int { return v.Area() }

func write(w io.Writer) { w.Write(nil) }

func local() int {
	f := target
	return f()
}

func methodValue(t T) int { return apply(t.Get) }

func goDefer() {
	go spawned()
	defer deferred()
}

func inLiteral() {
	func() { target() }()
}

func recurse(n int) int {
	if n == 0 {
		return 0
	}
	return recurse(n - 1)
}

var initial = target()

func init() { target() }

// Sizer has no package-level implementer. The local type in localSizer and the unnamed struct
// in unnamedSizer implement it with the methods of their embedded fields.
type Sizer interface {
	Size() int
	Label() string
}

// SizeA, SizeB and Labeler each have one method of Sizer.
type SizeA struct{}

func (SizeA) Size() int { return 8 }

type SizeB struct{}

func (SizeB) Size() int { return 9 }

type Labeler struct{}

func (Labeler) Label() string { return "label" }

func viaSizer(z Sizer) int { return z.Size() }

func localSizer() Sizer {
	type sized struct {
		SizeA
		Labeler
	}
	type unused struct{ SizeA }
	return sized{}
}

func unnamedSizer() Sizer {
	return &struct {
		SizeB
		Labeler
	}{}
}

// Getter is a generic module interface. T implements Getter[int].
type Getter[V any] interface{ Get() V }

func viaGetterInt(g Getter[int]) int { return g.Get() }

func viaGetterParam[V any](g Getter[V]) V { return g.Get() }

func viaParamIface[V any](x any) V { return x.(interface{ Get() V }).Get() }

func getF() func() int { return target }

// noName has calls whose operand is no name, and two conversions.
func noName(x any, ch chan func()) {
	getF()()
	x.(func())()
	(<-ch)()
	_ = []byte("x")
	_ = (*Rect)(nil)
}

func indexed(l []func()) { l[0]() }
