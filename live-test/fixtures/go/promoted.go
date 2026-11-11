package main

// Method promotion through an embedded pointer, and a type that has the name
// of its package.

// An interface with one method. The first struct below implements the method
// with a value receiver. The second struct embeds a pointer to the first one
// and gets the method by promotion: the implementation search reports this
// promoted method as an element that has no text of its own.
type Stamper interface {
	Stamp() string
}

type Ink struct{}

func (Ink) Stamp() string {
	return "ink"
}

type Pad struct {
	*Ink
}

// A type with the name of its package. The symbol search knows a symbol as
// package.name, so the text of this name matches each symbol of the package,
// and the type itself is not among the first results.
type Main struct{}
