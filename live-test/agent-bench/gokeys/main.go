// Command gokeys writes the answer keys of a Go module from the name resolution of the Go
// compiler (go/types through golang.org/x/tools/go/packages).
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const usage = `usage:
  gokeys extract -tree <dir> -configs linux,windows -out <file.jsonl>
  gokeys calls -tree <dir> -configs linux,windows,darwin -out <calls.jsonl> [-check]
  gokeys idents -tree <dir> -name <identifier>
  gokeys accept -tree <dir> -keys <file.jsonl> (-ids <id,...|@file> | -sample <n> [-seed <s>])
                -configs linux,windows -scratch <dir> [-minimal] [-keep]
  gokeys trace -tree <dir> -targets <targets.json> -dst <new folder> [-depth 6] [-no-check]`

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

// run is the command line entry. It returns the exit code: 0 success, 1 failure, 2 usage.
func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprintln(stderr, usage)
		return 2
	}
	switch args[0] {
	case "extract":
		return cmdExtract(args[1:], stdout, stderr)
	case "calls":
		return cmdCalls(args[1:], stdout, stderr)
	case "idents":
		return cmdIdents(args[1:], stdout, stderr)
	case "accept":
		return cmdAccept(args[1:], stdout, stderr)
	case "trace":
		return cmdTrace(args[1:], stdout, stderr)
	}
	fmt.Fprintln(stderr, usage)
	return 2
}

func cmdExtract(args []string, stdout, stderr io.Writer) int {
	fl := flag.NewFlagSet("extract", flag.ContinueOnError)
	fl.SetOutput(stderr)
	tree := fl.String("tree", "", "root folder of the module")
	configs := fl.String("configs", "", "comma-separated GOOS values; GOARCH is amd64")
	out := fl.String("out", "", "output JSONL file")
	if err := fl.Parse(args); err != nil {
		return 2
	}
	if *tree == "" || *configs == "" || *out == "" || fl.NArg() != 0 {
		fmt.Fprintln(stderr, usage)
		return 2
	}
	start := time.Now()
	recs, st, err := extract(*tree, splitConfigs(*configs))
	if err != nil {
		fmt.Fprintln(stderr, "gokeys extract:", err)
		return 1
	}
	if err := writeJSONL(*out, recs); err != nil {
		fmt.Fprintln(stderr, "gokeys extract:", err)
		return 1
	}
	st.print(stderr, time.Since(start))
	return 0
}

// splitConfigs gives the GOOS values of a comma-separated list.
func splitConfigs(s string) []string {
	var goos []string
	for _, c := range strings.Split(s, ",") {
		if c = strings.TrimSpace(c); c != "" {
			goos = append(goos, c)
		}
	}
	return goos
}

// cmdCalls: gokeys calls. Exit code 1 for an error, and with -check for a pair that only one
// side has.
func cmdCalls(args []string, stdout, stderr io.Writer) int {
	fl := flag.NewFlagSet("calls", flag.ContinueOnError)
	fl.SetOutput(stderr)
	tree := fl.String("tree", "", "root folder of the module")
	configs := fl.String("configs", "", "comma-separated GOOS values; GOARCH is amd64")
	out := fl.String("out", "", "output JSONL file")
	check := fl.Bool("check", false, "compare the static calls with the static call graph of go/ssa")
	if err := fl.Parse(args); err != nil {
		return 2
	}
	if *tree == "" || *configs == "" || *out == "" || fl.NArg() != 0 {
		fmt.Fprintln(stderr, usage)
		return 2
	}
	start := time.Now()
	recs, st, checks, err := extractCalls(*tree, splitConfigs(*configs), *check)
	if err != nil {
		fmt.Fprintln(stderr, "gokeys calls:", err)
		return 1
	}
	if err := writeJSONL(*out, recs); err != nil {
		fmt.Fprintln(stderr, "gokeys calls:", err)
		return 1
	}
	st.print(stdout, time.Since(start))
	if *check && !printCheck(stdout, recs, checks) {
		return 1
	}
	return 0
}

// writeJSONL writes one record for each line, atomically (a temporary file and a rename).
func writeJSONL[T any](path string, recs []T) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	f, err := os.CreateTemp(dir, "."+filepath.Base(path)+".tmp*")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if err := f.Chmod(0o644); err != nil {
		f.Close()
		return err
	}
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	for i := range recs {
		if err := enc.Encode(&recs[i]); err != nil {
			f.Close()
			return err
		}
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(f.Name(), path)
}
