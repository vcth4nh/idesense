package mod

import "bytes"

// ByteSink is an interface that types of the standard library implement.
type ByteSink interface {
	Write(p []byte) (int, error)
}

// BufSink gets the method of ByteSink from the embedded buffer of the standard library.
type BufSink struct {
	*bytes.Buffer
}

func fill(s ByteSink) {
	s.Write(nil)
}
