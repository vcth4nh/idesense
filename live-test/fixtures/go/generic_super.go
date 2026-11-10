package main

// Super-method fixtures for parameterized and composed interfaces: what a
// method's implicit super set looks like under generics, and how supers
// dedup when embedded interfaces repeat an identical signature.
// Go 1.18+ generic interface — IntStore satisfies Storage[int].
type Storage[T any] interface {
	Get(key string) T
}

type IntStore struct{}

func (s *IntStore) Get(key string) int {
	return 0
}

// Composition: combined interface embedding two interfaces with the same
// method. Tests dedup when a single struct method satisfies multiple
// interfaces with identical signatures.
type Runner1 interface {
	Run() string
}

type Runner2 interface {
	Run() string
}

type Combined interface {
	Runner1
	Runner2
}

type Implementer struct{}

func (i *Implementer) Run() string {
	return "run"
}
