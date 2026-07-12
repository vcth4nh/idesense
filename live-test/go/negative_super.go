package main

// Standalone struct method with a uniquely-named method — no interface in
// this file declares Compute, so no super (Go uses implicit interfaces).
// Ground truth: the correct result is an empty super list (method resolves,
// zero supers), not an error — matching GoLand's absent gutter icon here.
type Standalone struct{}

func (s *Standalone) Compute() string {
	return "standalone"
}
