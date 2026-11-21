package mod

// Two interfaces with the same method set, and a type that implements both.
type Pinger interface {
	Ping() string
}

type Prober interface {
	Ping() string
}

type Host struct{}

func (Host) Ping() string { return "pong" }

// An interface with an empty method set.
type Anything interface{}
