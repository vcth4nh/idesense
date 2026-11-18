package mod

// Each type goes to each interface of the module that it implements, so each coupled family
// of this module is its whole family. A composite literal of the test file converts the
// type with the side.
var (
	_ Shape   = &Circle{}
	_ Opener  = Door{}
	_ Starter = Door{}
	_ Starter = Gate{}
	_ Opener  = Hatch{}
	_ Lener   = ByAge(nil)
	_ Lener   = Queue{}
	_ Pinger  = Host{}
	_ Prober  = Host{}
)
