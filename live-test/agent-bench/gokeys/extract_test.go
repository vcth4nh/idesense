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

const testTree = "testdata/mod"

var (
	both    = []string{"linux", "windows"}
	windows = []string{"windows"}

	keys    map[string]Record // the keys of testdata/mod, by id
	rawKeys []map[string]any  // the same lines, decoded with no struct
)

// TestMain extracts the keys of testdata/mod one time, through the command line entry.
func TestMain(m *testing.M) {
	var err error
	if keys, rawKeys, err = extractTree(testTree); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	os.Exit(m.Run())
}

// extractTree extracts the keys of tree for linux and windows through the command line
// entry. It gives the records by id, and the same lines decoded with no struct.
func extractTree(tree string) (map[string]Record, []map[string]any, error) {
	dir, err := os.MkdirTemp("", "gokeys-test-")
	if err != nil {
		return nil, nil, err
	}
	defer os.RemoveAll(dir)
	out := filepath.Join(dir, "keys.jsonl")
	var stderr bytes.Buffer
	if code := run([]string{"extract", "-tree", tree, "-configs", "linux,windows", "-out", out}, os.Stdout, &stderr); code != 0 {
		return nil, nil, fmt.Errorf("extract %s: exit %d: %s", tree, code, stderr.String())
	}
	data, err := os.ReadFile(out)
	if err != nil {
		return nil, nil, err
	}
	recs := map[string]Record{}
	var raws []map[string]any
	sc := bufio.NewScanner(bytes.NewReader(data))
	sc.Buffer(make([]byte, 1<<20), 1<<26)
	for sc.Scan() {
		var r Record
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			return nil, nil, err
		}
		var raw map[string]any
		if err := json.Unmarshal(sc.Bytes(), &raw); err != nil {
			return nil, nil, err
		}
		if _, dup := recs[r.ID]; dup {
			return nil, nil, fmt.Errorf("duplicate id %s", r.ID)
		}
		recs[r.ID] = r
		raws = append(raws, raw)
	}
	return recs, raws, sc.Err()
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
		// embed.go, twin.go
		"newCircle", "lenBox", "boxLen",
		"Anything", "Host", "Host.Ping", "Pinger", "Pinger.Ping", "Prober", "Prober.Ping",
		// compute_fuzz.go declares no record: no configuration builds it
	), "go:example.com/mod_test.TestExternal")
	sort.Strings(want)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("ids:\n got  %v\n want %v", got, want)
	}
	checkRules(t, keys, rawKeys)
	// guards.go converts each type to each module interface that it implements, so each
	// coupled family is the whole family, and no site is optional.
	for _, r := range keys {
		if (r.Kind == "method" || r.Kind == "iface_method") && !reflect.DeepEqual(r.Coupled, r.Family) {
			t.Errorf("%s: coupled %v, family %v", r.ID, r.Coupled, r.Family)
		}
		for _, s := range r.Sites {
			if s.Optional {
				t.Errorf("%s: optional site %s:%d:%d", r.ID, s.File, s.Line, s.Col)
			}
		}
	}
}

// checkRules checks the rules that each key record follows.
func checkRules(t *testing.T, recs map[string]Record, raws []map[string]any) {
	t.Helper()
	// rel is on each use of a family member and on no other site; each use of a function or
	// a type is "self" (or "embedded" for a type); external is empty for a function or a type.
	// An optional site is a dnc use (or a use in a generated file) with a rel.
	rels := map[string]bool{"self": true, "embedded": true, "super": true, "sub": true, "sibling": true}
	for _, r := range recs {
		if r.External == nil || (len(r.External) != 0 && r.Kind != "method" && r.Kind != "iface_method") {
			t.Errorf("%s (%s): external %v", r.ID, r.Kind, r.External)
		}
		for _, s := range r.Sites {
			switch {
			case s.Class == "required" && !rels[s.Rel]:
				t.Errorf("%s: required site %s:%d:%d with rel %q", r.ID, s.File, s.Line, s.Col, s.Rel)
			case s.Class != "required" && s.Why != "generated" && !s.Optional && s.Rel != "":
				t.Errorf("%s: %s/%s site %s:%d:%d with rel %q", r.ID, s.Class, s.Why, s.File, s.Line, s.Col, s.Rel)
			case s.Optional && (s.Class != "dnc" || (s.Why != "use" && s.Why != "generated") || !rels[s.Rel]):
				t.Errorf("%s: optional site %s:%d:%d is %s/%s with rel %q", r.ID, s.File, s.Line, s.Col, s.Class, s.Why, s.Rel)
			case s.Optional && s.Rel == "self":
				t.Errorf("%s: optional site %s:%d:%d with rel self", r.ID, s.File, s.Line, s.Col)
			case s.Rel == "embedded" && r.Kind != "type" && r.Kind != "interface":
				t.Errorf("%s (%s): site %s:%d:%d with rel embedded", r.ID, r.Kind, s.File, s.Line, s.Col)
			case s.Rel != "" && s.Rel != "self" && s.Rel != "embedded" && r.Kind != "method" && r.Kind != "iface_method":
				t.Errorf("%s (%s): site %s:%d:%d with rel %q", r.ID, r.Kind, s.File, s.Line, s.Col, s.Rel)
			}
		}
		// coupled: sorted, a subset of family, with the record; only for a method and an
		// interface method.
		if r.Kind != "method" && r.Kind != "iface_method" {
			if r.Coupled != nil {
				t.Errorf("%s (%s): coupled %v", r.ID, r.Kind, r.Coupled)
			}
			continue
		}
		fam := map[string]bool{}
		for _, f := range r.Family {
			fam[f] = true
		}
		if !sort.StringsAreSorted(r.Coupled) || !hasEntry(r.Coupled, r.ID) {
			t.Errorf("%s: coupled %v is not sorted or has not the record", r.ID, r.Coupled)
		}
		for _, c := range r.Coupled {
			if !fam[c] {
				t.Errorf("%s: coupled member %s is not in the family %v", r.ID, c, r.Family)
			}
		}
	}
	fields := []string{"container", "decl", "external", "family", "id", "implementers", "kind", "lang", "name", "sites", "source"}
	methodFields := []string{"container", "coupled", "decl", "external", "family", "id", "implementers", "kind", "lang", "name", "sites", "source"}
	for _, raw := range raws {
		var names []string
		for k := range raw {
			names = append(names, k)
		}
		sort.Strings(names)
		want := fields
		if raw["kind"] == "method" || raw["kind"] == "iface_method" {
			want = methodFields
		}
		if !reflect.DeepEqual(names, want) {
			t.Fatalf("%v: fields %v, want %v", raw["id"], names, want)
		}
		if raw["lang"] != "go" || raw["source"] != "go/types" {
			t.Errorf("%v: lang %v source %v", raw["id"], raw["lang"], raw["source"])
		}
	}
	// One site for each position in each record.
	for _, r := range recs {
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
	// The type Base: the receiver, the embedded field, the selector and the literal key of
	// the embedded field name the type.
	checkSites(t, key(t, "Base"), "", []Site{
		site("embed.go", 4, 16, "required", "use", both), // the key Base: of Circle{...}
		site("embed.go", 4, 22, "required", "use", both),
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
		{ID: pkg + "Circle", File: "shapes.go", Line: 21, Col: 6, Class: "required"}, // through the embedded Base, *Circle
		{ID: pkg + "Square", File: "shapes.go", Line: 9, Col: 6, Class: "required"},
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
		`{"file":"compute_fuzz.go","line":3,"col":18,"in":"comment"}`,
		`{"file":"compute_fuzz.go","line":7,"col":9,"in":"code"}`,
		`{"file":"compute_fuzz.go","line":7,"col":35,"in":"string"}`,
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
	// The selector c.Base of the embedded field: "embedded" (TestRelEmbeddedForSelectorAndLiteralKey).
	checkRels(t, key(t, "Base"), "shapes.go", map[string]string{"18:9": "self", "22:2": "self", "39:23": "self", "40:11": "embedded"})
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

// A selector or a literal key that names an embedded field of the record's type is
// "embedded"; the type name on the embedding line stays "self". Also for an embedded
// interface (lenBox embeds Lener).
func TestRelEmbeddedForSelectorAndLiteralKey(t *testing.T) {
	base := key(t, "Base")
	checkRels(t, base, "shapes.go", map[string]string{
		"18:9":  "self",     // func (b Base) Area()
		"22:2":  "self",     // the embedding line in Circle
		"39:23": "self",     // the result type of baseOf
		"40:11": "embedded", // return c.Base
	})
	checkRels(t, base, "embed.go", map[string]string{
		"4:16": "embedded", // the key Base: of Circle{Base: Base{r: 1}}
		"4:22": "self",     // the type Base{r: 1}
	})
	lener := key(t, "Lener")
	checkRels(t, lener, "embed.go", map[string]string{
		"9:2":   "self",     // the embedding line in lenBox
		"12:23": "self",     // the result type of boxLen
		"13:11": "embedded", // return b.Lener
	})
	for _, s := range sitesIn(base, "embed.go") {
		if s.Class != "required" || s.Why != "use" {
			t.Errorf("Base site %s:%d:%d is %s/%s, want required/use", s.File, s.Line, s.Col, s.Class, s.Why)
		}
	}
}

// Pinger and Prober have the same method set; Host implements both. Anything has an empty
// method set: each interface satisfies it, so it gets no dnc entry.
func TestInterfaceImplementersHaveDncClass(t *testing.T) {
	cases := map[string][]Implementer{
		"Pinger": {
			{ID: pkg + "Host", File: "twin.go", Line: 12, Col: 6, Class: "required"},
			{ID: pkg + "Prober", File: "twin.go", Line: 8, Col: 6, Class: "dnc"},
		},
		"Prober": {
			{ID: pkg + "Host", File: "twin.go", Line: 12, Col: 6, Class: "required"},
			{ID: pkg + "Pinger", File: "twin.go", Line: 4, Col: 6, Class: "dnc"},
		},
	}
	for id, want := range cases {
		if got := key(t, id).Implementers; !reflect.DeepEqual(got, want) {
			t.Errorf("%s implementers:\n got  %+v\n want %+v", id, got, want)
		}
	}
	anything := key(t, "Anything")
	if len(anything.Implementers) == 0 {
		t.Errorf("Anything has no implementers")
	}
	for _, im := range anything.Implementers {
		if im.Class != "required" || keys[im.ID].Kind != "type" {
			t.Errorf("Anything implementer %+v (kind %s), want only types with class required", im, keys[im.ID].Kind)
		}
	}
}

// compute_fuzz.go has the build tag gofuzz, which no configuration sets. No load holds the
// file, so it declares no record, and each word of a record name in it is a dnc site with
// no configuration: a code word is "unproven", a comment or string word as in other files.
func TestUnbuiltFileSitesAreDnc(t *testing.T) {
	none := []string{} // JSON null decodes to nil and fails the compare
	c := key(t, "Compute")
	checkSites(t, c, "compute_fuzz.go", []Site{
		site("compute_fuzz.go", 3, 18, "dnc", "comment", none),
		site("compute_fuzz.go", 7, 9, "dnc", "unproven", none),
		site("compute_fuzz.go", 7, 35, "dnc", "string", none),
	})
	checkRels(t, c, "compute_fuzz.go", map[string]string{})
	if _, ok := keys[pkg+"fuzzCompute"]; ok {
		t.Errorf("a record for fuzzCompute, which no configuration builds")
	}
}

// testdata/cross: fakeConfigurer (configure_test.go, package cross) satisfies
// setter.Configurer, and fakeModule satisfies it through an embedded *fakeConfigurer. setter
// imports cross, so no test build of cross holds setter, and no universe of types.Implements
// has both. The method takes (n Counter), the interface method (c cross.Counter) of the plain
// package. The tree is not in testdata/mod: a folder there breaks a test of accept.
func TestCrossVariantImplementerIsDnc(t *testing.T) {
	ck, _, err := extractTree("testdata/cross")
	if err != nil {
		t.Fatal(err)
	}
	const cp, sp = "go:example.com/cross.", "go:example.com/cross/setter."
	want := []Implementer{
		{ID: cp + "fakeConfigurer", File: "configure_test.go", Line: 5, Col: 6, Class: "dnc"},
		{ID: cp + "fakeModule", File: "configure_test.go", Line: 10, Col: 6, Class: "dnc"},
	}
	if got := ck[sp+"Configurer"].Implementers; !reflect.DeepEqual(got, want) {
		t.Errorf("Configurer implementers:\n got  %+v\n want %+v", got, want)
	}
	// The families do not change.
	fc, cm := ck[cp+"fakeConfigurer.Configure"], ck[sp+"Configurer.Configure"]
	if !reflect.DeepEqual(fc.Family, []string{cp + "fakeConfigurer.Configure"}) {
		t.Errorf("fakeConfigurer.Configure family %v", fc.Family)
	}
	if !reflect.DeepEqual(cm.Family, []string{sp + "Configurer.Configure"}) {
		t.Errorf("Configurer.Configure family %v", cm.Family)
	}
	// The call through the interface is unproven for the method of the test type, with no rel.
	checkSites(t, fc, "", []Site{
		site("configure_test.go", 7, 23, "dnc", "decl", both),
		site("setter/setter.go", 7, 2, "forbidden", "decoy", both),
		site("setter/setter.go", 11, 11, "dnc", "unproven", both),
	})
	checkRels(t, fc, "", map[string]string{})
	checkRels(t, cm, "setter/setter.go", map[string]string{"11:11": "self"})
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

const coupledTree = "testdata/coupled"

const cpkg = "go:example.com/coupled."

var (
	coupledOnce sync.Once
	coupledKeys map[string]Record
	coupledRaw  []map[string]any
	coupledErr  error
)

// ckey gives a record of testdata/coupled; the first call extracts the keys of the tree.
func ckey(t *testing.T, id string) Record {
	t.Helper()
	coupledOnce.Do(func() { coupledKeys, coupledRaw, coupledErr = extractTree(coupledTree) })
	if coupledErr != nil {
		t.Fatal(coupledErr)
	}
	r, ok := coupledKeys[cpkg+id]
	if !ok {
		t.Fatalf("no record %s%s", cpkg, id)
	}
	return r
}

func cids(names ...string) []string {
	out := make([]string, len(names))
	for i, n := range names {
		out[i] = cpkg + n
	}
	return out
}

func TestCoupledKeysFollowTheRules(t *testing.T) {
	ckey(t, "P")
	checkRules(t, coupledKeys, coupledRaw)
}

// coupled.go and registry.go: P and Q have one method, and A, B, D, E, G, H and K implement
// both, so the nine methods are one family. The guard of A, the argument of B, the
// assignment of E to Q and the assignment of a P value to Q link five of them. G goes only to
// M, and m.(P) asserts a value of M to P (case 4). D reaches P only through an assertion from
// any, and H and K go to no interface.
func TestCoupledFamilyFollowsTheConversions(t *testing.T) {
	all := cids("A.Provision", "B.Provision", "D.Provision", "E.Provision", "G.Provision", "H.Provision",
		"K.Provision", "P.Provision", "Q.Provision")
	linked := cids("A.Provision", "B.Provision", "E.Provision", "G.Provision", "P.Provision", "Q.Provision")
	for _, n := range []string{"A.Provision", "B.Provision", "E.Provision", "G.Provision", "P.Provision", "Q.Provision",
		"D.Provision", "H.Provision", "K.Provision"} {
		r := ckey(t, n)
		if !reflect.DeepEqual(r.Family, all) {
			t.Errorf("%s family %v, want %v", n, r.Family, all)
		}
		want := linked
		if n == "D.Provision" || n == "H.Provision" || n == "K.Provision" {
			want = cids(n)
		}
		if !reflect.DeepEqual(r.Coupled, want) {
			t.Errorf("%s coupled %v, want %v", n, r.Coupled, want)
		}
	}
}

type useClass struct {
	class, rel string
	optional   bool
}

// useClasses gives the class of each use site of r in file ("line:col" → class, rel and
// optional), and checks that each use site has the why "use" and both configurations.
func useClasses(t *testing.T, r Record, file string) map[string]useClass {
	t.Helper()
	out := map[string]useClass{}
	for _, s := range sitesIn(r, file) {
		if s.Rel == "" {
			continue
		}
		if s.Why != "use" || !reflect.DeepEqual(s.Configs, both) {
			t.Errorf("%s: use site %s:%d:%d has why %q and configs %v", r.ID, s.File, s.Line, s.Col, s.Why, s.Configs)
		}
		out[fmt.Sprintf("%d:%d", s.Line, s.Col)] = useClass{s.Class, s.Rel, s.Optional}
	}
	return out
}

// coupled.go line 26 calls through P; lines 65 to 69 call the method of A, B, H, D and E.
func TestOptionalUseIsDncWithItsRel(t *testing.T) {
	req := func(rel string) useClass { return useClass{"required", rel, false} }
	opt := func(rel string) useClass { return useClass{"dnc", rel, true} }
	cases := map[string]map[string]useClass{
		"A.Provision": {"26:11": req("super"), "65:13": req("self"), "66:13": req("sibling"),
			"67:13": opt("sibling"), "68:13": opt("sibling"), "69:13": req("sibling")},
		"H.Provision": {"26:11": opt("super"), "65:13": opt("sibling"), "66:13": opt("sibling"),
			"67:13": req("self"), "68:13": opt("sibling"), "69:13": opt("sibling")},
		"P.Provision": {"26:11": req("self"), "65:13": req("sub"), "66:13": req("sub"),
			"67:13": opt("sub"), "68:13": opt("sub"), "69:13": req("sub")},
	}
	for n, want := range cases {
		if got := useClasses(t, ckey(t, n), "coupled.go"); !reflect.DeepEqual(got, want) {
			t.Errorf("%s uses:\n got  %v\n want %v", n, got, want)
		}
	}
	// registry.go line 23 calls through P; line 36 calls the method of G (case 4) and line
	// 37 the method of K.
	regCases := map[string]map[string]useClass{
		"A.Provision": {"23:12": req("super"), "36:13": req("sibling"), "37:13": opt("sibling")},
		"G.Provision": {"23:12": req("super"), "36:13": req("self"), "37:13": opt("sibling")},
		"K.Provision": {"23:12": opt("super"), "36:13": opt("sibling"), "37:13": req("self")},
	}
	for n, want := range regCases {
		if got := useClasses(t, ckey(t, n), "registry.go"); !reflect.DeepEqual(got, want) {
			t.Errorf("%s uses in registry.go:\n got  %v\n want %v", n, got, want)
		}
	}
	// The declarations of the family stay dnc declarations, also of a member outside the
	// coupled family.
	for _, s := range sitesIn(ckey(t, "A.Provision"), "coupled.go") {
		if s.Why == "decl" && (s.Class != "dnc" || s.Optional || s.Rel != "") {
			t.Errorf("A.Provision: declaration site %s:%d:%d is %+v", s.File, s.Line, s.Col, s)
		}
	}
}

// assert.go: s.(Halter) links Stop of Stopper and Halter, and the case Waiter of a type
// switch on a Stopper links Pause of Stopper and Waiter. Neither interface has the method set
// of the other one. Both implements the three interfaces, and its value goes to no interface.
func TestAssertionLinksTheCommonMethod(t *testing.T) {
	stop := cids("Both.Stop", "Halter.Stop", "Stopper.Stop")
	pause := cids("Both.Pause", "Stopper.Pause", "Waiter.Pause")
	cases := map[string][2][]string{ // id → family, coupled
		"Stopper.Stop":  {stop, cids("Halter.Stop", "Stopper.Stop")},
		"Halter.Stop":   {stop, cids("Halter.Stop", "Stopper.Stop")},
		"Both.Stop":     {stop, cids("Both.Stop")},
		"Stopper.Pause": {pause, cids("Stopper.Pause", "Waiter.Pause")},
		"Waiter.Pause":  {pause, cids("Stopper.Pause", "Waiter.Pause")},
		"Halter.Resume": {cids("Both.Resume", "Halter.Resume"), cids("Halter.Resume")},
	}
	for n, want := range cases {
		r := ckey(t, n)
		if !reflect.DeepEqual(r.Family, want[0]) || !reflect.DeepEqual(r.Coupled, want[1]) {
			t.Errorf("%s: family %v coupled %v, want %v and %v", n, r.Family, r.Coupled, want[0], want[1])
		}
	}
}

// viaParam returns a value of its type parameter as a P: no link, and the statistics count
// the conversion one time (the two configurations give the same pair).
func TestTypeParamConversionIsCountedWithNoLink(t *testing.T) {
	_, st, err := extract(coupledTree, both)
	if err != nil {
		t.Fatal(err)
	}
	if len(st.paramConv) != 1 {
		t.Errorf("conversions with a type parameter: %v, want one", st.paramConv)
	}
	if st.narrow == 0 || st.optional["sibling"] == 0 {
		t.Errorf("narrow %d, optional %v: want both above zero", st.narrow, st.optional)
	}
}

// Case 4 adds one link (G.Provision and P.Provision, registry.go), and a return statement
// gives its conversion edge, not an assertion.
func TestCase4LinksAreCounted(t *testing.T) {
	_, st, err := extract(coupledTree, both)
	if err != nil {
		t.Fatal(err)
	}
	if st.case4 != 1 || st.case4Edge != 0 {
		t.Errorf("case 4 links %d, with an assertion edge %d: want 1 and 0", st.case4, st.case4Edge)
	}
}
