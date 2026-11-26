package graph

// onlyWindows is only in the windows build.
func onlyWindows() int { return target() }

func winCaller() int { return onlyWindows() }
