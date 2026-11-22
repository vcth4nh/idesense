package coupled

// An interface with a method that the first interface does not have.
type M interface {
	Name() string
}

// This type goes only to that interface, as the result of a function.
type G struct{}

func (*G) Name() string { return "g" }

func (*G) Provision() error { return nil }

func newG() M {
	return &G{}
}

// An assertion from that interface to the first interface. The two interfaces have no
// common method.
func provisionM(m M) error {
	if p, ok := m.(P); ok {
		return p.Provision()
	}
	return nil
}

// This type has the same two methods, and its value goes to no interface.
type K struct{}

func (*K) Name() string { return "k" }

func (*K) Provision() error { return nil }

func directGK() {
	_ = (&G{}).Provision()
	_ = (&K{}).Provision()
}
