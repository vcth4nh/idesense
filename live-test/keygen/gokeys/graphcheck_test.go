package main

import (
	"bytes"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"testing"
)

var (
	graphCheckOnce sync.Once
	graphChecked   graphRun // gokeys graph -check on testdata/graph

	graphInnerOnce   sync.Once
	graphInnerFuncs  []GraphFunc // extractGraph with the check on testdata/graph
	graphInnerIfaces []GraphIface
	graphInnerCheck  *graphCheck
	graphInnerErr    error
)

func graphCheckResult(t *testing.T) graphRun {
	t.Helper()
	graphCheckOnce.Do(func() { graphChecked = runGraphCmd(graphTree, "-check") })
	if graphChecked.err != nil {
		t.Fatal(graphChecked.err)
	}
	return graphChecked
}

func graphChecks(t *testing.T) ([]GraphFunc, []GraphIface, *graphCheck) {
	t.Helper()
	graphInnerOnce.Do(func() {
		graphInnerFuncs, graphInnerIfaces, _, graphInnerCheck, graphInnerErr = extractGraph(graphTree, "linux", true)
	})
	if graphInnerErr != nil {
		t.Fatal(graphInnerErr)
	}
	return graphInnerFuncs, graphInnerIfaces, graphInnerCheck
}

// testdata/graph passes the check. The SSA form calls a thunk for Shape.Area(s): the check
// gives it the pairs of the interface call. The SSA side counts the three calls on a type
// parameter, and the two types that the code converts to an interface are in the type list.
func TestGraphCheckPasses(t *testing.T) {
	r := graphCheckResult(t)
	if r.code != 0 {
		t.Errorf("graph -check: exit %d\nstdout:\n%s\nstderr:\n%s", r.code, r.stdout, r.stderr)
	}
	for _, want := range []string{
		"check linux: pairs: both 22, only syntax 0, only ssa 0\n",
		": static calls 11, invoke calls of module interface methods 9, calls with no position 0, calls on a type parameter 3\n",
		"check linux: types: converted to an interface 2, of these outside the type list 0, callees that the table lacks 0, " +
			"by an instance of a generic type 0\n",
	} {
		if !strings.Contains(r.stdout, want) {
			t.Errorf("stdout has no line %q:\n%s", want, r.stdout)
		}
	}
	_, _, ch := graphChecks(t)
	g := "graph.go"
	for _, callee := range []Pos{cpos(g, 15, 13), cpos(g, 20, 15), cpos(g, 32, 14)} {
		if !ch.pairs[graphPair{file: g, line: 77, callee: callee}] {
			t.Errorf("the SSA side has no pair of Shape.Area(s) with the callee %+v", callee)
		}
	}
}

// A one-sided pair fails the check: with no entry of SizeB.Size in viaSizer, the SSA side has
// a pair that the syntax does not have.
func TestGraphCheckReportsAOneSidedPair(t *testing.T) {
	funcs, _, ch := graphChecks(t)
	sizeB := cpos("graph.go", 124, 14)
	changed := make([]GraphFunc, len(funcs))
	copy(changed, funcs)
	for i := range changed {
		if changed[i].Name == "viaSizer" {
			changed[i].Calls = slices.DeleteFunc(slices.Clone(changed[i].Calls), func(c GraphCall) bool {
				return c.Callee != nil && *c.Callee == sizeB
			})
		}
	}
	var out bytes.Buffer
	if ok := printGraphCheck(&out, changed, ch); ok {
		t.Errorf("printGraphCheck is ok with a pair that only the SSA side has:\n%s", out.String())
	}
	for _, want := range []string{
		"check linux: pairs: both 21, only syntax 0, only ssa 1\n",
		"  only ssa: graph.go:130 -> callee graph.go:124 SizeB.Size\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
}

// The check is not blind: a call after panic is dead code that SSA removes (only syntax), and a
// call through a local variable that holds a function or a method value is a static call of
// SSA with no step of the syntax (only ssa). A constant false condition stays in SSA.
func TestGraphCheckFindsDifferences(t *testing.T) {
	dir := t.TempDir()
	write := func(name, text string) {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("go.mod", "module example.com/diff\n\ngo 1.26\n")
	write("a.go", `package diff

type T struct{}

func (T) Get() int { return 1 }

func target() int { return 0 }

func deadAfterPanic() {
	panic("x")
	target()
}

func viaLocal() {
	f := target
	f()
}

func viaMethodValue(t T) {
	m := t.Get
	m()
}

func constFalse() {
	if false {
		target()
	}
}
`)
	var out, errb bytes.Buffer
	code := run([]string{"graph", "-tree", dir, "-goos", "linux", "-out", filepath.Join(dir, "graph.jsonl"), "-check"}, &out, &errb)
	if code != 1 {
		t.Errorf("exit %d, want 1; stderr: %s", code, errb.String())
	}
	for _, want := range []string{
		"check linux: pairs: both 1, only syntax 1, only ssa 2\n",
		"  only syntax: a.go:11 -> callee a.go:7 target\n",
		"  only ssa: a.go:16 -> callee a.go:7 target\n",
		"  only ssa: a.go:21 -> callee a.go:5 T.Get\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
}

// A type that the code converts to an interface is a second source of the implementers. With no
// row of the unnamed struct type of unnamedSizer, the table lacks SizeB.Size for Sizer.Size.
// Labeler.Label stays in the table through the local type sized.
func TestGraphCheckReportsALackOfTheTable(t *testing.T) {
	funcs, ifaces, ch := graphChecks(t)
	unnamed := "struct@graph.go:142:9"
	changed := make([]GraphIface, len(ifaces))
	for i, gi := range ifaces {
		changed[i] = gi
		changed[i].Methods = make([]GraphMethod, len(gi.Methods))
		for j, gm := range gi.Methods {
			changed[i].Methods[j] = gm
			changed[i].Methods[j].Impls = slices.DeleteFunc(slices.Clone(gm.Impls), func(im GraphImpl) bool { return im.Type == unnamed })
		}
	}
	without := *ch
	without.ifaces = changed
	var out bytes.Buffer
	if ok := printGraphCheck(&out, funcs, &without); ok {
		t.Errorf("printGraphCheck is ok with a callee that the table lacks:\n%s", out.String())
	}
	for _, want := range []string{
		"check linux: pairs: both 22, only syntax 0, only ssa 0\n",
		"check linux: types: converted to an interface 2, of these outside the type list 0, callees that the table lacks 1, " +
			"by an instance of a generic type 0\n",
		"  lacks: go:example.com/graph.Sizer.Size -> graph.go:124 SizeB.Size, by the type *struct{example.com/graph.SizeB; example.com/graph.Labeler}\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
	if n := strings.Count(out.String(), "  lacks: "); n != 1 {
		t.Errorf("%d lines lacks:, want 1:\n%s", n, out.String())
	}
}

// The table has no generic type (rule of a call step: a generic type gets no step). So a
// callee that only an instance of a generic type selects, as a value or behind a pointer, is
// counted apart and does not fail the check.
func TestGraphCheckCountsAGenericLackApart(t *testing.T) {
	dir := t.TempDir()
	write := func(name, text string) {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("go.mod", "module example.com/gen\n\ngo 1.26\n")
	write("a.go", `package gen

type Shape interface{ Area() int }

type Box[E any] struct{ e E }

func (Box[E]) Area() int { return 1 }

func boxValue() Shape { return Box[int]{} }

func boxPointer() Shape { return &Box[int]{} }
`)
	var out, errb bytes.Buffer
	code := run([]string{"graph", "-tree", dir, "-goos", "linux", "-out", filepath.Join(dir, "graph.jsonl"), "-check"}, &out, &errb)
	if code != 0 {
		t.Errorf("exit %d, want 0; stderr: %s\nstdout:\n%s", code, errb.String(), out.String())
	}
	for _, want := range []string{
		"check linux: types: converted to an interface 2, of these outside the type list 2, callees that the table lacks 0, " +
			"by an instance of a generic type 1\n",
		"  generic: go:example.com/gen.Shape.Area -> a.go:7 Box.Area, by the type *example.com/gen.Box[int]\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
	if strings.Contains(out.String(), "  lacks: ") {
		t.Errorf("a line lacks:\n%s", out.String())
	}
}
