package calls

// onWindows is only in the windows build.
func onWindows() int { return plain(20) }

func winCaller() int { return onWindows() }
