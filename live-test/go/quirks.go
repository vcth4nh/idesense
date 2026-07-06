package main

import (
	"fmt"
	"strconv"
	"strings"
)

// Function variable
func qFnVar(x string) int {
	fn := strconv.Atoi
	v, _ := fn(x)
	return v
}

// Closure
func qClosure(x string) int {
	coerce := func(s string) int {
		v, _ := strconv.Atoi(s)
		return v
	}
	return coerce(x)
}

// Map of functions
func qMapDispatch(key, x string) int {
	dispatch := map[string]func(string) int{
		"int": func(s string) int {
			v, _ := strconv.Atoi(s)
			return v
		},
		"len": func(s string) int { return len(s) },
	}
	return dispatch[key](x)
}

// Slice of functions
func qSliceIdx(x string) int {
	fns := []func(string) int{
		func(s string) int {
			v, _ := strconv.Atoi(s)
			return v
		},
		func(s string) int { return len(s) },
	}
	return fns[0](x)
}

// Interface dispatch
type Coercer interface {
	Coerce(s string) int
}

type IntCoercer struct{}

func (IntCoercer) Coerce(s string) int {
	v, _ := strconv.Atoi(s)
	return v
}

type LenCoercer struct{}

func (LenCoercer) Coerce(s string) int { return len(s) }

func qInterfaceDispatch(c Coercer, x string) int {
	return c.Coerce(x)
}

// Goroutine + channel
func qGoroutine(x string) int {
	ch := make(chan int, 1)
	go func() {
		v, _ := strconv.Atoi(x)
		ch <- v
	}()
	return <-ch
}

// Defer
func qDefer(x string) (out int) {
	defer func() {
		v, _ := strconv.Atoi(x)
		out = v
	}()
	return 0
}

// Method value
func qMethodValue(x string) int {
	c := IntCoercer{}
	fn := c.Coerce
	return fn(x)
}

// Method expression
func qMethodExpression(x string) int {
	fn := IntCoercer.Coerce
	return fn(IntCoercer{}, x)
}

// Variadic
func qVariadic(xs ...string) int {
	if len(xs) == 0 {
		return 0
	}
	v, _ := strconv.Atoi(xs[0])
	return v
}

// Type assertion
func qTypeAssertion(x interface{}) int {
	s := x.(string)
	v, _ := strconv.Atoi(s)
	return v
}

// Type switch
func qTypeSwitch(x interface{}) int {
	switch s := x.(type) {
	case string:
		v, _ := strconv.Atoi(s)
		return v
	default:
		return 0
	}
}

// Naked print to keep package "used"
func qPrintToUpper(x string) {
	fmt.Println(strings.ToUpper(x))
}

const (
	CoerceLimitA = iota
	CoerceLimitB
)

func coerceLimitUse() int {
	return CoerceLimitA + CoerceLimitB
}
