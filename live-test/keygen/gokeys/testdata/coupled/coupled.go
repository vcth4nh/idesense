// Package coupled has one structural family of nine methods. The conversions and the
// assertions of the package link six of them.
package coupled

type P interface {
	Provision() error
}

type Q interface {
	Provision() error
}

// The first type has a guard.
type A struct{}

func (*A) Provision() error { return nil }

var _ P = (*A)(nil)

// The second type goes to a parameter.
type B struct{}

func (*B) Provision() error { return nil }

func run(p P) error {
	return p.Provision()
}

func runB() error {
	return run(&B{})
}

// This type goes to no interface.
type H struct{}

func (*H) Provision() error { return nil }

// This type reaches the interface only through an assertion from an empty interface.
type D struct{}

func (*D) Provision() error { return nil }

func assertD() bool {
	var x any = &D{}
	_, ok := x.(P)
	return ok
}

// This type goes only to the second interface, and a value of the first interface goes to it.
type E struct{}

func (*E) Provision() error { return nil }

func toQ(p P) Q {
	var q Q = p
	return q
}

func useE() Q {
	var q Q = &E{}
	return q
}

func direct() {
	_ = (&A{}).Provision()
	_ = (&B{}).Provision()
	_ = (&H{}).Provision()
	_ = (&D{}).Provision()
	_ = (&E{}).Provision()
}

// A conversion from a type parameter gives no link.
func viaParam[T P](t T) P {
	return t
}
