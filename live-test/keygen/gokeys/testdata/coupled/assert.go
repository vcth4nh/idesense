package coupled

// Three interfaces. Each pair has one common method, and no interface has the method set of
// another one.
type Stopper interface {
	Stop()
	Pause()
}

type Halter interface {
	Stop()
	Resume()
}

type Waiter interface {
	Pause()
	Wait()
}

// This type implements the three interfaces, and its value goes to no interface.
type Both struct{}

func (Both) Stop()   {}
func (Both) Pause()  {}
func (Both) Resume() {}
func (Both) Wait()   {}

// An assertion to another interface links the common method.
func halter(s Stopper) bool {
	_, ok := s.(Halter)
	return ok
}

// A case of a type switch also links the common method.
func waiter(s Stopper) bool {
	switch s.(type) {
	case Waiter:
		return true
	}
	return false
}
