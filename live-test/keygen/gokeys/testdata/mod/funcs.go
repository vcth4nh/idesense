package mod

// Compute doubles x.
func Compute(x int) int { return 2 * x }

type Counter struct{ n int }

func (c *Counter) Incr() { c.n++ }

func useCompute() int {
	a := Compute(1)
	b := Compute(2)
	var c Counter
	inc := c.Incr
	inc()
	c.Incr()
	return a + b + c.n
}
