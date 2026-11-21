package mod

// Two interfaces with the same method. No one of them implements the other.
type Opener interface {
	Open() string
	Close()
}

type Starter interface {
	Open() string
	Start()
}

// The first type implements both interfaces, the second only Starter, the third only Opener.
type Door struct{}

func (Door) Open() string { return "door" }

func (Door) Close() {}

func (Door) Start() {}

type Gate struct{}

func (Gate) Open() string { return "gate" }

func (Gate) Start() {}

type Hatch struct{}

func (Hatch) Open() string { return "hatch" }

func (Hatch) Close() {}

func useDoors(d Door, g Gate, o Opener, s Starter) string {
	a := d.Open()
	b := g.Open()
	c := o.Open()
	e := s.Open()
	return a + b + c + e
}
