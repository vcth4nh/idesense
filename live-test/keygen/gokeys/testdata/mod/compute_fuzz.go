//go:build gofuzz

// A fuzz entry: Compute in a comment.
package mod

func fuzzCompute(data []byte) int {
	return Compute(len(data)) + len("Compute")
}
