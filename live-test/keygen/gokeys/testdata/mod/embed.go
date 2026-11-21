package mod

func newCircle() Circle {
	return Circle{Base: Base{r: 1}}
}

// A struct that embeds an interface of the module.
type lenBox struct {
	Lener
}

func boxLen(b lenBox) Lener {
	return b.Lener
}
