package main

import (
	"bytes"
	"fmt"
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

// graphModule writes the module example.com/<name> with the file a.go of text into a temp folder
// and gives the folder.
func graphModule(t *testing.T, name, text string) string {
	t.Helper()
	dir := t.TempDir()
	for file, data := range map[string]string{"go.mod": "module example.com/" + name + "\n\ngo 1.26\n", "a.go": text} {
		if err := os.WriteFile(filepath.Join(dir, file), []byte(data), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

// runGraphCheckModule runs gokeys graph -check for linux on the module of graphModule.
func runGraphCheckModule(t *testing.T, name, text string) (code int, stdout, stderr string) {
	t.Helper()
	dir := graphModule(t, name, text)
	var out, errb bytes.Buffer
	code = run([]string{"graph", "-tree", dir, "-goos", "linux", "-out", filepath.Join(dir, "graph.jsonl"), "-check"}, &out, &errb)
	return code, out.String(), errb.String()
}

// testdata/graph passes the check. The SSA form calls a thunk for Shape.Area(s): the check
// gives it the pairs of the interface call. The SSA side counts the three calls on a type
// parameter and the call of target in the initializer of the variable initial, and the two
// types that the code converts to an interface are in the type list.
func TestGraphCheckPasses(t *testing.T) {
	r := graphCheckResult(t)
	if r.code != 0 {
		t.Errorf("graph -check: exit %d\nstdout:\n%s\nstderr:\n%s", r.code, r.stdout, r.stderr)
	}
	for _, want := range []string{
		"check linux: pairs: both 22, only syntax 0, only ssa 0\n",
		": static calls 11, invoke calls of module interface methods 9, calls with no position 0, calls on a type parameter 3, " +
			"calls from a package initializer to a function of the graph 1\n",
		"check linux: types: converted to an interface 2, of these outside the type list 0, callees that the table lacks 0, " +
			"by an instance of a generic type 0, operands with a type parameter 0\n",
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
	code, out, errs := runGraphCheckModule(t, "diff", `package diff

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
	if code != 1 {
		t.Errorf("exit %d, want 1; stderr: %s", code, errs)
	}
	for _, want := range []string{
		"check linux: pairs: both 1, only syntax 1, only ssa 2\n",
		"  only syntax: a.go:11 -> callee a.go:7 target\n",
		"  only ssa: a.go:16 -> callee a.go:7 target\n",
		"  only ssa: a.go:21 -> callee a.go:5 T.Get\n",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("no line %q:\n%s", want, out)
		}
	}
}

// A range-over-func loop over a module function calls the function with no position in SSA.
// The syntax has no call there, so the check counts the call and names its caller and callee.
// The rule of a call step does not decide such a call, so the check fails.
func TestGraphCheckFailsForACallWithNoPosition(t *testing.T) {
	code, out, errs := runGraphCheckModule(t, "rng", `package rng

func seq(yield func(int) bool) {
	yield(1)
}

func loop() int {
	n := 0
	for x := range seq {
		n += x
	}
	return n
}
`)
	if code != 1 {
		t.Errorf("exit %d, want 1; stderr: %s\nstdout:\n%s", code, errs, out)
	}
	for _, want := range []string{
		", calls with no position 1, ",
		"  no position: caller a.go:7 loop -> callee a.go:3 seq\n",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("no line %q:\n%s", want, out)
		}
	}
}

// A call in a function literal of a package-level variable belongs to the package initializer,
// an excluded caller: it gives no pair, and the check counts it.
func TestGraphCheckCountsAPackageInitializerCall(t *testing.T) {
	code, out, errs := runGraphCheckModule(t, "ini", `package ini

func target() int { return 0 }

var h = func() int { return target() }
`)
	if code != 0 {
		t.Errorf("exit %d, want 0; stderr: %s\nstdout:\n%s", code, errs, out)
	}
	for _, want := range []string{
		"check linux: pairs: both 0, only syntax 0, only ssa 0\n",
		", calls from a package initializer to a function of the graph 1\n",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("no line %q:\n%s", want, out)
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
			"by an instance of a generic type 0, operands with a type parameter 0\n",
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

// withoutTypes gives a copy of ch whose type list does not hold the types with the ids.
func withoutTypes(ch *graphCheck, ids ...string) *graphCheck {
	without := *ch
	without.types = slices.DeleteFunc(slices.Clone(ch.types), func(te *implType) bool { return slices.Contains(ids, te.id) })
	return &without
}

// A converted type of the module that the type list does not hold fails the check, and the
// check names it: here the local type sized and the unnamed struct type of unnamedSizer. The
// table still has their callees, so no lack shows them.
func TestGraphCheckReportsAModuleTypeOutsideTheTypeList(t *testing.T) {
	funcs, _, ch := graphChecks(t)
	without := withoutTypes(ch, "go:example.com/graph.sized@graph.go:133:7", "struct@graph.go:142:9")
	if len(without.types) != len(ch.types)-2 {
		t.Fatalf("the type list has %d types, want %d", len(without.types), len(ch.types)-2)
	}
	var out bytes.Buffer
	if ok := printGraphCheck(&out, funcs, without); ok {
		t.Errorf("printGraphCheck is ok with a module type outside the type list:\n%s", out.String())
	}
	for _, want := range []string{
		"check linux: types: converted to an interface 2, of these outside the type list 2, callees that the table lacks 0, " +
			"by an instance of a generic type 0, operands with a type parameter 0\n",
		"  outside: *struct{example.com/graph.SizeB; example.com/graph.Labeler}\n" +
			"  outside: example.com/graph.sized\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
}

// A library type is no type of the type list, so it is not outside the list: *bytes.Buffer
// implements the module interface Writer.
func TestGraphCheckDoesNotCountALibraryType(t *testing.T) {
	code, out, errs := runGraphCheckModule(t, "lib", `package lib

import (
	"bytes"
	"io"
)

type Writer interface{ Write(p []byte) (int, error) }

func viaWriter(w Writer) { w.Write(nil) }

func asWriter() io.Writer { return &bytes.Buffer{} }
`)
	if code != 0 {
		t.Errorf("exit %d, want 0; stderr: %s\nstdout:\n%s", code, errs, out)
	}
	want := "check linux: types: converted to an interface 1, of these outside the type list 0, callees that the table lacks 0, " +
		"by an instance of a generic type 0, operands with a type parameter 0\n"
	if !strings.Contains(out, want) {
		t.Errorf("no line %q:\n%s", want, out)
	}
	if strings.Contains(out, "  outside: ") {
		t.Errorf("a line outside:\n%s", out)
	}
}

// The lack check compares by the interface that declares the method, so it can miss a type that
// the type list lacks. D embeds J. With no X in the type list and in the table, the call d.M()
// loses the callee Base.M, but the row of J.M has Base.M through Z, and the row of D.N has
// Named.N through W: no lack. The count of the types outside the list fails the check.
func TestGraphCheckFailsForAnOutsideTypeThatTheTableHides(t *testing.T) {
	dir := graphModule(t, "emb", `package emb

type J interface{ M() }

type D interface {
	J
	N()
}

type Base struct{}

func (Base) M() {}

type Other struct{}

func (Other) M() {}

type Named struct{}

func (Named) N() {}

type Z struct{ Base }

type W struct {
	Other
	Named
}

type X struct {
	Base
	Named
}

func viaD(d D) { d.M() }

func asJ() J { return Z{} }

func asD() D { return W{} }

func asX() D { return &X{} }
`)
	funcs, ifaces, _, ch, err := extractGraph(dir, "linux", true)
	if err != nil {
		t.Fatal(err)
	}
	x := "go:example.com/emb.X"
	changed := make([]GraphIface, len(ifaces))
	removed := 0
	for i, gi := range ifaces {
		changed[i] = gi
		changed[i].Methods = make([]GraphMethod, len(gi.Methods))
		for j, gm := range gi.Methods {
			changed[i].Methods[j] = gm
			changed[i].Methods[j].Impls = slices.DeleteFunc(slices.Clone(gm.Impls), func(im GraphImpl) bool { return im.Type == x })
			removed += len(gm.Impls) - len(changed[i].Methods[j].Impls)
		}
	}
	if removed != 2 {
		t.Fatalf("%d rows of X in the table, want 2 (J.M and D.N)", removed)
	}
	without := withoutTypes(ch, x)
	without.ifaces = changed
	var out bytes.Buffer
	if ok := printGraphCheck(&out, funcs, without); ok {
		t.Errorf("printGraphCheck is ok with a module type outside the type list:\n%s", out.String())
	}
	for _, want := range []string{
		"check linux: types: converted to an interface 3, of these outside the type list 1, callees that the table lacks 0, " +
			"by an instance of a generic type 0, operands with a type parameter 0\n",
		"  outside: *example.com/emb.X\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
	if strings.Contains(out.String(), "  lacks: ") {
		t.Errorf("a line lacks:\n%s", out.String())
	}
}

// The table has no generic type (rule of a call step: a generic type gets no step). So a
// callee that only an instance of a generic type selects, as a value or behind a pointer, is
// counted apart and does not fail the check, and such an instance is not outside the type list.
// The type int is no module type, and the operand []T is counted apart. (SSA converts t of the
// type T to any with ChangeType: no operand.)
func TestGraphCheckCountsAGenericLackApart(t *testing.T) {
	code, out, errs := runGraphCheckModule(t, "gen", `package gen

type Shape interface{ Area() int }

type Box[E any] struct{ e E }

func (Box[E]) Area() int { return 1 }

func boxValue() Shape { return Box[int]{} }

func boxPointer() Shape { return &Box[int]{} }

func anyInt() any { return 1 }

func anyOf[T any](t T) any { return []T{t} }
`)
	if code != 0 {
		t.Errorf("exit %d, want 0; stderr: %s\nstdout:\n%s", code, errs, out)
	}
	for _, want := range []string{
		"check linux: types: converted to an interface 3, of these outside the type list 0, callees that the table lacks 0, " +
			"by an instance of a generic type 1, operands with a type parameter 1\n",
		"  generic: go:example.com/gen.Shape.Area -> a.go:7 Box.Area, by the type *example.com/gen.Box[int]\n",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("no line %q:\n%s", want, out)
		}
	}
	for _, label := range []string{"  lacks: ", "  outside: "} {
		if strings.Contains(out, label) {
			t.Errorf("a line %q:\n%s", label, out)
		}
	}
}

// A callee that an instance of a generic type and also another type select stays a lack.
func TestGraphCheckLackOfAGenericAndAnotherTypeIsALack(t *testing.T) {
	m, area := "go:example.com/m.Shape.Area", cpos("a.go", 5, 14)
	ch := &graphCheck{goos: "linux", pairs: map[graphPair]bool{}, selects: map[ifaceSelect]bool{
		{method: m, callee: area, typ: "example.com/m.Box[int]", generic: true}: true,
		{method: m, callee: area, typ: "example.com/m.Plain"}:                   true,
	}}
	funcs := []GraphFunc{{Name: "Area", Container: "Base", Decl: area, Calls: []GraphCall{}}}
	var out bytes.Buffer
	if ok := printGraphCheck(&out, funcs, ch); ok {
		t.Errorf("printGraphCheck is ok with a callee that the table lacks:\n%s", out.String())
	}
	for _, want := range []string{
		", callees that the table lacks 1, by an instance of a generic type 0, ",
		"  lacks: go:example.com/m.Shape.Area -> a.go:5 Base.Area, by the type example.com/m.Plain\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
	if strings.Contains(out.String(), "  generic: ") {
		t.Errorf("a line generic:\n%s", out.String())
	}
}

// printFirst20 prints at most 20 lines, and then one line with the count of the rest.
func TestPrintFirst20(t *testing.T) {
	for _, c := range []struct{ n, printed, more int }{{0, 0, 0}, {20, 20, 0}, {21, 20, 1}, {25, 20, 5}} {
		lines := make([]string, c.n)
		for i := range lines {
			lines[i] = fmt.Sprintf("line %d", i)
		}
		var out bytes.Buffer
		printFirst20(&out, "x", lines)
		want := ""
		for i := 0; i < c.printed; i++ {
			want += fmt.Sprintf("  x: line %d\n", i)
		}
		if c.more > 0 {
			want += fmt.Sprintf("  x: ... and %d more\n", c.more)
		}
		if out.String() != want {
			t.Errorf("%d lines:\n got  %q\n want %q", c.n, out.String(), want)
		}
	}
}
