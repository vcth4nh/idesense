package cross

// A test type whose method set satisfies the interface of the subpackage. No test of this
// package imports the subpackage, which imports this package.
type fakeConfigurer struct{}

func (fakeConfigurer) Configure(n Counter) int { return 0 }

// It satisfies the interface through the embedded field.
type fakeModule struct {
	*fakeConfigurer
}
