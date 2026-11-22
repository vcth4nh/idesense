package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
)

// outLine is one output line of the subcommand accept.
type outLine struct {
	ID      string   `json:"id"`
	Kind    string   `json:"kind"`
	OK      *bool    `json:"ok"`
	Errors  []string `json:"errors"`
	Renamed int      `json:"renamed"`
	Skipped string   `json:"skipped"`
}

type acceptResult struct {
	code    int
	lines   []outLine
	raw     []map[string]any
	stderr  string
	scratch string
}

// writeKeys writes recs to a JSONL file in a new temporary folder and returns its path.
func writeKeys(t *testing.T, recs ...Record) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "keys.jsonl")
	if err := writeJSONL(p, recs); err != nil {
		t.Fatal(err)
	}
	return p
}

// runAccept runs "gokeys accept" with a new scratch folder and decodes its output lines.
func runAccept(t *testing.T, tree, keysFile string, args ...string) acceptResult {
	t.Helper()
	res := acceptResult{scratch: filepath.Join(t.TempDir(), "scratch")}
	full := append([]string{"accept", "-tree", tree, "-keys", keysFile, "-scratch", res.scratch}, args...)
	var out, errb bytes.Buffer
	res.code = run(full, &out, &errb)
	res.stderr = errb.String()
	sc := bufio.NewScanner(&out)
	for sc.Scan() {
		var l outLine
		if err := json.Unmarshal(sc.Bytes(), &l); err != nil {
			t.Fatalf("output line %q: %v", sc.Text(), err)
		}
		var raw map[string]any
		if err := json.Unmarshal(sc.Bytes(), &raw); err != nil {
			t.Fatal(err)
		}
		res.lines = append(res.lines, l)
		res.raw = append(res.raw, raw)
	}
	return res
}

// one checks that the run printed exactly one line and returns it.
func (r acceptResult) one(t *testing.T) outLine {
	t.Helper()
	if len(r.lines) != 1 {
		t.Fatalf("%d output lines, want 1; exit %d; stderr: %s", len(r.lines), r.code, r.stderr)
	}
	return r.lines[0]
}

func fieldNames(raw map[string]any) []string {
	var names []string
	for k := range raw {
		names = append(names, k)
	}
	sort.Strings(names)
	return names
}

// withoutSites returns a copy of r with no site at the given "file:line:col" positions. The
// slices of the records in keys are shared, so the copy gets a new slice.
func withoutSites(t *testing.T, r Record, positions ...string) Record {
	t.Helper()
	drop := map[string]bool{}
	for _, p := range positions {
		drop[p] = true
	}
	var sites []Site
	for _, s := range r.Sites {
		p := s.File + ":" + itoa(s.Line) + ":" + itoa(s.Col)
		if drop[p] {
			delete(drop, p)
			continue
		}
		sites = append(sites, s)
	}
	if len(drop) != 0 {
		t.Fatalf("%s has no site at %v", r.ID, drop)
	}
	r.Sites = sites
	return r
}

func itoa(n int) string {
	b, _ := json.Marshal(n)
	return string(b)
}

// treeDigest gives the hash and the mode of each file below root.
func treeDigest(t *testing.T, root string) map[string]string {
	t.Helper()
	out := map[string]string{}
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		b, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		sum := sha256.Sum256(b)
		out[path] = hex.EncodeToString(sum[:]) + " " + info.Mode().String()
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}

// scratchDirs lists the folders directly below the scratch folder (none when it is absent).
func scratchDirs(t *testing.T, scratch string) []string {
	t.Helper()
	ents, err := os.ReadDir(scratch)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		t.Fatal(err)
	}
	var out []string
	for _, e := range ents {
		out = append(out, filepath.Join(scratch, e.Name()))
	}
	return out
}

func anyContains(list []string, part string) bool {
	for _, s := range list {
		if strings.Contains(s, part) {
			return true
		}
	}
	return false
}

// Shape.Area: three declarations, the call through the interface and the call of the method
// that Circle gets from Base. The tree stays unchanged, and the scratch folder of the id is
// removed.
func TestAcceptPassesForCompleteKey(t *testing.T) {
	r := key(t, "Shape.Area")
	before := treeDigest(t, testTree)
	res := runAccept(t, testTree, writeKeys(t, r), "-ids", r.ID, "-configs", "linux,windows")
	l := res.one(t)
	if res.code != 0 || l.ID != r.ID || l.Kind != "iface_method" || l.OK == nil || !*l.OK || l.Renamed != 5 || len(l.Errors) != 0 {
		t.Fatalf("exit %d, line %+v (ok %v); stderr: %s", res.code, l, l.OK, res.stderr)
	}
	if got, want := fieldNames(res.raw[0]), []string{"errors", "id", "kind", "ok", "renamed"}; !reflect.DeepEqual(got, want) {
		t.Errorf("fields %v, want %v", got, want)
	}
	if !strings.Contains(res.stderr, "ok 1, failed 0, skipped 0") {
		t.Errorf("stderr has no count line: %s", res.stderr)
	}
	if d := scratchDirs(t, res.scratch); len(d) != 0 {
		t.Errorf("scratch folders left: %v", d)
	}
	if after := treeDigest(t, testTree); !reflect.DeepEqual(before, after) {
		t.Errorf("the tree changed")
	}
}

// Without the site of c.Area() (shapes.go:36:11) the rename leaves a call of a method that is
// gone.
func TestAcceptFailsWhenOneRequiredSiteIsAbsent(t *testing.T) {
	r := withoutSites(t, key(t, "Shape.Area"), "shapes.go:36:11")
	res := runAccept(t, testTree, writeKeys(t, r), "-ids", r.ID, "-configs", "linux,windows")
	l := res.one(t)
	if res.code != 1 || l.OK == nil || *l.OK || l.Renamed != 4 {
		t.Fatalf("exit %d, line %+v (ok %v); stderr: %s", res.code, l, l.OK, res.stderr)
	}
	if len(l.Errors) == 0 || len(l.Errors) > 5 || !anyContains(l.Errors, "shapes.go:36:") {
		t.Errorf("errors %q: want 1 to 5 with one at shapes.go:36", l.Errors)
	}
	if !strings.Contains(res.stderr, "ok 0, failed 1, skipped 0") {
		t.Errorf("stderr has no count line: %s", res.stderr)
	}
}

// Compute has a call in only_windows.go. Without that site, the Linux build passes and the
// Windows build fails.
func TestAcceptCoversWindowsOnlyFile(t *testing.T) {
	c := key(t, "Compute")
	res := runAccept(t, testTree, writeKeys(t, c), "-ids", c.ID, "-configs", "linux,windows")
	if l := res.one(t); res.code != 0 || l.OK == nil || !*l.OK || l.Renamed != 9 {
		t.Fatalf("complete key: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}

	part := withoutSites(t, c, "only_windows.go:4:9")
	keysFile := writeKeys(t, part)
	res = runAccept(t, testTree, keysFile, "-ids", c.ID, "-configs", "linux")
	if l := res.one(t); res.code != 0 || l.OK == nil || !*l.OK || l.Renamed != 8 {
		t.Fatalf("linux only: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	res = runAccept(t, testTree, keysFile, "-ids", c.ID, "-configs", "linux,windows")
	l := res.one(t)
	if res.code != 1 || l.OK == nil || *l.OK {
		t.Fatalf("linux,windows: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	if !anyContains(l.Errors, "windows: only_windows.go:4:") || anyContains(l.Errors, "linux:") {
		t.Errorf("errors %q: want one of windows at only_windows.go:4 and none of linux", l.Errors)
	}
}

func TestAcceptSkipsExternalRecord(t *testing.T) {
	r := key(t, "Celsius.String")
	if !hasEntry(r.External, "super:fmt.Stringer.String") {
		t.Fatalf("Celsius.String external %v", r.External)
	}
	res := runAccept(t, testTree, writeKeys(t, r), "-ids", r.ID, "-configs", "linux")
	l := res.one(t)
	if res.code != 0 || l.ID != r.ID || l.Kind != "method" || l.OK != nil || l.Skipped != "external" {
		t.Fatalf("exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	if v, ok := res.raw[0]["ok"]; !ok || v != nil {
		t.Errorf("ok is %v (present %v), want null", v, ok)
	}
	if got, want := fieldNames(res.raw[0]), []string{"id", "kind", "ok", "skipped"}; !reflect.DeepEqual(got, want) {
		t.Errorf("fields %v, want %v", got, want)
	}
	if !strings.Contains(res.stderr, "ok 0, failed 0, skipped 1") {
		t.Errorf("stderr has no count line: %s", res.stderr)
	}
	if d := scratchDirs(t, res.scratch); len(d) != 0 {
		t.Errorf("scratch folders for a skipped id: %v", d)
	}
}

// Hatch.Open: g.Open() (closure.go:37:9) calls Gate.Open, a sibling of Hatch.Open. The rename
// changes it, and each other Open of closure.go, and the build is clean.
func TestAcceptRenamesSiblingSites(t *testing.T) {
	r := key(t, "Hatch.Open")
	var rel string
	for _, s := range r.Sites {
		if s.File == "closure.go" && s.Line == 37 && s.Col == 9 {
			rel = s.Rel
		}
	}
	if rel != "sibling" {
		t.Fatalf("closure.go:37:9 of Hatch.Open has rel %q, want sibling", rel)
	}
	res := runAccept(t, testTree, writeKeys(t, r), "-ids", r.ID, "-configs", "linux,windows", "-keep")
	l := res.one(t)
	if res.code != 0 || l.OK == nil || !*l.OK || l.Renamed != 9 {
		t.Fatalf("exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	dirs := scratchDirs(t, res.scratch)
	if len(dirs) != 1 {
		t.Fatalf("kept scratch folders %v, want 1", dirs)
	}
	got, err := os.ReadFile(filepath.Join(dirs[0], "closure.go"))
	if err != nil {
		t.Fatal(err)
	}
	orig, err := os.ReadFile(filepath.Join(testTree, "closure.go"))
	if err != nil {
		t.Fatal(err)
	}
	want := strings.ReplaceAll(string(orig), "Open()", "OpenZq9()")
	if string(got) != want {
		t.Errorf("closure.go of the copy:\n%s\nwant:\n%s", got, want)
	}
	if !strings.Contains(string(got), "\tb := g.OpenZq9()\n") {
		t.Errorf("the sibling call is not renamed")
	}
}

// A site whose text is not the name fails the id with an error that names the site, and no
// package loads.
func TestAcceptFailsOnWrongPosition(t *testing.T) {
	c := key(t, "Compute")
	for _, tc := range []struct {
		name string
		edit func(*Site)
		want string
	}{
		{"column", func(s *Site) { s.Col++ }, "funcs.go:4:7"},
		{"line", func(s *Site) { s.Line = 99 }, "funcs.go:99:6"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			r := c
			r.Sites = append([]Site(nil), c.Sites...)
			for i := range r.Sites {
				if r.Sites[i].File == "funcs.go" && r.Sites[i].Why == "decl" {
					tc.edit(&r.Sites[i])
				}
			}
			res := runAccept(t, testTree, writeKeys(t, r), "-ids", r.ID, "-configs", "linux")
			l := res.one(t)
			if res.code != 1 || l.OK == nil || *l.OK || l.Renamed != 0 {
				t.Fatalf("exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
			}
			if len(l.Errors) != 1 || !strings.Contains(l.Errors[0], tc.want) {
				t.Errorf("errors %q: want one that names %s", l.Errors, tc.want)
			}
		})
	}
}

// With a manifest next to the tree, the copy has only the files of the manifest: junk.go is
// not in it and does not parse.
func TestAcceptCopiesOnlyManifestFiles(t *testing.T) {
	base := t.TempDir()
	tree := filepath.Join(base, "tree")
	var manifest strings.Builder
	ents, err := os.ReadDir(testTree)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(tree, 0o755); err != nil {
		t.Fatal(err)
	}
	for _, e := range ents {
		b, err := os.ReadFile(filepath.Join(testTree, e.Name()))
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(tree, e.Name()), b, 0o644); err != nil {
			t.Fatal(err)
		}
		sum := sha256.Sum256(b)
		manifest.WriteString(hex.EncodeToString(sum[:]) + "  " + e.Name() + "\n")
	}
	if err := os.WriteFile(filepath.Join(tree, "junk.go"), []byte("package mod\n\nfunc junk( {\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	c := key(t, "Compute")
	keysFile := writeKeys(t, c)

	// No manifest: the walk copies junk.go, and the load error fails the id.
	res := runAccept(t, tree, keysFile, "-ids", c.ID, "-configs", "linux")
	if l := res.one(t); res.code != 1 || l.OK == nil || *l.OK || !anyContains(l.Errors, "junk.go") {
		t.Fatalf("no manifest: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	if err := os.WriteFile(tree+".manifest", []byte(manifest.String()), 0o644); err != nil {
		t.Fatal(err)
	}
	res = runAccept(t, tree, keysFile, "-ids", c.ID, "-configs", "linux")
	if l := res.one(t); res.code != 0 || l.OK == nil || !*l.OK {
		t.Fatalf("manifest: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
}

// The sample takes only records with an empty external list, one kind after the other, and
// the same seed gives the same ids. Each site of these records is in a file that is not in
// the tree, so that each id fails before a load: the test reads only the selection.
func TestAcceptSampleIsStableAndSpreadOverKinds(t *testing.T) {
	var recs []Record
	for _, r := range keys {
		r.Sites = []Site{{File: "absent.go", Line: 1, Col: 1, Class: "dnc", Why: "decl"}}
		recs = append(recs, r)
	}
	sort.Slice(recs, func(a, b int) bool { return recs[a].ID < recs[b].ID })
	keysFile := writeKeys(t, recs...)
	sample := func(seed string) []outLine {
		res := runAccept(t, testTree, keysFile, "-sample", "10", "-seed", seed, "-configs", "linux")
		if len(res.lines) != 10 || res.code != 1 {
			t.Fatalf("seed %s: exit %d, %d lines; stderr: %s", seed, res.code, len(res.lines), res.stderr)
		}
		return res.lines
	}
	ids := func(ls []outLine) []string {
		var out []string
		for _, l := range ls {
			out = append(out, l.ID)
		}
		return out
	}
	one := sample("1")
	perKind := map[string]int{}
	seen := map[string]bool{}
	for _, l := range one {
		perKind[l.Kind]++
		if seen[l.ID] {
			t.Errorf("id %s two times", l.ID)
		}
		seen[l.ID] = true
		if r := keys[l.ID]; len(r.External) != 0 {
			t.Errorf("sampled %s with external %v", l.ID, r.External)
		}
		if !anyContains(l.Errors, "absent.go:1:1") {
			t.Errorf("%s: errors %q", l.ID, l.Errors)
		}
	}
	want := map[string]int{"func": 2, "iface_method": 2, "interface": 2, "method": 2, "type": 2}
	if !reflect.DeepEqual(perKind, want) {
		t.Errorf("ids by kind %v, want %v", perKind, want)
	}
	if again := sample("1"); !reflect.DeepEqual(ids(again), ids(one)) {
		t.Errorf("seed 1 gave two selections:\n %v\n %v", ids(one), ids(again))
	}
	if other := sample("2"); reflect.DeepEqual(ids(other), ids(one)) {
		t.Errorf("seed 2 gave the selection of seed 1: %v", ids(one))
	}
}

// -ids @file reads one id on each line, in the order of the file; -ids and -sample are
// mutually exclusive; an id with no record stops the run before any work.
func TestAcceptIdsFileAndFlagRules(t *testing.T) {
	a, b := key(t, "Celsius.String"), key(t, "ByteSink.Write")
	keysFile := writeKeys(t, a, b)
	list := filepath.Join(t.TempDir(), "ids.txt")
	if err := os.WriteFile(list, []byte(b.ID+"\n\n"+a.ID+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	res := runAccept(t, testTree, keysFile, "-ids", "@"+list, "-configs", "linux")
	if res.code != 0 || len(res.lines) != 2 || res.lines[0].ID != b.ID || res.lines[1].ID != a.ID {
		t.Fatalf("@file: exit %d, lines %+v; stderr: %s", res.code, res.lines, res.stderr)
	}
	res = runAccept(t, testTree, keysFile, "-ids", a.ID+","+b.ID, "-configs", "linux")
	if res.code != 0 || len(res.lines) != 2 || res.lines[0].ID != a.ID || res.lines[1].ID != b.ID {
		t.Fatalf("comma list: exit %d, lines %+v; stderr: %s", res.code, res.lines, res.stderr)
	}
	if res = runAccept(t, testTree, keysFile, "-ids", a.ID, "-sample", "3", "-configs", "linux"); res.code != 2 || len(res.lines) != 0 {
		t.Errorf("-ids with -sample: exit %d, %d lines", res.code, len(res.lines))
	}
	if res = runAccept(t, testTree, keysFile, "-configs", "linux"); res.code != 2 || len(res.lines) != 0 {
		t.Errorf("no -ids and no -sample: exit %d, %d lines", res.code, len(res.lines))
	}
	res = runAccept(t, testTree, keysFile, "-ids", a.ID+",go:example.com/mod.Nothing", "-configs", "linux")
	if res.code != 1 || len(res.lines) != 0 || !strings.Contains(res.stderr, "go:example.com/mod.Nothing") {
		t.Errorf("unknown id: exit %d, %d lines, stderr: %s", res.code, len(res.lines), res.stderr)
	}
}

// coupledKeysFile writes each record of testdata/coupled to a key file; a record of repl
// takes the place of the record with its id.
func coupledKeysFile(t *testing.T, repl ...Record) string {
	t.Helper()
	ckey(t, "P")
	by := map[string]Record{}
	for id, r := range coupledKeys {
		by[id] = r
	}
	for _, r := range repl {
		by[r.ID] = r
	}
	recs := make([]Record, 0, len(by))
	for _, r := range by {
		recs = append(recs, r)
	}
	sort.Slice(recs, func(a, b int) bool { return recs[a].ID < recs[b].ID })
	return writeKeys(t, recs...)
}

// The minimal rename of A.Provision renames the declarations of A, B, E, G, P and Q and the
// six required uses (coupled.go lines 26, 65, 66 and 69, registry.go lines 23 and 36). The
// calls on D, H and K and their declarations keep the name, and the tree builds in each
// configuration. The full rename renames the nine declarations and the nine uses.
func TestAcceptMinimalRenamePasses(t *testing.T) {
	r := ckey(t, "A.Provision")
	keysFile := coupledKeysFile(t)
	res := runAccept(t, coupledTree, keysFile, "-ids", r.ID, "-configs", "linux,windows", "-minimal", "-keep")
	l := res.one(t)
	if res.code != 0 || l.OK == nil || !*l.OK || l.Renamed != 12 || len(l.Errors) != 0 {
		t.Fatalf("minimal: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	if got, want := fieldNames(res.raw[0]), []string{"errors", "id", "kind", "ok", "renamed"}; !reflect.DeepEqual(got, want) {
		t.Errorf("fields %v, want %v", got, want)
	}
	dirs := scratchDirs(t, res.scratch)
	if len(dirs) != 1 {
		t.Fatalf("kept scratch folders %v, want 1", dirs)
	}
	for file, want := range map[string]map[int]bool{
		"coupled.go": {6: true, 10: true, 16: true, 23: true, 26: true, 36: false, 41: false,
			52: true, 65: true, 66: true, 67: false, 68: false, 69: true},
		"registry.go": {13: true, 23: true, 33: false, 36: true, 37: false},
	} {
		b, err := os.ReadFile(filepath.Join(dirs[0], file))
		if err != nil {
			t.Fatal(err)
		}
		lines := strings.Split(string(b), "\n")
		for n, renamed := range want {
			if got := strings.Contains(lines[n-1], "Provision"+renameSuffix); got != renamed {
				t.Errorf("%s:%d renamed %v, want %v: %q", file, n, got, renamed, lines[n-1])
			}
		}
	}
	res = runAccept(t, coupledTree, keysFile, "-ids", r.ID, "-configs", "linux,windows")
	if l := res.one(t); res.code != 0 || l.OK == nil || !*l.OK || l.Renamed != 18 {
		t.Fatalf("full: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
}

// A rename of only A.Provision and its call (no other declaration of the coupled family)
// does not build: the guard of A (coupled.go line 18) fails.
func TestAcceptMinimalFailsWithNoCoupledDeclaration(t *testing.T) {
	r := ckey(t, "A.Provision")
	r.Coupled = []string{r.ID}
	var sites []Site
	for _, s := range r.Sites {
		if s.Why == "decl" || s.Rel == "self" {
			sites = append(sites, s)
		}
	}
	r.Sites = sites
	res := runAccept(t, coupledTree, coupledKeysFile(t, r), "-ids", r.ID, "-configs", "linux", "-minimal")
	l := res.one(t)
	if res.code != 1 || l.OK == nil || *l.OK || l.Renamed != 2 {
		t.Fatalf("exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	if !anyContains(l.Errors, "linux: coupled.go:18:") {
		t.Errorf("errors %q: want one at coupled.go:18", l.Errors)
	}
}

// With a coupled family smaller than the family, the minimal mode finds a declaration of the
// family through the decl of its record: with no record of a member, or with no coupled
// list, the id fails before a load and the error says why.
func TestAcceptMinimalNeedsTheFamilyRecordsAndCoupled(t *testing.T) {
	r := ckey(t, "A.Provision")
	res := runAccept(t, coupledTree, writeKeys(t, r), "-ids", r.ID, "-configs", "linux", "-minimal")
	l := res.one(t)
	if res.code != 1 || l.OK == nil || *l.OK || l.Renamed != 0 || len(l.Errors) != 1 ||
		!strings.Contains(l.Errors[0], cpkg+"B.Provision") {
		t.Fatalf("no family records: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
	if d := scratchDirs(t, res.scratch); len(d) != 0 {
		t.Errorf("scratch folders left: %v", d)
	}
	old := r
	old.Coupled = nil
	res = runAccept(t, coupledTree, coupledKeysFile(t, old), "-ids", r.ID, "-configs", "linux", "-minimal")
	if l := res.one(t); res.code != 1 || l.OK == nil || *l.OK || len(l.Errors) != 1 || !strings.Contains(l.Errors[0], "coupled") {
		t.Fatalf("no coupled list: exit %d, line %+v; stderr: %s", res.code, l, res.stderr)
	}
}

// A coupled family that is the whole family (Shape.Area of testdata/mod) and a function
// (Compute, no coupled list) give the sites of the full rename.
func TestAcceptMinimalEqualsFullForWholeFamily(t *testing.T) {
	area, compute := key(t, "Shape.Area"), key(t, "Compute")
	res := runAccept(t, testTree, writeKeys(t, compute, area), "-ids", area.ID+","+compute.ID, "-configs", "linux,windows", "-minimal")
	if res.code != 0 || len(res.lines) != 2 || res.lines[0].Renamed != 5 || res.lines[1].Renamed != 9 {
		t.Fatalf("exit %d, lines %+v; stderr: %s", res.code, res.lines, res.stderr)
	}
}
