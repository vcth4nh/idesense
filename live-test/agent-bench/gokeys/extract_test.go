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
	"testing"
)

const testTree = "testdata/mod"

var (
	both    = []string{"linux", "windows"}
	windows = []string{"windows"}

	keys    map[string]Record // the keys of testdata/mod, by id
	rawKeys []map[string]any  // the same lines, decoded with no struct
)

// TestMain extracts the keys of testdata/mod one time, through the command line entry.
func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "gokeys-test-")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	out := filepath.Join(dir, "keys.jsonl")
	var stderr bytes.Buffer
	code := run([]string{"extract", "-tree", testTree, "-configs", "linux,windows", "-out", out}, os.Stdout, &stderr)
	if code != 0 {
		fmt.Fprintf(os.Stderr, "extract exit %d: %s\n", code, stderr.String())
		os.Exit(1)
	}
	data, err := os.ReadFile(out)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	keys = map[string]Record{}
	sc := bufio.NewScanner(bytes.NewReader(data))
	sc.Buffer(make([]byte, 1<<20), 1<<26)
	for sc.Scan() {
		var r Record
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		var raw map[string]any
		if err := json.Unmarshal(sc.Bytes(), &raw); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if _, dup := keys[r.ID]; dup {
			fmt.Fprintln(os.Stderr, "duplicate id", r.ID)
			os.Exit(1)
		}
		keys[r.ID] = r
		rawKeys = append(rawKeys, raw)
	}
	code = m.Run()
	os.RemoveAll(dir)
	os.Exit(code)
}

const pkg = "go:example.com/mod."

func key(t *testing.T, id string) Record {
	t.Helper()
	r, ok := keys[pkg+id]
	if !ok {
		t.Fatalf("no record %s%s", pkg, id)
	}
	return r
}

func ids(names ...string) []string {
	out := make([]string, len(names))
	for i, n := range names {
		out[i] = pkg + n
	}
	return out
}

func site(file string, line, col int, class, why string, configs []string) Site {
	return Site{File: file, Line: line, Col: col, Class: class, Why: why, Configs: configs}
}

// sitesIn gives the sites of r in file (all files when file is "").
func sitesIn(r Record, file string) []Site {
	var out []Site
	for _, s := range r.Sites {
		if file == "" || s.File == file {
			out = append(out, s)
		}
	}
	return out
}

// checkSites compares the sites of r in file with want. It ignores the field Rel; checkRels
// tests it.
func checkSites(t *testing.T, r Record, file string, want []Site) {
	t.Helper()
	got := sitesIn(r, file)
	for i := range got {
		got[i].Rel = ""
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s sites in %q:\n got  %s\n want %s", r.ID, file, fmtSites(got), fmtSites(want))
	}
}

// checkRels compares the sites of r in file that have a rel with want ("line:col" → rel).
func checkRels(t *testing.T, r Record, file string, want map[string]string) {
	t.Helper()
	got := map[string]string{}
	for _, s := range sitesIn(r, file) {
		if s.Rel != "" {
			got[fmt.Sprintf("%d:%d", s.Line, s.Col)] = s.Rel
		}
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s rels in %q:\n got  %v\n want %v", r.ID, file, got, want)
	}
}

func hasEntry(list []string, entry string) bool {
	for _, e := range list {
		if e == entry {
			return true
		}
	}
	return false
}

func fmtSites(ss []Site) string {
	var b strings.Builder
	for _, s := range ss {
		fmt.Fprintf(&b, "\n   %s:%d:%d %s/%s %v", s.File, s.Line, s.Col, s.Class, s.Why, s.Configs)
	}
	return b.String()
}

func TestRecordSetIsExact(t *testing.T) {
	var got []string
	for id := range keys {
		got = append(got, id)
	}
	sort.Strings(got)
	want := append(ids(
		"Base", "Base.Area", "Circle", "Circle.Name", "Compute", "Counter", "Counter.Incr",
		"Dog", "Dog.Speak", "Robot", "Robot.Speak", "Shape", "Shape.Area", "Shape.Name",
		"Square", "Square.Area", "Square.Name", "TestTotal", "accent", "baseOf", "circleArea",
		"generated", "talk", "total", "useCompute", "windowsOnly",
		// closure.go
		"Door", "Door.Close", "Door.Open", "Door.Start", "Gate", "Gate.Open", "Gate.Start",
		"Hatch", "Hatch.Close", "Hatch.Open", "Opener", "Opener.Close", "Opener.Open",
		"Starter", "Starter.Open", "Starter.Start", "useDoors",
		// stringer.go, lener.go, sink.go
		"Celsius", "Celsius.String", "Label", "Label.String", "show",
		"ByAge", "ByAge.Len", "ByAge.Less", "ByAge.Swap", "Lener", "Lener.Len", "Queue", "Queue.Len", "sizes",
		"BufSink", "ByteSink", "ByteSink.Write", "fill",
	), "go:example.com/mod_test.TestExternal")
	sort.Strings(want)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("ids:\n got  %v\n want %v", got, want)
	}
	// rel is on each use of a family member and on no other site; each use of a function or
	// a type is "self"; external is empty for a function or a type.
	rels := map[string]bool{"self": true, "super": true, "sub": true, "sibling": true}
	for _, r := range keys {
		if r.External == nil || (len(r.External) != 0 && r.Kind != "method" && r.Kind != "iface_method") {
			t.Errorf("%s (%s): external %v", r.ID, r.Kind, r.External)
		}
		for _, s := range r.Sites {
			switch {
			case s.Class == "required" && !rels[s.Rel]:
				t.Errorf("%s: required site %s:%d:%d with rel %q", r.ID, s.File, s.Line, s.Col, s.Rel)
			case s.Class != "required" && s.Why != "generated" && s.Rel != "":
				t.Errorf("%s: %s/%s site %s:%d:%d with rel %q", r.ID, s.Class, s.Why, s.File, s.Line, s.Col, s.Rel)
			case s.Rel != "" && s.Rel != "self" && r.Kind != "method" && r.Kind != "iface_method":
				t.Errorf("%s (%s): site %s:%d:%d with rel %q", r.ID, r.Kind, s.File, s.Line, s.Col, s.Rel)
			}
		}
	}
	fields := []string{"container", "decl", "external", "family", "id", "implementers", "kind", "lang", "name", "sites", "source"}
	for _, raw := range rawKeys {
		var names []string
		for k := range raw {
			names = append(names, k)
		}
		sort.Strings(names)
		if !reflect.DeepEqual(names, fields) {
			t.Fatalf("%v: fields %v, want %v", raw["id"], names, fields)
		}
		if raw["lang"] != "go" || raw["source"] != "go/types" {
			t.Errorf("%v: lang %v source %v", raw["id"], raw["lang"], raw["source"])
		}
	}
	// One site for each position in each record.
	for _, r := range keys {
		seen := map[[3]any]bool{}
		for _, s := range r.Sites {
			k := [3]any{s.File, s.Line, s.Col}
			if seen[k] {
				t.Errorf("%s: two sites at %s:%d:%d", r.ID, s.File, s.Line, s.Col)
			}
			seen[k] = true
		}
	}
}

func TestFunctionUsesAndMethodValue(t *testing.T) {
	c := key(t, "Compute")
	if c.Kind != "func" || c.Name != "Compute" || c.Container != "" {
		t.Errorf("Compute: kind %q name %q container %q", c.Kind, c.Name, c.Container)
	}
	if c.Decl != (Pos{File: "funcs.go", Line: 4, Col: 6}) {
		t.Errorf("Compute decl %+v", c.Decl)
	}
	if !reflect.DeepEqual(c.Family, ids("Compute")) {
		t.Errorf("Compute family %v", c.Family)
	}
	if c.Implementers == nil || len(c.Implementers) != 0 {
		t.Errorf("Compute implementers %v, want []", c.Implementers)
	}
	checkSites(t, c, "funcs.go", []Site{
		site("funcs.go", 3, 4, "dnc", "comment", both),
		site("funcs.go", 4, 6, "dnc", "decl", both),
		site("funcs.go", 11, 7, "required", "use", both),
		site("funcs.go", 12, 7, "required", "use", both),
	})

	incr := key(t, "Counter.Incr")
	if incr.Kind != "method" || incr.Name != "Incr" || incr.Container != "Counter" {
		t.Errorf("Counter.Incr: kind %q name %q container %q", incr.Kind, incr.Name, incr.Container)
	}
	checkSites(t, incr, "", []Site{
		site("funcs.go", 8, 19, "dnc", "decl", both),
		site("funcs.go", 14, 11, "required", "use", both), // method value
		site("funcs.go", 16, 4, "required", "use", both),
	})
}

func TestFamilyJoinsInterfaceAndImplementers(t *testing.T) {
	area := ids("Base.Area", "Shape.Area", "Square.Area")
	for _, id := range []string{"Shape.Area", "Square.Area", "Base.Area"} {
		if got := key(t, id).Family; !reflect.DeepEqual(got, area) {
			t.Errorf("%s family %v, want %v", id, got, area)
		}
	}
	name := ids("Circle.Name", "Shape.Name", "Square.Name")
	for _, id := range []string{"Shape.Name", "Square.Name", "Circle.Name"} {
		if got := key(t, id).Family; !reflect.DeepEqual(got, name) {
			t.Errorf("%s family %v, want %v", id, got, name)
		}
	}
	sa := key(t, "Shape.Area")
	if sa.Kind != "iface_method" || sa.Container != "Shape" || sa.Decl != (Pos{"shapes.go", 5, 2}) {
		t.Errorf("Shape.Area: kind %q container %q decl %+v", sa.Kind, sa.Container, sa.Decl)
	}
	// The same sites for each member: the three declarations, the call through the
	// interface and the call of the promoted method.
	want := []Site{
		site("shapes.go", 5, 2, "dnc", "decl", both),
		site("shapes.go", 11, 17, "dnc", "decl", both),
		site("shapes.go", 18, 15, "dnc", "decl", both),
		site("shapes.go", 30, 12, "required", "use", both),
		site("shapes.go", 36, 11, "required", "use", both),
	}
	checkSites(t, key(t, "Square.Area"), "", want)
	checkSites(t, sa, "", want)
}

func TestEmbeddedPromotionSite(t *testing.T) {
	ba := key(t, "Base.Area")
	checkSites(t, ba, "", []Site{
		site("shapes.go", 5, 2, "dnc", "decl", both),
		site("shapes.go", 11, 17, "dnc", "decl", both),
		site("shapes.go", 18, 15, "dnc", "decl", both),
		site("shapes.go", 30, 12, "required", "use", both),
		site("shapes.go", 36, 11, "required", "use", both), // c.Area() on Circle
	})
	// The type Base: the receiver, the embedded field and the selector of the embedded
	// field name the type.
	checkSites(t, key(t, "Base"), "", []Site{
		site("shapes.go", 15, 4, "dnc", "comment", both),
		site("shapes.go", 16, 6, "dnc", "decl", both),
		site("shapes.go", 18, 9, "required", "use", both),
		site("shapes.go", 20, 49, "dnc", "comment", both),
		site("shapes.go", 22, 2, "required", "use", both),
		site("shapes.go", 39, 23, "required", "use", both),
		site("shapes.go", 40, 11, "required", "use", both),
	})
}

func TestDecoyIsForbidden(t *testing.T) {
	dog := key(t, "Dog.Speak")
	if !reflect.DeepEqual(dog.Family, ids("Dog.Speak")) {
		t.Errorf("Dog.Speak family %v", dog.Family)
	}
	checkSites(t, dog, "", []Site{
		site("decoy.go", 5, 12, "dnc", "decl", both),
		site("decoy.go", 9, 14, "forbidden", "decoy", both),
		site("decoy.go", 12, 13, "required", "use", both),
		site("decoy.go", 13, 15, "forbidden", "decoy", both),
	})
	checkSites(t, key(t, "Robot.Speak"), "", []Site{
		site("decoy.go", 5, 12, "forbidden", "decoy", both),
		site("decoy.go", 9, 14, "dnc", "decl", both),
		site("decoy.go", 12, 13, "forbidden", "decoy", both),
		site("decoy.go", 13, 15, "required", "use", both),
	})
}

func TestWindowsOnlySiteHasItsConfig(t *testing.T) {
	checkSites(t, key(t, "Compute"), "only_windows.go", []Site{
		site("only_windows.go", 4, 9, "required", "use", windows),
	})
	w := key(t, "windowsOnly")
	if w.Decl != (Pos{"only_windows.go", 3, 6}) {
		t.Errorf("windowsOnly decl %+v", w.Decl)
	}
	checkSites(t, w, "", []Site{site("only_windows.go", 3, 6, "dnc", "decl", windows)})
}

func TestTestFileSiteIsRequired(t *testing.T) {
	c := key(t, "Compute")
	checkSites(t, c, "shapes_test.go", []Site{
		site("shapes_test.go", 9, 5, "required", "use", both),
		site("shapes_test.go", 10, 12, "dnc", "string", both),
	})
	checkSites(t, c, "ext_test.go", []Site{
		site("ext_test.go", 10, 9, "required", "use", both),
	})
	ext, ok := keys["go:example.com/mod_test.TestExternal"]
	if !ok || ext.Kind != "func" || ext.Decl != (Pos{"ext_test.go", 9, 6}) {
		t.Errorf("TestExternal: %+v", ext)
	}
}

func TestCommentStringGeneratedAreDnc(t *testing.T) {
	c := key(t, "Compute")
	checkSites(t, c, "words.go", []Site{
		site("words.go", 3, 16, "dnc", "comment", both),
		site("words.go", 4, 21, "dnc", "string", both),
	})
	checkSites(t, c, "gen.go", []Site{site("gen.go", 5, 31, "dnc", "generated", both)})
	checkRels(t, c, "gen.go", map[string]string{"5:31": "self"}) // a use in a generated file keeps its rel
	// A declaration in a generated file stays a declaration. The header word is a comment
	// site of the generated file.
	checkSites(t, key(t, "generated"), "", []Site{
		site("gen.go", 1, 9, "dnc", "generated", both),
		site("gen.go", 5, 6, "dnc", "decl", both),
	})
}

func TestImplementersOfInterface(t *testing.T) {
	s := key(t, "Shape")
	if s.Kind != "interface" || !reflect.DeepEqual(s.Family, ids("Shape")) {
		t.Errorf("Shape: kind %q family %v", s.Kind, s.Family)
	}
	want := []Implementer{
		{ID: pkg + "Circle", File: "shapes.go", Line: 21, Col: 6}, // through the embedded Base, *Circle
		{ID: pkg + "Square", File: "shapes.go", Line: 9, Col: 6},
	}
	if !reflect.DeepEqual(s.Implementers, want) {
		t.Errorf("Shape implementers %+v, want %+v", s.Implementers, want)
	}
	for _, id := range []string{"Base", "Circle", "Square"} {
		r := key(t, id)
		if r.Kind != "type" || r.Implementers == nil || len(r.Implementers) != 0 {
			t.Errorf("%s: kind %q implementers %v, want type and []", id, r.Kind, r.Implementers)
		}
	}
}

func TestIdentsSubcommand(t *testing.T) {
	var out, errb bytes.Buffer
	if code := run([]string{"idents", "-tree", testTree, "-name", "Compute"}, &out, &errb); code != 0 {
		t.Fatalf("idents exit %d: %s", code, errb.String())
	}
	want := strings.Join([]string{
		`{"file":"accent.go","line":3,"col":14,"in":"comment"}`,
		`{"file":"accent.go","line":4,"col":43,"in":"code"}`,
		`{"file":"accent.go","line":6,"col":25,"in":"code"}`,
		`{"file":"ext_test.go","line":10,"col":9,"in":"code"}`,
		`{"file":"funcs.go","line":3,"col":4,"in":"comment"}`,
		`{"file":"funcs.go","line":4,"col":6,"in":"code"}`,
		`{"file":"funcs.go","line":11,"col":7,"in":"code"}`,
		`{"file":"funcs.go","line":12,"col":7,"in":"code"}`,
		`{"file":"gen.go","line":5,"col":31,"in":"code"}`,
		`{"file":"only_windows.go","line":4,"col":9,"in":"code"}`,
		`{"file":"shapes_test.go","line":9,"col":5,"in":"code"}`,
		`{"file":"shapes_test.go","line":10,"col":12,"in":"string"}`,
		`{"file":"words.go","line":3,"col":16,"in":"comment"}`,
		`{"file":"words.go","line":4,"col":21,"in":"string"}`,
	}, "\n") + "\n"
	if out.String() != want {
		t.Errorf("idents output:\n%s\nwant:\n%s", out.String(), want)
	}
}

// The column counts UTF-16 code units, not bytes: "é" is two bytes and one unit; "😀"
// (U+1F600) is four bytes, one code point and two units (line 6: code point column 24).
func TestColumnCountsCharacters(t *testing.T) {
	checkSites(t, key(t, "Compute"), "accent.go", []Site{
		site("accent.go", 3, 14, "dnc", "comment", both),
		site("accent.go", 4, 43, "required", "use", both),
		site("accent.go", 6, 25, "required", "use", both),
	})
	if d := key(t, "accent").Decl; d != (Pos{"accent.go", 4, 6}) {
		t.Errorf("accent decl %+v", d)
	}
}

// Opener and Starter both declare Open; Door implements both, Gate only Starter, Hatch only
// Opener. One step from Opener.Open does not reach Gate.Open; the closure does.
func TestFamilyIsTransitiveClosure(t *testing.T) {
	open := ids("Door.Open", "Gate.Open", "Hatch.Open", "Opener.Open", "Starter.Open")
	for _, id := range []string{"Door.Open", "Gate.Open", "Hatch.Open", "Opener.Open", "Starter.Open"} {
		if got := key(t, id).Family; !reflect.DeepEqual(got, open) {
			t.Errorf("%s family %v, want %v", id, got, open)
		}
	}
	closeFam := ids("Door.Close", "Hatch.Close", "Opener.Close")
	if got := key(t, "Hatch.Close").Family; !reflect.DeepEqual(got, closeFam) {
		t.Errorf("Hatch.Close family %v, want %v", got, closeFam)
	}
	// Each use of a member is required for each member.
	want := []Site{
		site("closure.go", 5, 2, "dnc", "decl", both),
		site("closure.go", 10, 2, "dnc", "decl", both),
		site("closure.go", 17, 13, "dnc", "decl", both),
		site("closure.go", 25, 13, "dnc", "decl", both),
		site("closure.go", 31, 14, "dnc", "decl", both),
		site("closure.go", 36, 9, "required", "use", both),
		site("closure.go", 37, 9, "required", "use", both),
		site("closure.go", 38, 9, "required", "use", both),
		site("closure.go", 39, 9, "required", "use", both),
	}
	checkSites(t, key(t, "Hatch.Open"), "", want)
	checkSites(t, key(t, "Starter.Open"), "", want)
}

// Lines 36 to 39 of closure.go: d.Open() (Door), g.Open() (Gate), o.Open() (Opener),
// s.Open() (Starter).
func TestRelSelfSuperSubSibling(t *testing.T) {
	cases := map[string]map[string]string{
		"Door.Open":    {"36:9": "self", "37:9": "sibling", "38:9": "super", "39:9": "super"},
		"Hatch.Open":   {"36:9": "sibling", "37:9": "sibling", "38:9": "super", "39:9": "sibling"},
		"Opener.Open":  {"36:9": "sub", "37:9": "sibling", "38:9": "self", "39:9": "sibling"},
		"Starter.Open": {"36:9": "sub", "37:9": "sub", "38:9": "sibling", "39:9": "self"},
	}
	for id, want := range cases {
		checkRels(t, key(t, id), "closure.go", want)
	}
	// shapes.go 30:12 is s.Area() through Shape; 36:11 is c.Area() on Circle, the promoted
	// Base.Area. Base alone does not implement Shape, so Shape.Area is no super of Base.Area.
	checkRels(t, key(t, "Base.Area"), "shapes.go", map[string]string{"30:12": "sibling", "36:11": "self"})
	checkRels(t, key(t, "Square.Area"), "shapes.go", map[string]string{"30:12": "super", "36:11": "sibling"})
	checkRels(t, key(t, "Shape.Area"), "shapes.go", map[string]string{"30:12": "self", "36:11": "sub"})
	// The selector of the embedded field names the type: self.
	checkRels(t, key(t, "Base"), "shapes.go", map[string]string{"18:9": "self", "22:2": "self", "39:23": "self", "40:11": "self"})
}

// Celsius.String implements fmt.Stringer; Label.String(prefix string) implements nothing.
// stringer.go 16:9 is s.String() on a fmt.Stringer, 17:9 is l.String("x") on a Label.
func TestExternalSuperFromLibraryInterface(t *testing.T) {
	c := key(t, "Celsius.String")
	if !hasEntry(c.External, "super:fmt.Stringer.String") {
		t.Errorf("Celsius.String external %v: no super:fmt.Stringer.String", c.External)
	}
	for _, e := range c.External {
		if !strings.HasPrefix(e, "super:") || !strings.HasSuffix(e, ".String") {
			t.Errorf("Celsius.String external entry %q", e)
		}
	}
	checkSites(t, c, "stringer.go", []Site{
		site("stringer.go", 8, 18, "dnc", "decl", both),
		site("stringer.go", 13, 14, "forbidden", "decoy", both),
		site("stringer.go", 16, 9, "dnc", "unproven", both),
		site("stringer.go", 17, 9, "forbidden", "decoy", both),
	})
	l := key(t, "Label.String")
	if len(l.External) != 0 {
		t.Errorf("Label.String external %v, want []", l.External)
	}
	checkSites(t, l, "stringer.go", []Site{
		site("stringer.go", 8, 18, "forbidden", "decoy", both),
		site("stringer.go", 13, 14, "dnc", "decl", both),
		site("stringer.go", 16, 9, "forbidden", "decoy", both),
		site("stringer.go", 17, 9, "required", "use", both),
	})
}

// Lener.Len, ByAge.Len and Queue.Len are one family. Only ByAge implements sort.Interface,
// and only the interface method has library implementers; Queue.Len gets both entries.
func TestExternalIsUnionOverFamily(t *testing.T) {
	q := key(t, "Queue.Len")
	if !reflect.DeepEqual(q.Family, ids("ByAge.Len", "Lener.Len", "Queue.Len")) {
		t.Errorf("Queue.Len family %v", q.Family)
	}
	for _, e := range []string{"super:sort.Interface.Len", "impl:bytes.Buffer"} {
		if !hasEntry(q.External, e) {
			t.Errorf("Queue.Len external has no %s: %v", e, q.External)
		}
	}
	for _, id := range []string{"ByAge.Len", "Lener.Len"} {
		if got := key(t, id).External; !reflect.DeepEqual(got, q.External) {
			t.Errorf("%s external differs from Queue.Len:\n %v\n %v", id, got, q.External)
		}
	}
	if got := key(t, "ByAge.Less").External; !reflect.DeepEqual(got, []string{"super:sort.Interface.Less"}) {
		t.Errorf("ByAge.Less external %v", got)
	}
}

// *bytes.Buffer implements ByteSink; BufSink implements it with the method of the embedded
// *bytes.Buffer.
func TestExternalImplFromLibraryType(t *testing.T) {
	w := key(t, "ByteSink.Write")
	for _, e := range []string{"impl:bytes.Buffer", "impl:bytes.Buffer.Write via go:example.com/mod.BufSink"} {
		if !hasEntry(w.External, e) {
			t.Errorf("ByteSink.Write external has no %s: %v", e, w.External)
		}
	}
	for _, e := range w.External {
		if !strings.HasPrefix(e, "impl:") {
			t.Errorf("ByteSink.Write external entry %q", e)
		}
	}
	if !reflect.DeepEqual(w.Family, ids("ByteSink.Write")) {
		t.Errorf("ByteSink.Write family %v", w.Family)
	}
	checkSites(t, w, "", []Site{
		site("sink.go", 7, 2, "dnc", "decl", both),
		site("sink.go", 16, 4, "required", "use", both),
	})
}

func TestTypeErrorExitsWithOne(t *testing.T) {
	dir := t.TempDir()
	write := func(name, text string) {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("go.mod", "module example.com/broken\n\ngo 1.26\n")
	write("a.go", "package broken\n\nfunc f() int { return undefinedName }\n")
	var out, errb bytes.Buffer
	code := run([]string{"extract", "-tree", dir, "-configs", "linux", "-out", filepath.Join(dir, "k.jsonl")}, &out, &errb)
	if code != 1 {
		t.Fatalf("exit %d, want 1; stderr: %s", code, errb.String())
	}
	if !strings.Contains(errb.String(), "undefinedName") {
		t.Errorf("stderr does not name the error: %s", errb.String())
	}
	if _, err := os.Stat(filepath.Join(dir, "k.jsonl")); !os.IsNotExist(err) {
		t.Errorf("output file written despite the error")
	}
}
