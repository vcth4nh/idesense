package main

import "fmt"

// Cross-file struct embedding: Labeled embeds an unexported struct declared
// in another file of this package, so the embed field line is a cross-file
// usage site of that struct and promotes its method into Labeled.
type Labeled struct {
	baseShape
	label string
}

// Note calls the promoted method, giving it a cross-file caller and usage.
func (l Labeled) Note() string {
	return fmt.Sprintf("%s: %s", l.label, l.Describe())
}
