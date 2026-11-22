// Package setter declares an interface that test types of the parent package satisfy.
package setter

import "example.com/cross"

type Configurer interface {
	Configure(c cross.Counter) int
}

func apply(x Configurer) int {
	return x.Configure(cross.Counter{})
}
