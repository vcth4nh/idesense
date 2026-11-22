package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"testing"
)

// testdata/trace has a function called directly, a method called only through an interface
// value, a function called through a function value, a call inside a function literal, a
// target in a file with a comment after the package clause, a target whose body opens and
// closes on one line, a target whose brace is below its name, a caller in a _test.go file and
// one in the external test package. Each call line of a target ends with "// call of <name>".
const traceTree = "testdata/trace"

const traceImport = "example.com/trace/internal/benchtrace"

// testTarget is one entry of a targets file.
type testTarget struct {
	ID   string `json:"id"`
	File string `json:"file"`
	Line int    `json:"line"`
}

// traceTargets are the targets of testdata/trace: the id, the file and the function name. The
// id of Commented has a quote, a backslash and a newline.
var traceTargets = []struct{ id, file, name string }{
	{"go:example.com/trace.Sq.Area", "trace.go", "Area"},
	{"go:example.com/trace.Direct", "trace.go", "Direct"},
	{"go:example.com/trace.viaValue", "trace.go", "viaValue"},
	{"go:example.com/trace.lit", "trace.go", "lit"},
	{"go:example.com/trace.OneLine", "trace.go", "OneLine"},
	{"go:example.com/trace.Multi", "trace.go", "Multi"},
	{"odd \"id\" \\ \n", "comment.go", "Commented"},
}

// realTemp gives a temporary folder with no symbolic link in its path.
func realTemp(t *testing.T) string {
	t.Helper()
	dir, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return dir
}

// funcDecl gives the declaration of the function name in the file of the tree.
func funcDecl(t *testing.T, tree, file, name string) (*token.FileSet, *ast.File, *ast.FuncDecl) {
	t.Helper()
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filepath.Join(tree, file), nil, parser.SkipObjectResolution)
	if err != nil {
		t.Fatal(err)
	}
	for _, d := range f.Decls {
		if fd, ok := d.(*ast.FuncDecl); ok && fd.Name.Name == name {
			return fset, f, fd
		}
	}
	t.Fatalf("%s has no function %s", file, name)
	return nil, nil, nil
}

func declLine(t *testing.T, tree, file, name string) int {
	t.Helper()
	fset, _, fd := funcDecl(t, tree, file, name)
	return fset.Position(fd.Name.Pos()).Line
}

// mainTargets gives the targets of testdata/trace with the lines of the source.
func mainTargets(t *testing.T) []testTarget {
	t.Helper()
	var out []testTarget
	for _, tt := range traceTargets {
		out = append(out, testTarget{tt.id, tt.file, declLine(t, traceTree, tt.file, tt.name)})
	}
	return out
}

// callLine gives the file and the line of the only line of the tree that ends with
// "// call of <name>".
func callLine(t *testing.T, tree, name string) (string, int) {
	t.Helper()
	var file string
	var line int
	err := filepath.WalkDir(tree, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() || !strings.HasSuffix(path, ".go") {
			return err
		}
		b, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		for i, l := range strings.Split(string(b), "\n") {
			if strings.HasSuffix(l, "// call of "+name) {
				if file != "" {
					t.Fatalf("two lines call %s", name)
				}
				file, _ = filepath.Rel(tree, path)
				line = i + 1
			}
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if file == "" {
		t.Fatalf("no line calls %s", name)
	}
	return filepath.ToSlash(file), line
}

func writeTargets(t *testing.T, dir string, targets []testTarget) string {
	t.Helper()
	b, err := json.Marshal(targets)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "targets.json")
	if err := os.WriteFile(path, b, 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

type traceCmd struct {
	code           int
	stdout, stderr string
}

func runTrace(args ...string) traceCmd {
	var stdout, stderr bytes.Buffer
	code := run(append([]string{"trace"}, args...), &stdout, &stderr)
	return traceCmd{code, stdout.String(), stderr.String()}
}

// envWithout gives the environment of the test with no variable key.
func envWithout(key string) []string {
	var env []string
	for _, kv := range os.Environ() {
		if !strings.HasPrefix(kv, key+"=") {
			env = append(env, kv)
		}
	}
	return env
}

// goTool runs the go command in dir with env.
func goTool(dir string, env []string, args ...string) (string, error) {
	cmd := exec.Command("go", args...)
	cmd.Dir = dir
	cmd.Env = append(env, "PWD="+dir)
	out, err := cmd.CombinedOutput()
	return string(out), err
}

type fileEntry struct {
	mode fs.FileMode
	data string // the content of a file, the target of a link, "" for a folder
}

// snapshot gives each file, link and folder below root, by its relative path.
func snapshot(t *testing.T, root string) map[string]fileEntry {
	t.Helper()
	out := map[string]fileEntry{}
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil || path == root {
			return err
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		info, err := os.Lstat(path)
		if err != nil {
			return err
		}
		e := fileEntry{mode: info.Mode()}
		switch {
		case info.Mode()&fs.ModeSymlink != 0:
			e.data, err = os.Readlink(path)
		case info.Mode().IsRegular():
			var b []byte
			b, err = os.ReadFile(path)
			e.data = string(b)
		}
		out[filepath.ToSlash(rel)] = e
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}

type traceFrame struct {
	Func string `json:"func"`
	File string `json:"file"`
	Line int    `json:"line"`
}

type traceLine struct {
	ID     string       `json:"id"`
	Frames []traceFrame `json:"frames"`
}

// readTrace decodes the trace file (an unknown field is an error) and checks that no line
// comes two times.
func readTrace(t *testing.T, path string) []traceLine {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var out []traceLine
	seen := map[string]bool{}
	sc := bufio.NewScanner(bytes.NewReader(b))
	for sc.Scan() {
		if seen[sc.Text()] {
			t.Errorf("the line comes two times: %s", sc.Text())
		}
		seen[sc.Text()] = true
		dec := json.NewDecoder(bytes.NewReader(sc.Bytes()))
		dec.DisallowUnknownFields()
		var l traceLine
		if err := dec.Decode(&l); err != nil {
			t.Fatalf("%v: %s", err, sc.Text())
		}
		out = append(out, l)
	}
	if err := sc.Err(); err != nil {
		t.Fatal(err)
	}
	return out
}

// editedSource gives the expected text of a file of the copy: the import after the package
// name and the call of Hit after the opening brace of each target of the file.
func editedSource(t *testing.T, tree, file string, targets []struct{ id, file, name string }) (string, map[int]bool) {
	t.Helper()
	src, err := os.ReadFile(filepath.Join(tree, file))
	if err != nil {
		t.Fatal(err)
	}
	type ins struct {
		off  int
		text string
	}
	var list []ins
	changed := map[int]bool{}
	for _, tt := range targets {
		if tt.file != file {
			continue
		}
		fset, f, fd := funcDecl(t, tree, file, tt.name)
		if len(list) == 0 {
			p := fset.Position(f.Name.End())
			list = append(list, ins{p.Offset, `; import benchtrace_ "` + traceImport + `"`})
			changed[p.Line] = true
		}
		p := fset.Position(fd.Body.Lbrace)
		list = append(list, ins{p.Offset + 1, "benchtrace_.Hit(" + strconv.Quote(tt.id) + "); "})
		changed[p.Line] = true
	}
	out := string(src)
	for i := len(list) - 1; i >= 0; i-- {
		// The offsets grow with the index: the package name comes first, and the targets are
		// in the order of the file.
		if i > 0 && list[i].off < list[i-1].off {
			t.Fatalf("the targets of %s are not in the order of the file", file)
		}
		out = out[:list[i].off] + list[i].text + out[list[i].off:]
	}
	return out, changed
}

// The copy of testdata/trace: the files, the lines of the edited files, the trace of the test
// suite of the copy, the run with no BENCH_TRACE_OUT, and a second copy.
func TestTraceCopyLogsTheCallers(t *testing.T) {
	tmp := realTemp(t)
	targetsFile := writeTargets(t, tmp, mainTargets(t))
	dst := filepath.Join(tmp, "copy")
	r := runTrace("-tree", traceTree, "-targets", targetsFile, "-dst", dst)
	if r.code != 0 {
		t.Fatalf("exit %d\nstdout:\n%s\nstderr:\n%s", r.code, r.stdout, r.stderr)
	}
	for _, want := range []string{"targets: 7\n", "edited files: 2\n", "folder: " + dst + "\n", "time: "} {
		if !strings.Contains(r.stdout, want) {
			t.Errorf("stdout has no %q:\n%s", want, r.stdout)
		}
	}

	t.Run("files", func(t *testing.T) {
		orig, cp := snapshot(t, traceTree), snapshot(t, dst)
		gen, ok := cp["internal/benchtrace/benchtrace.go"]
		if !ok {
			t.Fatal("the copy has no internal/benchtrace/benchtrace.go")
		}
		for _, want := range []string{"package benchtrace\n", "const depth = 6\n", "func Hit(id string) {\n"} {
			if !strings.Contains(gen.data, want) {
				t.Errorf("benchtrace.go has no %q", want)
			}
		}
		for _, name := range []string{"internal", "internal/benchtrace", "internal/benchtrace/benchtrace.go"} {
			delete(cp, name)
		}
		for rel, o := range orig {
			c, ok := cp[rel]
			switch {
			case !ok:
				t.Errorf("the copy has no %s", rel)
			case o.mode.IsDir() != c.mode.IsDir():
				t.Errorf("%s: mode %v in the tree, %v in the copy", rel, o.mode, c.mode)
			case rel == "trace.go" || rel == "comment.go":
			case o != c:
				t.Errorf("%s: the copy differs from the tree", rel)
			}
		}
		for rel := range cp {
			if _, ok := orig[rel]; !ok {
				t.Errorf("the copy has an extra %s", rel)
			}
		}
	})

	t.Run("lines", func(t *testing.T) {
		for _, file := range []string{"trace.go", "comment.go"} {
			want, changed := editedSource(t, traceTree, file, traceTargets)
			gotB, err := os.ReadFile(filepath.Join(dst, file))
			if err != nil {
				t.Fatal(err)
			}
			got := string(gotB)
			if got != want {
				t.Errorf("%s of the copy:\n%s\nwant:\n%s", file, got, want)
			}
			origB, err := os.ReadFile(filepath.Join(traceTree, file))
			if err != nil {
				t.Fatal(err)
			}
			ol, gl := strings.Split(string(origB), "\n"), strings.Split(got, "\n")
			if len(ol) != len(gl) {
				t.Errorf("%s: %d lines in the tree, %d in the copy", file, len(ol), len(gl))
				continue
			}
			for i := range ol {
				if (ol[i] != gl[i]) != changed[i+1] {
					t.Errorf("%s:%d: changed %v, want %v: %q -> %q", file, i+1, ol[i] != gl[i], changed[i+1], ol[i], gl[i])
				}
			}
		}
		// The brace of Multi is two lines below its name, and the package line of comment.go
		// keeps its comment after the import.
		_, changed := editedSource(t, traceTree, "trace.go", traceTargets)
		if !changed[declLine(t, traceTree, "trace.go", "Multi")+2] {
			t.Errorf("the brace line of Multi is not changed")
		}
		got, _ := os.ReadFile(filepath.Join(dst, "comment.go"))
		wantLine := `package trace; import benchtrace_ "` + traceImport + `" // the package clause has a comment after it` + "\n"
		if !strings.HasPrefix(string(got), wantLine) {
			t.Errorf("comment.go starts with %q, want %q", strings.SplitAfter(string(got), "\n")[0], wantLine)
		}
	})

	t.Run("trace", func(t *testing.T) {
		out := filepath.Join(tmp, "trace.jsonl")
		if o, err := goTool(dst, append(envWithout("BENCH_TRACE_OUT"), "BENCH_TRACE_OUT="+out), "test", "-count=1", "./..."); err != nil {
			t.Fatalf("go test in the copy: %v\n%s", err, o)
		}
		lines := readTrace(t, out)
		byID := map[string][]traceLine{}
		for _, l := range lines {
			byID[l.ID] = append(byID[l.ID], l)
			if len(l.Frames) == 0 || len(l.Frames) > 6 {
				t.Errorf("%q: %d frames", l.ID, len(l.Frames))
			}
			for _, f := range l.Frames {
				if !filepath.IsAbs(f.File) {
					t.Errorf("%q: the frame file %s is not absolute", l.ID, f.File)
				}
			}
		}
		// The first frame of each target: the function, the file and the line of the call.
		funcs := map[string]string{
			"Area":      "example.com/trace.Total",
			"Direct":    "example.com/trace.CallDirect",
			"viaValue":  "example.com/trace.apply",
			"lit":       "example.com/trace.InLiteral.func1",
			"OneLine":   "example.com/trace.TestCalls",
			"Multi":     "example.com/trace.TestCalls",
			"Commented": "example.com/trace_test.TestCommented",
		}
		for _, tt := range traceTargets {
			file, line := callLine(t, traceTree, tt.name)
			want := traceFrame{funcs[tt.name], filepath.Join(dst, filepath.FromSlash(file)), line}
			var firsts []traceFrame
			found := false
			for _, l := range byID[tt.id] {
				firsts = append(firsts, l.Frames[0])
				found = found || l.Frames[0] == want
			}
			if !found {
				t.Errorf("%s: no line with the first frame %+v; first frames %+v", tt.name, want, firsts)
			}
		}
		// The loop calls CallDirect three times from one line: one call stack, one line.
		if n := len(byID["go:example.com/trace.Direct"]); n != 1 {
			t.Errorf("Direct has %d lines, want 1", n)
		}
		if len(byID) != len(traceTargets) {
			t.Errorf("the trace has %d ids, want %d", len(byID), len(traceTargets))
		}
	})

	t.Run("unset", func(t *testing.T) {
		before, beforeTmp := snapshot(t, dst), snapshot(t, tmp)
		if o, err := goTool(dst, envWithout("BENCH_TRACE_OUT"), "test", "-count=1", "./..."); err != nil {
			t.Fatalf("go test in the copy: %v\n%s", err, o)
		}
		if after := snapshot(t, dst); !reflect.DeepEqual(after, before) {
			t.Errorf("the run with no BENCH_TRACE_OUT changed the copy")
		}
		if after := snapshot(t, tmp); !reflect.DeepEqual(after, beforeTmp) {
			t.Errorf("the run with no BENCH_TRACE_OUT changed the folder of the copy")
		}
	})

	t.Run("two runs equal", func(t *testing.T) {
		dst2 := filepath.Join(tmp, "copy2")
		r2 := runTrace("-tree", traceTree, "-targets", targetsFile, "-dst", dst2)
		if r2.code != 0 {
			t.Fatalf("exit %d\nstderr:\n%s", r2.code, r2.stderr)
		}
		if a, b := snapshot(t, dst), snapshot(t, dst2); !reflect.DeepEqual(a, b) {
			t.Errorf("two runs give different files:\n%v\n%v", a, b)
		}
	})
}

// -depth sets the constant of the generated file and the count of frames of a line.
func TestTraceDepth(t *testing.T) {
	tmp := realTemp(t)
	dst := filepath.Join(tmp, "copy")
	r := runTrace("-tree", traceTree, "-targets", writeTargets(t, tmp, mainTargets(t)), "-dst", dst, "-depth", "2", "-no-check")
	if r.code != 0 {
		t.Fatalf("exit %d\nstderr:\n%s", r.code, r.stderr)
	}
	gen, err := os.ReadFile(filepath.Join(dst, "internal", "benchtrace", "benchtrace.go"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(gen), "const depth = 2\n") {
		t.Errorf("benchtrace.go has no depth 2")
	}
	out := filepath.Join(tmp, "trace.jsonl")
	if o, err := goTool(dst, append(envWithout("BENCH_TRACE_OUT"), "BENCH_TRACE_OUT="+out), "test", "-count=1", "./..."); err != nil {
		t.Fatalf("go test in the copy: %v\n%s", err, o)
	}
	two := 0
	for _, l := range readTrace(t, out) {
		if len(l.Frames) > 2 {
			t.Errorf("%q: %d frames", l.ID, len(l.Frames))
		}
		if len(l.Frames) == 2 {
			two++
		}
	}
	if two == 0 {
		t.Errorf("no line has 2 frames")
	}
}

// writeTree writes the files (relative path: text) below a new temporary folder. A text that
// starts with "-> " makes a symbolic link to the rest of the text.
func writeTree(t *testing.T, files map[string]string) string {
	t.Helper()
	dir := realTemp(t)
	for rel, text := range files {
		path := filepath.Join(dir, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		var err error
		if link, ok := strings.CutPrefix(text, "-> "); ok {
			err = os.Symlink(link, path)
		} else {
			err = os.WriteFile(path, []byte(text), 0o644)
		}
		if err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

const errGoMod = "module example.com/e\n\ngo 1.26\n"

// errBase is a.go of the error trees: F at line 5 and G at line 9.
const errBase = `package e

type T struct{}

func F() int {
	return 1
}

func G() int {
	return F()
}
`

// Each error of the command. A target error and a tree error come before a file of -dst is
// written; a check error comes after the copy.
func TestTraceErrors(t *testing.T) {
	f5 := []testTarget{{"f", "a.go", 5}}
	cases := []struct {
		name    string
		files   map[string]string
		targets []testTarget
		args    []string
		dstMade bool
		want    string
	}{
		{"no function at the position", nil, []testTarget{{"t", "a.go", 3}}, nil, false,
			`target "t": no function declaration has its name at a.go:3`},
		{"a function with no body", map[string]string{"b.go": "package e\n\nfunc NoBody()\n"},
			[]testTarget{{"n", "b.go", 3}}, nil, false, `target "n": the function NoBody at b.go:3 has no body`},
		{"a file that does not parse", map[string]string{"c.go": "package e\n\nfunc Broken( {\n"},
			[]testTarget{{"c", "c.go", 3}}, nil, false, `target "c": c.go does not parse`},
		{"a missing file", nil, []testTarget{{"m", "none.go", 3}}, nil, false, `target "m": none.go:`},
		{"a target above the tree", nil, []testTarget{{"o", "../a.go", 5}}, nil, false,
			`target "o": the file ../a.go is outside the tree`},
		{"an absolute target", nil, []testTarget{{"o", "/etc/hostname", 1}}, nil, false,
			`target "o": the file /etc/hostname is outside the tree`},
		{"a target through a link", map[string]string{"l.go": "-> a.go"}, []testTarget{{"l", "l.go", 5}}, nil, false,
			`target "l": the file l.go is a symbolic link or below one`},
		{"no go.mod", map[string]string{"go.mod": ""}, f5, nil, false, "no go.mod with a module line at the tree root"},
		{"no module line", map[string]string{"go.mod": "go 1.26\n"}, f5, nil, false,
			"no go.mod with a module line at the tree root"},
		{"two targets with one id", nil, []testTarget{{"x", "a.go", 5}, {"x", "a.go", 9}}, nil, false,
			`the id "x" comes two times`},
		{"two targets at one position", nil, []testTarget{{"x", "a.go", 5}, {"y", "./a.go", 5}}, nil, false,
			`the targets "x" and "y" have one position a.go:5`},
		{"an existing benchtrace folder", map[string]string{"internal/benchtrace/keep.txt": "x\n"}, f5, nil, false,
			"the tree already has internal/benchtrace"},
		{"a linked internal folder", map[string]string{"real/x.txt": "x\n", "internal": "-> real"}, f5, nil, false,
			"internal of the tree is no folder (a symbolic link or a file)"},
		{"a file with the identifier", map[string]string{"d.go": "package e\n\nvar benchtrace_ = 1\n\nfunc D() {}\n"},
			[]testTarget{{"d", "d.go", 5}}, nil, false, "d.go already has the identifier benchtrace_"},
		{"a build failure", map[string]string{"e.go": "package e\n\nvar benchtrace_ = 0\n"}, f5, nil, true,
			"go build ./... failed"},
		{"a test build failure", map[string]string{"e_test.go": "package e\n\nvar benchtrace_ = 0\n"}, f5, nil, true,
			"go test -count=1 -run ^$ ./... failed"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			files := map[string]string{"go.mod": errGoMod, "a.go": errBase}
			for k, v := range tc.files {
				files[k] = v
			}
			if v, ok := files["go.mod"]; ok && v == "" {
				delete(files, "go.mod")
			}
			tree := writeTree(t, files)
			tmp := realTemp(t)
			dst := filepath.Join(tmp, "copy")
			before := snapshot(t, tree)
			r := runTrace(append([]string{"-tree", tree, "-targets", writeTargets(t, tmp, tc.targets), "-dst", dst}, tc.args...)...)
			if r.code != 1 {
				t.Errorf("exit %d, want 1\nstdout:\n%s\nstderr:\n%s", r.code, r.stdout, r.stderr)
			}
			if !strings.Contains(r.stderr, tc.want) {
				t.Errorf("stderr has no %q:\n%s", tc.want, r.stderr)
			}
			_, err := os.Lstat(dst)
			if made := err == nil; made != tc.dstMade {
				t.Errorf("the folder -dst exists: %v, want %v", made, tc.dstMade)
			}
			if !reflect.DeepEqual(snapshot(t, tree), before) {
				t.Errorf("the command changed the tree")
			}
		})
	}
}

// The output of the Go tool is in the error of a check, and -no-check skips the two checks.
func TestTraceCheckOutputAndNoCheck(t *testing.T) {
	for _, name := range []string{"e.go", "e_test.go"} {
		tree := writeTree(t, map[string]string{"go.mod": errGoMod, "a.go": errBase, name: "package e\n\nvar benchtrace_ = 0\n"})
		tmp := realTemp(t)
		targets := writeTargets(t, tmp, []testTarget{{"f", "a.go", 5}})
		r := runTrace("-tree", tree, "-targets", targets, "-dst", filepath.Join(tmp, "copy"))
		if r.code != 1 || !strings.Contains(r.stderr, "benchtrace_") || !strings.Contains(r.stderr, name) {
			t.Errorf("%s: exit %d, want 1 and the output of the Go tool:\n%s", name, r.code, r.stderr)
		}
		r = runTrace("-tree", tree, "-targets", targets, "-dst", filepath.Join(tmp, "copy2"), "-no-check")
		if r.code != 0 {
			t.Errorf("%s with -no-check: exit %d\n%s", name, r.code, r.stderr)
		}
	}
}

// An existing -dst, a -dst in the tree and the usage errors.
func TestTraceDstAndUsage(t *testing.T) {
	tree := writeTree(t, map[string]string{"go.mod": errGoMod, "a.go": errBase})
	tmp := realTemp(t)
	targets := writeTargets(t, tmp, []testTarget{{"f", "a.go", 5}})
	if err := os.Mkdir(filepath.Join(tmp, "there"), 0o755); err != nil {
		t.Fatal(err)
	}
	before := snapshot(t, tree)
	for _, tc := range []struct {
		dst, want string
	}{
		{filepath.Join(tmp, "there"), "exists"},
		{filepath.Join(tree, "copy"), "is inside the tree"},
		{filepath.Join(tmp, "no", "copy"), "the parent folder of -dst"},
	} {
		r := runTrace("-tree", tree, "-targets", targets, "-dst", tc.dst, "-no-check")
		if r.code != 1 || !strings.Contains(r.stderr, tc.want) {
			t.Errorf("-dst %s: exit %d, want 1 and %q:\n%s", tc.dst, r.code, tc.want, r.stderr)
		}
	}
	if !reflect.DeepEqual(snapshot(t, tree), before) {
		t.Errorf("the command changed the tree")
	}
	for _, args := range [][]string{
		{"-tree", tree, "-targets", targets},
		{"-tree", tree, "-dst", filepath.Join(tmp, "c")},
		{"-targets", targets, "-dst", filepath.Join(tmp, "c")},
		{"-tree", tree, "-targets", targets, "-dst", filepath.Join(tmp, "c"), "-depth", "0"},
		{"-tree", tree, "-targets", targets, "-dst", filepath.Join(tmp, "c"), "extra"},
	} {
		if r := runTrace(args...); r.code != 2 {
			t.Errorf("%v: exit %d, want 2", args, r.code)
		}
	}
}

// The copy has each file and folder of the tree but no .git folder, a link stays a link, and a
// file keeps its mode.
func TestTraceCopiesTheTree(t *testing.T) {
	tree := writeTree(t, map[string]string{
		"go.mod":          errGoMod,
		"a.go":            errBase,
		".git/HEAD":       "ref\n",
		"sub/.git/config": "x\n",
		"sub/x.txt":       "x\n",
		"link":            "-> sub/x.txt",
		"run.sh":          "#!/bin/sh\n",
	})
	if err := os.Chmod(filepath.Join(tree, "run.sh"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(tree, "empty"), 0o755); err != nil {
		t.Fatal(err)
	}
	tmp := realTemp(t)
	dst := filepath.Join(tmp, "copy")
	r := runTrace("-tree", tree, "-targets", writeTargets(t, tmp, []testTarget{{"f", "a.go", 5}}), "-dst", dst, "-no-check")
	if r.code != 0 {
		t.Fatalf("exit %d\n%s", r.code, r.stderr)
	}
	got := snapshot(t, dst)
	var names []string
	for rel := range got {
		names = append(names, rel)
	}
	want := []string{"a.go", "empty", "go.mod", "internal", "internal/benchtrace", "internal/benchtrace/benchtrace.go",
		"link", "run.sh", "sub", "sub/x.txt"}
	sort.Strings(names)
	if !reflect.DeepEqual(names, want) {
		t.Errorf("the copy has %v, want %v", names, want)
	}
	if e := got["link"]; e.mode&fs.ModeSymlink == 0 || e.data != "sub/x.txt" {
		t.Errorf("link: mode %v, target %q", e.mode, e.data)
	}
	if e := got["run.sh"]; e.mode.Perm() != 0o755 {
		t.Errorf("run.sh: mode %v", e.mode)
	}
	if e := got["empty"]; !e.mode.IsDir() {
		t.Errorf("empty: mode %v", e.mode)
	}
}
