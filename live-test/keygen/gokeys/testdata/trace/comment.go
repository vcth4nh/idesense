package trace // the package clause has a comment after it

// Commented has its caller in the external test package.
func Commented() int {
	return 5
}
