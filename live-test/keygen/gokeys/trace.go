package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

// traceAlias is the import name of the package benchtrace in an edited file.
const traceAlias = "benchtrace_"

// traceTarget is one entry of the targets file of gokeys trace. File is relative to the tree,
// Line is the line of the name token of a function declaration (the decl of a record of gokeys
// calls).
type traceTarget struct {
	ID   string `json:"id"`
	File string `json:"file"`
	Line int    `json:"line"`
}

// traceInsert is one text insert at a byte offset of a file.
type traceInsert struct {
	off  int
	text string
}

// traceFile is one target file of the tree, with its inserts sorted by offset.
type traceFile struct {
	rel     string // relative to the tree, with forward slashes
	src     []byte
	inserts []traceInsert
}

// cmdTrace: gokeys trace. It writes a copy of the tree in which each target function calls
// benchtrace.Hit as its first statement. The edits are inserts on existing lines, so a stack
// frame of the copy has the line of the tree.
func cmdTrace(args []string, stdout, stderr io.Writer) int {
	fl := flag.NewFlagSet("trace", flag.ContinueOnError)
	fl.SetOutput(stderr)
	tree := fl.String("tree", "", "root folder of the module (with go.mod); never written")
	targetsPath := fl.String("targets", "", "JSON list of {id, file, line}")
	dst := fl.String("dst", "", "the new folder of the copy; its parent folder must exist")
	depth := fl.Int("depth", 6, "the maximum count of caller frames in one trace line")
	noCheck := fl.Bool("no-check", false, "skip go build and go test -run '^$' in the copy")
	if err := fl.Parse(args); err != nil {
		return 2
	}
	if *tree == "" || *targetsPath == "" || *dst == "" || *depth < 1 || fl.NArg() != 0 {
		fmt.Fprintln(stderr, usage)
		return 2
	}
	start := time.Now()
	targets, edited, folder, err := trace(*tree, *targetsPath, *dst, *depth, !*noCheck)
	if err != nil {
		fmt.Fprintln(stderr, "gokeys trace:", err)
		return 1
	}
	fmt.Fprintf(stdout, "targets: %d\nedited files: %d\nfolder: %s\ntime: %.1fs\n",
		targets, edited, folder, time.Since(start).Seconds())
	return 0
}

// trace checks the tree and the targets, writes the copy and runs the checks. It gives the
// count of the targets, the count of the edited files and the folder of the copy. Each error
// of the tree, of a target and of -dst comes before the copy; after a check error the copy
// stays.
func trace(tree, targetsPath, dst string, depth int, check bool) (int, int, string, error) {
	treeAbs, err := filepath.Abs(tree)
	if err != nil {
		return 0, 0, "", err
	}
	treeReal, err := filepath.EvalSymlinks(treeAbs)
	if err != nil {
		return 0, 0, "", err
	}
	if info, err := os.Stat(treeReal); err != nil {
		return 0, 0, "", err
	} else if !info.IsDir() {
		return 0, 0, "", fmt.Errorf("%s is no folder", treeAbs)
	}
	mod := ""
	if b, err := os.ReadFile(filepath.Join(treeReal, "go.mod")); err == nil {
		mod = modulePath(b)
	}
	if mod == "" {
		return 0, 0, "", fmt.Errorf("no go.mod with a module line at the tree root %s", treeReal)
	}
	if err := checkInternal(treeReal); err != nil {
		return 0, 0, "", err
	}
	targets, err := readTargets(targetsPath)
	if err != nil {
		return 0, 0, "", err
	}
	files, err := planTrace(treeReal, targets, mod+"/internal/benchtrace")
	if err != nil {
		return 0, 0, "", err
	}
	dstReal, err := newCopyFolder(dst, treeAbs, treeReal)
	if err != nil {
		return 0, 0, "", err
	}

	if err := copyTree(treeReal, dstReal); err != nil {
		return 0, 0, "", fmt.Errorf("copy to %s: %w", dstReal, err)
	}
	for _, tf := range files {
		path := filepath.Join(dstReal, filepath.FromSlash(tf.rel))
		info, err := os.Lstat(path)
		if err != nil {
			return 0, 0, "", err
		}
		if !info.Mode().IsRegular() || !realPath(path) {
			return 0, 0, "", fmt.Errorf("the copy of %s is no regular file", tf.rel)
		}
		if err := os.WriteFile(path, applyInserts(tf.src, tf.inserts), info.Mode().Perm()); err != nil {
			return 0, 0, "", err
		}
	}
	pkg := filepath.Join(dstReal, "internal", "benchtrace")
	if err := os.MkdirAll(pkg, 0o755); err != nil {
		return 0, 0, "", err
	}
	if !realPath(pkg) {
		return 0, 0, "", fmt.Errorf("%s: a folder of the path is a symbolic link", pkg)
	}
	src := strings.Replace(benchtraceSource, "{{depth}}", strconv.Itoa(depth), 1)
	if err := os.WriteFile(filepath.Join(pkg, "benchtrace.go"), []byte(src), 0o644); err != nil {
		return 0, 0, "", err
	}
	if check {
		if err := traceChecks(dstReal); err != nil {
			return 0, 0, "", err
		}
	}
	return len(targets), len(files), dstReal, nil
}

// modulePath gives the path of the module line of a go.mod file, "" when it has no module line.
func modulePath(mod []byte) string {
	for _, line := range strings.Split(string(mod), "\n") {
		if i := strings.Index(line, "//"); i >= 0 {
			line = line[:i]
		}
		rest, ok := strings.CutPrefix(strings.TrimSpace(line), "module")
		path := strings.TrimSpace(rest)
		if !ok || path == rest || path == "" {
			continue
		}
		if path[0] == '"' || path[0] == '`' {
			p, err := strconv.Unquote(path)
			if err != nil {
				return ""
			}
			return p
		}
		return path
	}
	return ""
}

// checkInternal refuses a tree with internal/benchtrace, and a tree whose internal is a file or
// a symbolic link (the new package would not be in the copy).
func checkInternal(treeReal string) error {
	info, err := os.Lstat(filepath.Join(treeReal, "internal"))
	switch {
	case errors.Is(err, fs.ErrNotExist):
		return nil
	case err != nil:
		return err
	case !info.IsDir():
		return fmt.Errorf("internal of the tree is no folder (a symbolic link or a file)")
	}
	_, err = os.Lstat(filepath.Join(treeReal, "internal", "benchtrace"))
	switch {
	case err == nil:
		return fmt.Errorf("the tree already has internal/benchtrace")
	case !errors.Is(err, fs.ErrNotExist):
		return err
	}
	return nil
}

// readTargets reads the targets file: one JSON list, with no unknown field.
func readTargets(path string) ([]traceTarget, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.DisallowUnknownFields()
	var targets []traceTarget
	if err := dec.Decode(&targets); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, fmt.Errorf("%s: data after the list", path)
	}
	return targets, nil
}

type tracePos struct {
	rel  string
	line int
}

// planTrace checks each target and gives the inserts of each target file, sorted by path. With
// a problem it gives an error with one line for each problem.
func planTrace(treeReal string, targets []traceTarget, importPath string) ([]traceFile, error) {
	var errs []string
	ids := map[string]bool{}
	byPos := map[tracePos]string{}
	byFile := map[string][]traceTarget{}
	for _, tg := range targets {
		if ids[tg.ID] {
			errs = append(errs, fmt.Sprintf("the id %q comes two times", tg.ID))
			continue
		}
		ids[tg.ID] = true
		local := filepath.FromSlash(tg.File)
		if tg.File == "" {
			errs = append(errs, fmt.Sprintf("target %q: no file", tg.ID))
			continue
		}
		if !filepath.IsLocal(local) {
			errs = append(errs, fmt.Sprintf("target %q: the file %s is outside the tree", tg.ID, tg.File))
			continue
		}
		rel := filepath.ToSlash(filepath.Clean(local))
		p := tracePos{rel, tg.Line}
		if other, ok := byPos[p]; ok {
			errs = append(errs, fmt.Sprintf("the targets %q and %q have one position %s:%d", other, tg.ID, rel, tg.Line))
			continue
		}
		byPos[p] = tg.ID
		byFile[rel] = append(byFile[rel], tg)
	}
	rels := make([]string, 0, len(byFile))
	for rel := range byFile {
		rels = append(rels, rel)
	}
	sort.Strings(rels)
	var files []traceFile
	for _, rel := range rels {
		tf, fileErrs := planFile(treeReal, rel, byFile[rel], importPath)
		if len(fileErrs) > 0 {
			errs = append(errs, fileErrs...)
			continue
		}
		files = append(files, tf)
	}
	if len(errs) > 0 {
		return nil, errors.New(strings.Join(errs, "\n"))
	}
	return files, nil
}

// planFile gives the inserts of one target file: the import after the package name, and the
// call of Hit after the opening brace of the body of each target function.
func planFile(treeReal, rel string, targets []traceTarget, importPath string) (traceFile, []string) {
	fail := func(format string, a ...any) (traceFile, []string) {
		var errs []string
		for _, tg := range targets {
			errs = append(errs, fmt.Sprintf("target %q: ", tg.ID)+fmt.Sprintf(format, a...))
		}
		return traceFile{}, errs
	}
	path := filepath.Join(treeReal, filepath.FromSlash(rel))
	info, err := os.Lstat(path)
	switch {
	case err != nil:
		return fail("%s: %v", rel, err)
	case info.Mode()&fs.ModeSymlink != 0 || !realPath(path):
		return fail("the file %s is a symbolic link or below one", rel)
	case !info.Mode().IsRegular():
		return fail("the file %s is no regular file", rel)
	}
	src, err := os.ReadFile(path)
	if err != nil {
		return fail("%s: %v", rel, err)
	}
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, rel, src, parser.SkipObjectResolution)
	if err != nil {
		return fail("%s does not parse: %v", rel, err)
	}
	has := false
	ast.Inspect(f, func(n ast.Node) bool {
		if id, ok := n.(*ast.Ident); ok && id.Name == traceAlias {
			has = true
		}
		return !has
	})
	if has {
		return fail("%s already has the identifier %s", rel, traceAlias)
	}
	tf := traceFile{rel: rel, src: src, inserts: []traceInsert{{
		off:  fset.PositionFor(f.Name.End(), false).Offset,
		text: "; import " + traceAlias + " " + strconv.Quote(importPath),
	}}}
	var errs []string
	for _, tg := range targets {
		var found []*ast.FuncDecl
		for _, d := range f.Decls {
			if fd, ok := d.(*ast.FuncDecl); ok && fset.PositionFor(fd.Name.Pos(), false).Line == tg.Line {
				found = append(found, fd)
			}
		}
		switch {
		case len(found) == 0:
			errs = append(errs, fmt.Sprintf("target %q: no function declaration has its name at %s:%d", tg.ID, rel, tg.Line))
		case len(found) > 1:
			errs = append(errs, fmt.Sprintf("target %q: %d function declarations have their name at %s:%d", tg.ID, len(found), rel, tg.Line))
		case found[0].Body == nil:
			errs = append(errs, fmt.Sprintf("target %q: the function %s at %s:%d has no body", tg.ID, found[0].Name.Name, rel, tg.Line))
		default:
			tf.inserts = append(tf.inserts, traceInsert{
				off:  fset.PositionFor(found[0].Body.Lbrace, false).Offset + 1,
				text: traceAlias + ".Hit(" + strconv.Quote(tg.ID) + "); ",
			})
		}
	}
	if len(errs) > 0 {
		return traceFile{}, errs
	}
	sort.Slice(tf.inserts, func(a, b int) bool { return tf.inserts[a].off < tf.inserts[b].off })
	return tf, nil
}

// applyInserts gives src with each insert (sorted by offset). An insert has no newline, so no
// line moves.
func applyInserts(src []byte, inserts []traceInsert) []byte {
	var b bytes.Buffer
	last := 0
	for _, in := range inserts {
		b.Write(src[last:in.off])
		b.WriteString(in.text)
		last = in.off
	}
	b.Write(src[last:])
	return b.Bytes()
}

// newCopyFolder gives the resolved path of the new folder dst: its parent folder must exist,
// dst must not exist, and dst must not be inside the tree.
func newCopyFolder(dst, treeAbs, treeReal string) (string, error) {
	abs, err := filepath.Abs(dst)
	if err != nil {
		return "", err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(abs))
	if err != nil {
		return "", fmt.Errorf("the parent folder of -dst: %w", err)
	}
	real := filepath.Join(parent, filepath.Base(abs))
	if _, err := os.Lstat(real); err == nil {
		return "", fmt.Errorf("-dst %s exists", real)
	} else if !errors.Is(err, fs.ErrNotExist) {
		return "", err
	}
	if within(abs, treeAbs) || within(real, treeReal) {
		return "", fmt.Errorf("-dst %s is inside the tree", real)
	}
	return real, nil
}

// copyTree copies each file, symbolic link and folder of src to the new folder dst, but no .git
// folder. A link stays a link, and a file keeps its mode.
func copyTree(src, dst string) error {
	var files, dirs []string
	err := filepath.WalkDir(src, func(path string, d fs.DirEntry, err error) error {
		if err != nil || path == src {
			return err
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		switch {
		case d.IsDir() && d.Name() == ".git":
			return filepath.SkipDir
		case d.IsDir():
			dirs = append(dirs, rel)
		default:
			files = append(files, filepath.ToSlash(rel))
		}
		return nil
	})
	if err != nil {
		return err
	}
	if err := copyFiles(src, dst, files); err != nil {
		return err
	}
	// The folders with no file.
	for _, rel := range dirs {
		if err := os.MkdirAll(filepath.Join(dst, rel), 0o755); err != nil {
			return err
		}
	}
	return nil
}

// traceChecks runs go build ./... and go test -count=1 -run ^$ ./... in dir, with the
// environment of the caller. The second command compiles each test package and runs no test.
func traceChecks(dir string) error {
	for _, args := range [][]string{{"build", "./..."}, {"test", "-count=1", "-run", "^$", "./..."}} {
		cmd := exec.Command("go", args...)
		cmd.Dir = dir
		out, err := cmd.CombinedOutput()
		if err != nil {
			return fmt.Errorf("check in %s: go %s failed: %v\n%s", dir, strings.Join(args, " "), err, out)
		}
	}
	return nil
}

// benchtraceSource is the file internal/benchtrace/benchtrace.go of the copy; {{depth}} is the
// value of -depth.
const benchtraceSource = `// Code generated by gokeys trace. DO NOT EDIT.

// Package benchtrace logs the callers of the target functions of gokeys trace. Each target
// function calls Hit as its first statement.
package benchtrace

import (
	"bytes"
	"encoding/json"
	"os"
	"runtime"
	"strconv"
	"sync"
)

// depth is the maximum count of caller frames in one line.
const depth = {{depth}}

// out is the trace file. The process reads the variable one time, at its start.
var out = os.Getenv("BENCH_TRACE_OUT")

// key is one call stack of a target as program counters.
type key struct {
	id  string
	pcs [depth]uintptr
}

var (
	mu      sync.Mutex
	seenPCs = map[key]bool{}
	seen    = map[string]bool{} // the lines of the process
)

// Hit logs one line for each distinct call stack of a target.
func Hit(id string) {
	if out == "" {
		return
	}
	k := key{id: id}
	// Skip runtime.Callers, Hit and the target function: the first frame is the caller of the
	// target function.
	n := runtime.Callers(3, k.pcs[:])
	mu.Lock()
	defer mu.Unlock()
	if seenPCs[k] {
		return
	}
	seenPCs[k] = true
	var b bytes.Buffer
	b.WriteString("{\"id\":")
	b.Write(quote(id))
	b.WriteString(",\"frames\":[")
	if n > 0 {
		// CallersFrames gives an inlined function a frame of its own.
		frames := runtime.CallersFrames(k.pcs[:n])
		for i := 0; i < depth; i++ {
			f, more := frames.Next()
			if i > 0 {
				b.WriteByte(',')
			}
			b.WriteString("{\"func\":")
			b.Write(quote(f.Function))
			b.WriteString(",\"file\":")
			b.Write(quote(f.File))
			b.WriteString(",\"line\":")
			b.WriteString(strconv.Itoa(f.Line))
			b.WriteByte('}')
			if !more {
				break
			}
		}
	}
	b.WriteString("]}\n")
	line := b.String()
	if seen[line] {
		return
	}
	seen[line] = true
	// One open for each line: the test binaries of several packages append to one file. An
	// error of the file is ignored.
	f, err := os.OpenFile(out, os.O_WRONLY|os.O_APPEND|os.O_CREATE, 0o644)
	if err != nil {
		return
	}
	f.WriteString(line)
	f.Close()
}

// quote gives s as a JSON string.
func quote(s string) []byte {
	b, _ := json.Marshal(s)
	return b
}
`
