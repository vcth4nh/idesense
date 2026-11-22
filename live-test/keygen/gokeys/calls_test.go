package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"sync"
	"testing"
)

// testdata/calls has one example of each call form (calls.go), a function and its caller in
// a _windows.go file, a caller in a _test.go file of the package and one in the external test
// package.
const callsTree = "testdata/calls"

type callsRun struct {
	code           int
	stdout, stderr string
	data           []byte
	recs           []CallRecord
	err            error
}

// runCallsCmd runs gokeys calls on tree for linux and windows through the command line entry
// and decodes the output file (an unknown field is an error).
func runCallsCmd(tree string, extra ...string) callsRun {
	dir, err := os.MkdirTemp("", "gokeys-calls-test-")
	if err != nil {
		return callsRun{err: err}
	}
	defer os.RemoveAll(dir)
	out := filepath.Join(dir, "calls.jsonl")
	var stdout, stderr bytes.Buffer
	args := append([]string{"calls", "-tree", tree, "-configs", "linux,windows", "-out", out}, extra...)
	r := callsRun{code: run(args, &stdout, &stderr)}
	r.stdout, r.stderr = stdout.String(), stderr.String()
	if r.data, r.err = os.ReadFile(out); r.err != nil {
		r.err = fmt.Errorf("%w (exit %d, stderr %s)", r.err, r.code, r.stderr)
		return r
	}
	sc := bufio.NewScanner(bytes.NewReader(r.data))
	sc.Buffer(make([]byte, 1<<20), 1<<26)
	for sc.Scan() {
		dec := json.NewDecoder(bytes.NewReader(sc.Bytes()))
		dec.DisallowUnknownFields()
		var rec CallRecord
		if r.err = dec.Decode(&rec); r.err != nil {
			return r
		}
		r.recs = append(r.recs, rec)
	}
	r.err = sc.Err()
	return r
}

var (
	callsOnce    sync.Once
	callsChecked callsRun // gokeys calls -check on testdata/calls

	callsInnerOnce sync.Once
	callsInner     []*ssaCheck // the check results of extractCalls, by configuration
	callsInnerRecs []CallRecord
	callsInnerErr  error
)

func callsResult(t *testing.T) callsRun {
	t.Helper()
	callsOnce.Do(func() { callsChecked = runCallsCmd(callsTree, "-check") })
	if callsChecked.err != nil {
		t.Fatal(callsChecked.err)
	}
	return callsChecked
}

func callsChecks(t *testing.T) ([]CallRecord, []*ssaCheck) {
	t.Helper()
	callsInnerOnce.Do(func() {
		callsInnerRecs, _, callsInner, callsInnerErr = extractCalls(callsTree, both, true)
	})
	if callsInnerErr != nil {
		t.Fatal(callsInnerErr)
	}
	return callsInnerRecs, callsInner
}

func cpos(file string, line, col int) Pos { return Pos{File: file, Line: line, Col: col} }

func callRec(t *testing.T, recs []CallRecord, decl Pos) CallRecord {
	t.Helper()
	for _, r := range recs {
		if r.Decl == decl {
			return r
		}
	}
	t.Fatalf("no record at %+v", decl)
	return CallRecord{}
}

func use(file string, line, col int, call bool, in *Pos, lit bool, configs []string) CallUse {
	return CallUse{File: file, Line: line, Col: col, Call: call, In: in, Lit: lit, Configs: configs}
}

func at(file string, line, col int) *Pos { p := cpos(file, line, col); return &p }

func fmtUses(us []CallUse) string {
	var b strings.Builder
	for _, u := range us {
		in := "null"
		if u.In != nil {
			in = fmt.Sprintf("%s:%d:%d", u.In.File, u.In.Line, u.In.Col)
		}
		fmt.Fprintf(&b, "\n   %s:%d:%d call %v in %s lit %v %v", u.File, u.Line, u.Col, u.Call, in, u.Lit, u.Configs)
	}
	return b.String()
}

func checkUses(t *testing.T, recs []CallRecord, decl Pos, want []CallUse) {
	t.Helper()
	r := callRec(t, recs, decl)
	if r.Uses == nil {
		t.Errorf("%s: uses is null, want a list", r.Name)
	}
	if !reflect.DeepEqual(r.Uses, want) && !(len(r.Uses) == 0 && len(want) == 0) {
		t.Errorf("%s uses:\n got  %s\n want %s", r.Name, fmtUses(r.Uses), fmtUses(want))
	}
}

const callsPkg = "go:example.com/calls."

// The records by decl, with the id, the kind, the name, the container, the last line and the
// configurations.
func TestCallsRecordSet(t *testing.T) {
	r := callsResult(t)
	type head struct {
		Decl                      Pos
		ID, Kind, Name, Container string
		End                       int
		Configs                   []string
	}
	var got []head
	for _, rec := range r.recs {
		if rec.Lang != "go" {
			t.Errorf("%s: lang %q", rec.Name, rec.Lang)
		}
		got = append(got, head{rec.Decl, rec.ID, rec.Kind, rec.Name, rec.Container, rec.End, rec.Configs})
	}
	c := "calls.go"
	want := []head{
		{cpos(c, 7, 13), callsPkg + "Base.Area", "method", "Area", "Base", 7, both},
		{cpos(c, 15, 12), callsPkg + "T.Get", "method", "Get", "T", 15, both},
		{cpos(c, 17, 13), callsPkg + "T.Set", "method", "Set", "T", 17, both},
		{cpos(c, 25, 17), callsPkg + "Box.Val", "method", "Val", "Box", 25, both},
		{cpos(c, 27, 6), callsPkg + "plain", "func", "plain", "", 27, both},
		{cpos(c, 29, 6), callsPkg + "spawned", "func", "spawned", "", 29, both},
		{cpos(c, 31, 6), callsPkg + "deferred", "func", "deferred", "", 31, both},
		{cpos(c, 33, 6), callsPkg + "wrapped", "func", "wrapped", "", 33, both},
		{cpos(c, 35, 6), callsPkg + "apply", "func", "apply", "", 35, both},
		{cpos(c, 37, 6), callsPkg + "generic", "func", "generic", "", 37, both},
		{cpos(c, 40, 6), callsPkg + "Exported", "func", "Exported", "", 40, both},
		{cpos(c, 42, 6), callsPkg + "callers", "func", "callers", "", 58, both},
		{cpos(c, 60, 6), callsPkg + "inLiteral", "func", "inLiteral", "", 62, both},
		{cpos(c, 71, 6), "", "func", "init", "", 71, both},
		{cpos(c, 73, 6), "", "func", "_", "", 73, both},
		{cpos("calls_test.go", 5, 6), callsPkg + "TestPlain", "func", "TestPlain", "", 5, both},
		{cpos("calls_windows.go", 4, 6), callsPkg + "onWindows", "func", "onWindows", "", 4, windows},
		{cpos("calls_windows.go", 6, 6), callsPkg + "winCaller", "func", "winCaller", "", 6, windows},
		{cpos("ext_test.go", 9, 6), "go:example.com/calls_test.TestExported", "func", "TestExported", "", 9, both},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("records:\n got  %+v\n want %+v", got, want)
	}
}

// The field names and their order in the file, for a record and for a use.
func TestCallsLineShape(t *testing.T) {
	r := callsResult(t)
	lines := strings.Split(strings.TrimSuffix(string(r.data), "\n"), "\n")
	var winCaller string
	for _, l := range lines {
		if strings.Contains(l, `"name":"winCaller"`) {
			winCaller = l
		}
	}
	want := `{"id":"go:example.com/calls.winCaller","lang":"go","kind":"func","name":"winCaller","container":"",` +
		`"decl":{"file":"calls_windows.go","line":6,"col":6},"end":6,"configs":["windows"],"uses":[]}`
	if winCaller != want {
		t.Errorf("winCaller line:\n got  %s\n want %s", winCaller, want)
	}
	var onWindows string
	for _, l := range lines {
		if strings.Contains(l, `"name":"onWindows"`) {
			onWindows = l
		}
	}
	wantUse := `"uses":[{"file":"calls_windows.go","line":6,"col":31,"call":true,` +
		`"in":{"file":"calls_windows.go","line":6,"col":6},"lit":false,"configs":["windows"]}]}`
	if !strings.HasSuffix(onWindows, wantUse) {
		t.Errorf("onWindows line:\n got  %s\n want the end %s", onWindows, wantUse)
	}
}

func TestCallsPlainMethodAndPromotedCalls(t *testing.T) {
	r := callsResult(t)
	c := "calls.go"
	callers := at(c, 42, 6)
	// Each use of plain: a plain call, in a literal in a function, in the initializer of a
	// package-level variable, in a literal there, in init, in a _test.go file and in a
	// _windows.go file.
	checkUses(t, r.recs, cpos(c, 27, 6), []CallUse{
		use(c, 43, 2, true, callers, false, both),
		use(c, 61, 11, true, at(c, 60, 6), true, both),
		use(c, 64, 15, true, nil, false, both),
		use(c, 66, 38, true, nil, true, both),
		use(c, 71, 15, true, at(c, 71, 6), false, both),
		use("calls_test.go", 5, 32, true, at("calls_test.go", 5, 6), false, both),
		use("calls_windows.go", 4, 31, true, at("calls_windows.go", 4, 6), false, windows),
	})
	// T.Get: a method call, the method expression T.Get(t) and the method value t.Get. The
	// call g.Get() through the interface Getter (line 56) is no use of T.Get.
	checkUses(t, r.recs, cpos(c, 15, 12), []CallUse{
		use(c, 44, 4, true, callers, false, both),
		use(c, 46, 4, true, callers, false, both),
		use(c, 48, 10, false, callers, false, both),
	})
	// (*T).Set(&t, 2): a method expression with parentheses.
	checkUses(t, r.recs, cpos(c, 17, 13), []CallUse{use(c, 47, 7, true, callers, false, both)})
	// o.Area() selects the method that Outer promotes from Base.
	checkUses(t, r.recs, cpos(c, 7, 13), []CallUse{use(c, 45, 4, true, callers, false, both)})
	// Exported as an argument, and its call in the external test package.
	checkUses(t, r.recs, cpos(c, 40, 6), []CallUse{
		use(c, 49, 8, false, callers, false, both),
		use("ext_test.go", 9, 41, true, at("ext_test.go", 9, 6), false, both),
	})
	checkUses(t, r.recs, cpos(c, 35, 6), []CallUse{
		use(c, 48, 2, true, callers, false, both),
		use(c, 49, 2, true, callers, false, both),
	})
}

func TestCallsGoDeferParenGeneric(t *testing.T) {
	r := callsResult(t)
	c := "calls.go"
	callers := at(c, 42, 6)
	checkUses(t, r.recs, cpos(c, 29, 6), []CallUse{use(c, 50, 5, true, callers, false, both)})
	checkUses(t, r.recs, cpos(c, 31, 6), []CallUse{use(c, 51, 8, true, callers, false, both)})
	// (wrapped)(6), and the call in the function with the name _.
	checkUses(t, r.recs, cpos(c, 33, 6), []CallUse{
		use(c, 52, 3, true, callers, false, both),
		use(c, 73, 12, true, at(c, 73, 6), false, both),
	})
	// generic[int](7) and generic(8); Box[int]{}.Val() resolves to the method of the origin.
	checkUses(t, r.recs, cpos(c, 37, 6), []CallUse{
		use(c, 53, 2, true, callers, false, both),
		use(c, 54, 2, true, callers, false, both),
	})
	checkUses(t, r.recs, cpos(c, 25, 17), []CallUse{use(c, 55, 13, true, callers, false, both)})
}

// No record has a use at the conversion T(t) (line 57) or at the call through the interface
// (line 56), and a definition is no use.
func TestCallsNoUseForConversionInterfaceOrDefinition(t *testing.T) {
	r := callsResult(t)
	for _, rec := range r.recs {
		for _, u := range rec.Uses {
			if u.File == "calls.go" && (u.Line == 56 || u.Line == 57) {
				t.Errorf("%s has a use at %s:%d:%d", rec.Name, u.File, u.Line, u.Col)
			}
			if u.File == rec.Decl.File && u.Line == rec.Decl.Line && u.Col == rec.Decl.Col {
				t.Errorf("%s: the definition is a use", rec.Name)
			}
		}
	}
	for _, d := range []Pos{cpos("calls.go", 42, 6), cpos("calls.go", 60, 6), cpos("calls.go", 71, 6)} {
		checkUses(t, r.recs, d, nil)
	}
}

func TestCallsWindowsFile(t *testing.T) {
	r := callsResult(t)
	w := "calls_windows.go"
	checkUses(t, r.recs, cpos(w, 4, 6), []CallUse{use(w, 6, 31, true, at(w, 6, 6), false, windows)})
}

// The counts of the command output, and two runs give equal bytes.
func TestCallsOutputAndTwoRunsEqual(t *testing.T) {
	r := callsResult(t)
	for _, want := range []string{
		`records: 19, with id "" 2` + "\n",
		"uses: 24, call false 2, in null 2, lit true 2\n",
	} {
		if !strings.Contains(r.stdout, want) {
			t.Errorf("stdout has no line %q:\n%s", want, r.stdout)
		}
	}
	again := runCallsCmd(callsTree)
	if again.err != nil {
		t.Fatal(again.err)
	}
	if again.code != 0 {
		t.Errorf("calls without -check: exit %d: %s", again.code, again.stderr)
	}
	if !bytes.Equal(again.data, r.data) {
		t.Errorf("two runs give different files:\n%s\n---\n%s", r.data, again.data)
	}
}

// The id, the kind, the name, the container and the decl are those of gokeys extract; a
// record with the id "" has no extract record, and each function and method record of
// extract has a calls record.
func TestCallsIDsAreThoseOfExtract(t *testing.T) {
	r := callsResult(t)
	ek, _, err := extractTree(callsTree)
	if err != nil {
		t.Fatal(err)
	}
	byID := map[string]bool{}
	for _, rec := range r.recs {
		if rec.ID == "" {
			for _, e := range ek {
				if e.Decl == rec.Decl {
					t.Errorf("%s at %+v has the id \"\", extract has %s", rec.Name, rec.Decl, e.ID)
				}
			}
			continue
		}
		byID[rec.ID] = true
		e, ok := ek[rec.ID]
		if !ok {
			t.Errorf("%s: no extract record", rec.ID)
			continue
		}
		if e.Kind != rec.Kind || e.Name != rec.Name || e.Container != rec.Container || e.Decl != rec.Decl {
			t.Errorf("%s: extract %s %s %s %+v, calls %s %s %s %+v", rec.ID, e.Kind, e.Name, e.Container, e.Decl,
				rec.Kind, rec.Name, rec.Container, rec.Decl)
		}
	}
	for id, e := range ek {
		if (e.Kind == "func" || e.Kind == "method") && !byID[id] {
			t.Errorf("extract record %s has no calls record", id)
		}
	}
}

func TestCallsCheckPasses(t *testing.T) {
	r := callsResult(t)
	if r.code != 0 {
		t.Errorf("calls -check: exit %d\nstdout:\n%s\nstderr:\n%s", r.code, r.stdout, r.stderr)
	}
	for _, want := range []string{
		"check linux: pairs: both 15, only syntax 0, only ssa 0\n",
		"check windows: pairs: both 17, only syntax 0, only ssa 0\n",
	} {
		if !strings.Contains(r.stdout, want) {
			t.Errorf("stdout has no line %q:\n%s", want, r.stdout)
		}
	}
}

// A one-sided pair fails the check: a syntax pair with no SSA call gives the exit code 1 and
// its line.
func TestCallsCheckReportsAOneSidedPair(t *testing.T) {
	recs, checks := callsChecks(t)
	changed := make([]CallRecord, len(recs))
	copy(changed, recs)
	for i := range changed {
		if changed[i].Name == "inLiteral" {
			changed[i].Uses = []CallUse{use("calls.go", 99, 1, true, at("calls.go", 42, 6), false, both)}
		}
	}
	var out bytes.Buffer
	if ok := printCheck(&out, changed, checks); ok {
		t.Errorf("printCheck is ok with a pair that only the syntax has:\n%s", out.String())
	}
	for _, want := range []string{
		"check linux: pairs: both 15, only syntax 1, only ssa 0\n",
		"  only syntax: caller calls.go:42 callers -> callee calls.go:60 inLiteral\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
}

// The check is not blind: a call after panic is dead code that SSA removes (only syntax), and a
// call through a local variable that holds a function or a method value is a static call of
// SSA with no call use (only ssa). A constant false condition stays in SSA.
func TestCallsCheckFindsDifferences(t *testing.T) {
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
	code := run([]string{"calls", "-tree", dir, "-configs", "linux", "-out", filepath.Join(dir, "calls.jsonl"), "-check"}, &out, &errb)
	if code != 1 {
		t.Errorf("exit %d, want 1; stderr: %s", code, errb.String())
	}
	for _, want := range []string{
		"check linux: pairs: both 1, only syntax 1, only ssa 2\n",
		"  only syntax: caller a.go:9 deadAfterPanic -> callee a.go:7 target\n",
		"  only ssa: caller a.go:14 viaLocal -> callee a.go:7 target\n",
		"  only ssa: caller a.go:19 viaMethodValue -> callee a.go:5 T.Get\n",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("no line %q:\n%s", want, out.String())
		}
	}
}

// distinctExcl sorts the excluded calls and removes the repeats (two package variants give
// the same calls).
func distinctExcl(es []exclCall) []exclCall {
	seen := map[exclCall]bool{}
	out := []exclCall{}
	for _, e := range es {
		if !seen[e] {
			seen[e] = true
			out = append(out, e)
		}
	}
	less := func(a, b Pos) int {
		switch {
		case a.File != b.File:
			return strings.Compare(a.File, b.File)
		case a.Line != b.Line:
			return a.Line - b.Line
		}
		return a.Col - b.Col
	}
	sort.Slice(out, func(i, j int) bool {
		if c := less(out[i].self, out[j].self); c != 0 {
			return c < 0
		}
		return less(out[i].callee, out[j].callee) < 0
	})
	return out
}

// Each class of excluded SSA callers: the static calls of the class reach a function
// declaration of the tree, and with no exclusion they give a pair that the syntax does not
// have.
func TestCallsCheckExclusionClasses(t *testing.T) {
	recs, checks := callsChecks(t)
	c := "calls.go"
	area, get, set, val, gen := cpos(c, 7, 13), cpos(c, 15, 12), cpos(c, 17, 13), cpos(c, 25, 17), cpos(c, 37, 6)
	plainDecl, initDecl := cpos(c, 27, 6), cpos(c, 71, 6)
	cases := []struct {
		class string
		want  []exclCall // the caller at the position of its own name (no position: zero), and the callee
	}{
		// var initial = plain(10), the literal of viaLiteral, and the call of init.
		{clsPackageInit, []exclCall{{callee: plainDecl}, {callee: initDecl}}},
		// The method set of Outer has a wrapper of the promoted Base.Area (ssautil.AllFunctions
		// takes the method sets of an exported type), and the method set of *T has a wrapper of
		// T.Get (var _ Getter = &T{}).
		{clsWrapper, []exclCall{{self: area, selfOK: true, callee: area}, {self: get, selfOK: true, callee: get}}},
		// T.Get(t) and (*T).Set(&t, 2) call a thunk.
		{clsThunk, []exclCall{{self: get, selfOK: true, callee: get}, {self: set, selfOK: true, callee: set}}},
		// apply(t.Get) makes a bound method closure.
		{clsBound, []exclCall{{self: get, selfOK: true, callee: get}}},
		// generic[int], generic(8) and Box[int]{}.Val() call an instantiation wrapper.
		{clsInstWrapper, []exclCall{{self: val, selfOK: true, callee: val}, {self: gen, selfOK: true, callee: gen}}},
	}
	for _, tc := range cases {
		t.Run(tc.class, func(t *testing.T) {
			for _, ch := range checks {
				got := distinctExcl(ch.excluded[tc.class])
				if !reflect.DeepEqual(got, tc.want) {
					t.Errorf("%s %s: excluded calls %+v, want %+v", ch.config, tc.class, got, tc.want)
				}
				syn := syntaxPairs(recs, ch.config)
				for _, e := range got {
					p := callPair{e.self, e.callee}
					if e.selfOK && syn[p] {
						t.Errorf("%s %s: the syntax has the pair %+v", ch.config, tc.class, p)
					}
					if e.selfOK && ch.pairs[p] {
						t.Errorf("%s %s: the SSA pairs have the excluded pair %+v", ch.config, tc.class, p)
					}
				}
			}
		})
	}
	// The uses of plain that the package initializer holds have the in null.
	for _, u := range callRec(t, recs, plainDecl).Uses {
		if u.Line == 64 || u.Line == 66 {
			if u.In != nil {
				t.Errorf("use %d:%d has in %+v", u.Line, u.Col, u.In)
			}
		}
	}
}
