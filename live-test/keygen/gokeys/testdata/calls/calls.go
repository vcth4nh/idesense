// Package calls has one example of each call form of the calls subcommand.
package calls

// Base has a method that Outer promotes.
type Base struct{}

func (Base) Area() int { return 1 }

// Outer embeds Base.
type Outer struct{ Base }

// T has a value method and a pointer method.
type T struct{ n int }

func (t T) Get() int { return t.n }

func (t *T) Set(n int) { t.n = n }

// Getter is an interface with the method of T.
type Getter interface{ Get() int }

// Box is a generic type with a method.
type Box[E any] struct{ e E }

func (b Box[E]) Val() E { return b.e }

func plain(n int) int { return n }

func spawned(n int) {}

func deferred(n int) {}

func wrapped(n int) int { return n }

func apply(f func() int) int { return f() }

func generic[E any](e E) E { return e }

// Exported has a caller in the external test package.
func Exported() int { return 0 }

func callers(t T, o Outer, g Getter) {
	plain(1)
	t.Get()
	o.Area()
	T.Get(t)
	(*T).Set(&t, 2)
	apply(t.Get)
	apply(Exported)
	go spawned(4)
	defer deferred(5)
	(wrapped)(6)
	generic[int](7)
	generic(8)
	Box[int]{}.Val()
	g.Get()
	_ = T(t)
}

func inLiteral() {
	func() { plain(9) }()
}

var initial = plain(10)

var viaLiteral = func() int { return plain(11) }

// The conversion of a pointer to Getter makes the wrapper of the method set of *T.
var _ Getter = &T{}

func init() { plain(12) }

func _() { wrapped(13) }
