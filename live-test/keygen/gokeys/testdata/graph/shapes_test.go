package graph

// testShape implements Shape only in the test build.
type testShape struct{}

func (testShape) Area() int { return 7 }

func (testShape) Name() string { return "test" }
