The repository at {root} is a checkout of the project caddy. Work only with this checkout.

Find each function or method of this repository that calls the method `GetIPRanges` of the type `caddyhttp.StaticIPRange`, which is declared at modules/caddyhttp/ip_range.go:85. A call counts when it names this method. A call of an interface method counts too, when the interface value can hold a value of this type. List only the direct callers: do not list the callers of the callers. A call inside a function literal counts for the function or method declaration that holds the literal. Test code counts. A file counts also when the build for this machine does not compile it. Answer with the line that holds the name of each such function or method in its declaration. Do not list `GetIPRanges` itself.

Answer with JSON only: {"sites": ["<path relative to the repository root>:<line number>", ...]}
