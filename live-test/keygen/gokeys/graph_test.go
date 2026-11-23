package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"sync"
	"testing"
)

// testdata/graph has one example of each call step (graph.go), a type that implements Shape in
// a _test.go file, and a function and its caller in a _windows.go file.
const graphTree = "testdata/graph"

const graphPkg = "go:example.com/graph."

type graphRun struct {
	code           int
	stdout, stderr string
	data           []byte
	funcs          []GraphFunc
	ifaces         []GraphIface
	err            error
}

// runGraphCmd runs gokeys graph on tree for linux through the command line entry and decodes
// the output file by the field rec of each line. An unknown field, and a func line after an
// iface line, are errors.
func runGraphCmd(tree string) graphRun {
	dir, err := os.MkdirTemp("", "gokeys-graph-test-")
	if err != nil {
		return graphRun{err: err}
	}
	defer os.RemoveAll(dir)
	out := filepath.Join(dir, "graph.jsonl")
	var stdout, stderr bytes.Buffer
	r := graphRun{code: run([]string{"graph", "-tree", tree, "-goos", "linux", "-out", out}, &stdout, &stderr)}
	r.stdout, r.stderr = stdout.String(), stderr.String()
	if r.data, r.err = os.ReadFile(out); r.err != nil {
		r.err = fmt.Errorf("%w (exit %d, stderr %s)", r.err, r.code, r.stderr)
		return r
	}
	sc := bufio.NewScanner(bytes.NewReader(r.data))
	sc.Buffer(make([]byte, 1<<20), 1<<26)
	for sc.Scan() {
		var head struct {
			Rec string `json:"rec"`
		}
		if r.err = json.Unmarshal(sc.Bytes(), &head); r.err != nil {
			return r
		}
		dec := json.NewDecoder(bytes.NewReader(sc.Bytes()))
		dec.DisallowUnknownFields()
		switch head.Rec {
		case "func":
			if len(r.ifaces) > 0 {
				r.err = fmt.Errorf("a func line after an iface line: %s", sc.Bytes())
				return r
			}
			var f GraphFunc
			if r.err = dec.Decode(&f); r.err != nil {
				return r
			}
			r.funcs = append(r.funcs, f)
		case "iface":
			var i GraphIface
			if r.err = dec.Decode(&i); r.err != nil {
				return r
			}
			r.ifaces = append(r.ifaces, i)
		default:
			r.err = fmt.Errorf("rec %q: %s", head.Rec, sc.Bytes())
			return r
		}
	}
	r.err = sc.Err()
	return r
}

var (
	graphOnce  sync.Once
	graphFirst graphRun // gokeys graph on testdata/graph
)

func graphResult(t *testing.T) graphRun {
	t.Helper()
	graphOnce.Do(func() { graphFirst = runGraphCmd(graphTree) })
	if graphFirst.err != nil {
		t.Fatal(graphFirst.err)
	}
	if graphFirst.code != 0 {
		t.Fatalf("graph: exit %d: %s", graphFirst.code, graphFirst.stderr)
	}
	return graphFirst
}

// graphName gives the name of a function record, Container.Name for a method.
func graphName(f GraphFunc) string {
	if f.Container != "" {
		return f.Container + "." + f.Name
	}
	return f.Name
}

func graphFunc(t *testing.T, r graphRun, name string) GraphFunc {
	t.Helper()
	for _, f := range r.funcs {
		if graphName(f) == name {
			return f
		}
	}
	t.Fatalf("no function %s", name)
	return GraphFunc{}
}

// checkSteps compares the calls of the function name, in the order of the file, as
// "<kind> <callee name or null> lit=<lit> iface=<iface>".
func checkSteps(t *testing.T, r graphRun, name string, want ...string) {
	t.Helper()
	names := map[Pos]string{}
	for _, f := range r.funcs {
		names[f.Decl] = graphName(f)
	}
	got := []string{}
	for _, c := range graphFunc(t, r, name).Calls {
		callee := "null"
		if c.Callee != nil {
			if callee = names[*c.Callee]; callee == "" {
				callee = fmt.Sprintf("%+v", *c.Callee)
			}
		}
		got = append(got, fmt.Sprintf("%s %s lit=%v iface=%q", c.Kind, callee, c.Lit, c.Iface))
	}
	if want == nil {
		want = []string{}
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s calls:\n got  %q\n want %q", name, got, want)
	}
}

// checkCallsAt checks that each call of the function name is at line:col.
func checkCallsAt(t *testing.T, r graphRun, name string, line, col int) {
	t.Helper()
	for _, c := range graphFunc(t, r, name).Calls {
		if c.Line != line || c.Col != col {
			t.Errorf("%s: call at %d:%d, want %d:%d", name, c.Line, c.Col, line, col)
		}
	}
}

const shapeArea = `iface="go:example.com/graph.Shape.Area"`

func TestGraphStepKinds(t *testing.T) {
	r := graphResult(t)
	checkSteps(t, r, "direct", `direct target lit=false iface=""`)
	checkCallsAt(t, r, "direct", 67, 28)
	// o.Area() selects the method that Outer promotes from Base.
	checkSteps(t, r, "promoted", `embedded Base.Area lit=false iface=""`)
	checkSteps(t, r, "goDefer", `direct spawned lit=false iface=""`, `direct deferred lit=false iface=""`)
	// The call of the literal itself has no name (TestGraphCallWithNoCalleeName).
	checkSteps(t, r, "inLiteral", `direct target lit=true iface=""`, `other null lit=false iface=""`)
	checkSteps(t, r, "recurse", `direct recurse lit=false iface=""`)
	checkSteps(t, r, "init", `direct target lit=false iface=""`)
	for _, c := range []struct{ name, id, kind, container string }{
		{"direct", graphPkg + "direct", "func", ""},
		{"init", "", "func", ""},
		{"Rect.Area", graphPkg + "Rect.Area", "method", "Rect"},
		{"Pair.Area", graphPkg + "Pair.Area", "method", "Pair"},
	} {
		f := graphFunc(t, r, c.name)
		if f.Rec != "func" || f.ID != c.id || f.Kind != c.kind || f.Container != c.container {
			t.Errorf("%s: rec %q id %q kind %q container %q, want func %q %q %q",
				c.name, f.Rec, f.ID, f.Kind, f.Container, c.id, c.kind, c.container)
		}
	}
}

func TestGraphInterfaceCallHasOneEntryForEachImplementer(t *testing.T) {
	r := graphResult(t)
	// Square selects Base.Area; Holder selects the method of Shape and gives no entry; Pair is
	// generic.
	checkSteps(t, r, "viaShape",
		"iface Base.Area lit=false "+shapeArea,
		"iface Circle.Area lit=false "+shapeArea,
		"iface Rect.Area lit=false "+shapeArea)
	checkCallsAt(t, r, "viaShape", 71, 39)
	if c := graphFunc(t, r, "viaShape").Calls; len(c) == 0 || c[0].Callee == nil || *c[0].Callee != graphFunc(t, r, "Base.Area").Decl {
		t.Errorf("the first call is %+v, want the decl of Base.Area as the callee", c)
	}
}

// h.Area() dispatches on the embedded field of type Shape.
func TestGraphEmbeddedInterfaceFieldIsAnInterfaceCall(t *testing.T) {
	r := graphResult(t)
	checkSteps(t, r, "viaHolder",
		"iface Base.Area lit=false "+shapeArea,
		"iface Circle.Area lit=false "+shapeArea,
		"iface Rect.Area lit=false "+shapeArea)
	checkCallsAt(t, r, "viaHolder", 73, 41)
}

func TestGraphUnnamedModuleInterfaceCounts(t *testing.T) {
	r := graphResult(t)
	checkSteps(t, r, "viaUnnamed", `iface Glass.Lens lit=false iface=""`)
	checkCallsAt(t, r, "viaUnnamed", 75, 65)
}

func TestGraphInterfaceMethodExpressionIsAnInterfaceCall(t *testing.T) {
	r := graphResult(t)
	checkSteps(t, r, "methodExpr",
		"iface Base.Area lit=false "+shapeArea,
		"iface Circle.Area lit=false "+shapeArea,
		"iface Rect.Area lit=false "+shapeArea)
	checkCallsAt(t, r, "methodExpr", 77, 45)
}

// A call of a method of a library interface, of a function value and on a value of a type
// parameter gives no step. The method value t.Get is no call.
func TestGraphOtherCalls(t *testing.T) {
	r := graphResult(t)
	other := `other null lit=false iface=""`
	checkSteps(t, r, "write", other)
	checkCallsAt(t, r, "write", 81, 29)
	checkSteps(t, r, "local", other)
	checkCallsAt(t, r, "local", 85, 9)
	checkSteps(t, r, "use", other)
	checkCallsAt(t, r, "use", 79, 39)
	checkSteps(t, r, "apply", other)
	checkSteps(t, r, "methodValue", `direct apply lit=false iface=""`)
	checkCallsAt(t, r, "methodValue", 88, 36)
}

// A named type of a function body and an unnamed struct type are implementers. Each one gets
// the method Size from an embedded field, and no package-level type implements Sizer.
func TestGraphLocalAndUnnamedStructImplementers(t *testing.T) {
	r := graphResult(t)
	sizerSize := `iface="go:example.com/graph.Sizer.Size"`
	checkSteps(t, r, "viaSizer", "iface SizeA.Size lit=false "+sizerSize, "iface SizeB.Size lit=false "+sizerSize)
	checkCallsAt(t, r, "viaSizer", 130, 39)
}

// The ids of two unnamed struct types whose first occurrences start at one position differ.
func TestGraphUnnamedStructIDsAreUnique(t *testing.T) {
	dir := t.TempDir()
	write := func(name, text string) {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("go.mod", "module example.com/tie\n\ngo 1.26\n")
	write("a.go", `package tie

type I interface{ M() int }

type J interface{ N() int }

type A struct{}

func (A) M() int { return 1 }

type B struct{}

func (B) N() int { return 2 }

func f() {
	_ = struct {
		A
		F struct{ B }
	}{}.F
}
`)
	_, ifaces, _, _, err := extractGraph(dir, "linux", false)
	if err != nil {
		t.Fatal(err)
	}
	var got []string
	for _, i := range ifaces {
		for _, m := range i.Methods {
			for _, im := range m.Impls {
				got = append(got, m.Name+" "+im.Type)
			}
		}
	}
	want := []string{"M go:example.com/tie.A", "M struct@a.go:16:6", "N go:example.com/tie.B", "N struct@a.go:16:6#2"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("implementers:\n got  %q\n want %q", got, want)
	}
}

// A call through a module interface whose type mentions a type parameter gives one entry other.
// Getter[int] has the concrete method Get() int.
func TestGraphGenericInterfaceWithTypeParameterIsOther(t *testing.T) {
	r := graphResult(t)
	other := `other null lit=false iface=""`
	checkSteps(t, r, "viaGetterParam", other)
	checkCallsAt(t, r, "viaGetterParam", 153, 54)
	checkSteps(t, r, "viaParamIface", other)
	checkCallsAt(t, r, "viaParamIface", 155, 70)
	checkSteps(t, r, "viaGetterInt", `iface T.Get lit=false iface="go:example.com/graph.Getter.Get"`)
	checkCallsAt(t, r, "viaGetterInt", 151, 49)
}

// A call whose operand is no name gives one entry other at its left parenthesis. A conversion
// gives no entry, and l[0]() stays at the name l.
func TestGraphCallWithNoCalleeName(t *testing.T) {
	r := graphResult(t)
	other := `other null lit=false iface=""`
	checkSteps(t, r, "noName", `direct getF lit=false iface=""`, other, other, other)
	var got []string
	for _, c := range graphFunc(t, r, "noName").Calls {
		got = append(got, fmt.Sprintf("%d:%d", c.Line, c.Col))
	}
	if want := []string{"161:2", "161:8", "162:12", "163:8"}; !reflect.DeepEqual(got, want) {
		t.Errorf("noName: calls at %q, want %q", got, want)
	}
	checkSteps(t, r, "indexed", other)
	checkCallsAt(t, r, "indexed", 168, 28)
	if c := graphFunc(t, r, "inLiteral").Calls; len(c) != 2 || c[1].Line != 96 || c[1].Col != 21 {
		t.Errorf("inLiteral: calls %+v, want the call of the literal at 96:21", c)
	}
}

// The build is linux with no test file, and the call in the initializer of a package-level
// variable (graph.go:106) belongs to no function.
func TestGraphNoTestTypeNoOtherBuildNoPackageLevelCall(t *testing.T) {
	r := graphResult(t)
	for _, f := range r.funcs {
		if f.Decl.File != "graph.go" {
			t.Errorf("function %s in %s", graphName(f), f.Decl.File)
		}
		for _, c := range f.Calls {
			if c.Line == 106 {
				t.Errorf("%s has a call at line 106", graphName(f))
			}
		}
	}
	for _, i := range r.ifaces {
		for _, m := range i.Methods {
			for _, im := range m.Impls {
				if im.Type == graphPkg+"testShape" || im.TypeDecl.File != "graph.go" {
					t.Errorf("%s: implementer %s at %+v", m.ID, im.Type, im.TypeDecl)
				}
			}
		}
	}
}

// Holder selects the methods of its embedded field Shape: the module declares no function for
// them, so the method is null. Pair is generic and testShape is in a test file: no entry. The
// local type sized and the unnamed struct type of unnamedSizer implement Sizer, with an id of
// their position.
func TestGraphInterfaceTable(t *testing.T) {
	r := graphResult(t)
	g := "graph.go"
	impl := func(typ string, line, col int, method *Pos, own bool) GraphImpl {
		return GraphImpl{Type: graphPkg + typ, TypeDecl: cpos(g, line, col), Method: method, Own: own}
	}
	sized, unnamed := "go:example.com/graph.sized@graph.go:133:7", "struct@graph.go:142:9"
	want := []GraphIface{{Rec: "iface", ID: graphPkg + "Shape", Name: "Shape", Decl: cpos(g, 7, 6), Methods: []GraphMethod{
		{ID: graphPkg + "Shape.Area", Name: "Area", Decl: cpos(g, 8, 2), Impls: []GraphImpl{
			impl("Circle", 18, 6, at(g, 20, 15), true),
			impl("Holder", 37, 6, nil, false),
			impl("Rect", 30, 6, at(g, 32, 14), true),
			impl("Square", 25, 6, at(g, 15, 13), false),
		}},
		{ID: graphPkg + "Shape.Name", Name: "Name", Decl: cpos(g, 9, 2), Impls: []GraphImpl{
			impl("Circle", 18, 6, at(g, 22, 15), true),
			impl("Holder", 37, 6, nil, false),
			impl("Rect", 30, 6, at(g, 34, 14), true),
			impl("Square", 25, 6, at(g, 27, 15), true),
		}},
	}}, {Rec: "iface", ID: graphPkg + "Sizer", Name: "Sizer", Decl: cpos(g, 112, 6), Methods: []GraphMethod{
		{ID: graphPkg + "Sizer.Label", Name: "Label", Decl: cpos(g, 114, 2), Impls: []GraphImpl{
			{Type: sized, TypeDecl: cpos(g, 133, 7), Method: at(g, 128, 16)},
			{Type: unnamed, TypeDecl: cpos(g, 142, 9), Method: at(g, 128, 16)},
		}},
		{ID: graphPkg + "Sizer.Size", Name: "Size", Decl: cpos(g, 113, 2), Impls: []GraphImpl{
			{Type: sized, TypeDecl: cpos(g, 133, 7), Method: at(g, 120, 14)},
			{Type: unnamed, TypeDecl: cpos(g, 142, 9), Method: at(g, 124, 14)},
		}},
	}}}
	if !reflect.DeepEqual(r.ifaces, want) {
		got, _ := json.MarshalIndent(r.ifaces, "", " ")
		exp, _ := json.MarshalIndent(want, "", " ")
		t.Errorf("interfaces:\n got  %s\n want %s", got, exp)
	}
}

// The statistics, the field names and their order in the file, and two runs give equal bytes.
func TestGraphOutputAndTwoRunsEqual(t *testing.T) {
	r := graphResult(t)
	for _, want := range []string{
		"config linux: 1 packages of the patterns, ",
		`functions: 40, with id "" 1` + "\n",
		"calls: 33, direct 8, embedded 1, iface 13, other 11\n",
		"interfaces: 2\n",
		"generic types (no implementer): 1, 1 with each method name of a module interface\n",
		"named types of a function body: 2, 1 implement a module interface\n",
		"unnamed struct types with an embedded field: 1, 1 implement a module interface\n",
		"calls through a type that mentions a type parameter (kind other): 3\n",
		"method expressions of an interface type (I.M(v), kind iface): 1\n",
		"time: ",
	} {
		if !strings.Contains(r.stdout, want) {
			t.Errorf("stdout has no line %q:\n%s", want, r.stdout)
		}
	}
	lines := strings.Split(strings.TrimSuffix(string(r.data), "\n"), "\n")
	for _, want := range []string{
		`{"rec":"func","id":"go:example.com/graph.spawned","kind":"func","name":"spawned","container":"",` +
			`"decl":{"file":"graph.go","line":63,"col":6},"end":63,"calls":[]}`,
		`{"rec":"func","id":"go:example.com/graph.direct","kind":"func","name":"direct","container":"",` +
			`"decl":{"file":"graph.go","line":67,"col":6},"end":67,"calls":[{"line":67,"col":28,` +
			`"callee":{"file":"graph.go","line":59,"col":6},"kind":"direct","lit":false,"iface":""}]}`,
		`{"rec":"func","id":"go:example.com/graph.write","kind":"func","name":"write","container":"",` +
			`"decl":{"file":"graph.go","line":81,"col":6},"end":81,"calls":[{"line":81,"col":29,` +
			`"callee":null,"kind":"other","lit":false,"iface":""}]}`,
	} {
		if !slices.Contains(lines, want) {
			t.Errorf("no line %s", want)
		}
	}
	wantIface := `{"rec":"iface","id":"go:example.com/graph.Shape","name":"Shape","decl":{"file":"graph.go","line":7,"col":6},` +
		`"methods":[{"id":"go:example.com/graph.Shape.Area","name":"Area","decl":{"file":"graph.go","line":8,"col":2},` +
		`"impls":[{"type":"go:example.com/graph.Circle","type_decl":{"file":"graph.go","line":18,"col":6},` +
		`"method":{"file":"graph.go","line":20,"col":15},"own":true},` +
		`{"type":"go:example.com/graph.Holder","type_decl":{"file":"graph.go","line":37,"col":6},"method":null,"own":false},`
	if first := lines[len(r.funcs)]; !strings.HasPrefix(first, wantIface) {
		t.Errorf("first iface line:\n got  %s\n want the start %s", first, wantIface)
	}
	again := runGraphCmd(graphTree)
	if again.err != nil {
		t.Fatal(again.err)
	}
	if again.code != 0 {
		t.Errorf("second run: exit %d: %s", again.code, again.stderr)
	}
	if !bytes.Equal(again.data, r.data) {
		t.Errorf("two runs give different files:\n%s\n---\n%s", r.data, again.data)
	}
}
