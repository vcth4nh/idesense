// Package trace is the test module of gokeys trace. Each line with a call of a target function
// ends with the comment "call of <name of the target>".
package trace

// Shape is an interface: Sq.Area is called only through an interface value.
type Shape interface{ Area() int }

type Sq struct{ side int }

func (s Sq) Area() int {
	return s.side * s.side
}

func Direct() int {
	return 1
}

func viaValue() int {
	return 2
}

func lit() int {
	return 3
}

func OneLine() int { return 4 }

// Multi has its opening brace two lines below its name.
func Multi(
	a int,
) int {
	return a
}

// CallDirect calls Direct directly.
func CallDirect() int {
	return Direct() // call of Direct
}

// Total calls Area through the interface value s. With no inlining the compiler cannot change
// the call into a direct call, so the call goes through the method wrapper of *Sq.
//
//go:noinline
func Total(s Shape) int {
	return s.Area() // call of Area
}

// apply calls viaValue through the function value f.
//
//go:noinline
func apply(f func() int) int {
	return f() // call of viaValue
}

func CallValue() int {
	return apply(viaValue)
}

// InLiteral calls lit inside a function literal.
func InLiteral() int {
	g := func() int {
		return lit() // call of lit
	}
	return g()
}
