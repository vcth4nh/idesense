package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"go/types"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"golang.org/x/tools/go/packages"
	"golang.org/x/tools/go/types/typeutil"
	"golang.org/x/tools/refactor/satisfy"
)

// Record is one key record (the key model of Task 1, plus `external` and `coupled`). Each
// position is 1-based; the column counts UTF-16 code units. Coupled is set only for a method
// and an interface method (see coupledFamily).
type Record struct {
	ID           string        `json:"id"`
	Lang         string        `json:"lang"`
	Kind         string        `json:"kind"`
	Name         string        `json:"name"`
	Container    string        `json:"container"`
	Decl         Pos           `json:"decl"`
	Family       []string      `json:"family"`
	Coupled      []string      `json:"coupled,omitempty"`
	Sites        []Site        `json:"sites"`
	Implementers []Implementer `json:"implementers"`
	External     []string      `json:"external"`
	Source       string        `json:"source"`
}

type Pos struct {
	File string `json:"file"`
	Line int    `json:"line"`
	Col  int    `json:"col"`
}

// Site is one occurrence of the name of a record. Rel is set on a use that resolves to a
// family member: "self", "embedded" (a selector or a literal key that names an embedded
// field of the record's type), "super", "sub" or "sibling". Optional is set on a use whose
// family members are all outside the coupled family: its class is "dnc".
type Site struct {
	File     string   `json:"file"`
	Line     int      `json:"line"`
	Col      int      `json:"col"`
	Class    string   `json:"class"`
	Why      string   `json:"why"`
	Configs  []string `json:"configs"`
	Rel      string   `json:"rel,omitempty"`
	Optional bool     `json:"optional,omitempty"`
}

// Implementer is one module type that implements an interface record: Class "required" for
// a type that is no interface, "dnc" for another module interface whose method set
// satisfies the record's interface, and "dnc" for a type or interface that satisfies it only
// across package variants (no build holds both, see crossVariant).
type Implementer struct {
	ID    string `json:"id"`
	File  string `json:"file"`
	Line  int    `json:"line"`
	Col   int    `json:"col"`
	Class string `json:"class"`
}

// The mode of the brief, plus NeedName for the package paths.
const loadMode = packages.NeedName | packages.NeedTypes | packages.NeedTypesInfo |
	packages.NeedSyntax | packages.NeedDeps | packages.NeedImports

// extPrefix marks, in methodOf, a method declared outside the module.
const extPrefix = "ext:"

// The methods that the standard library finds through unnamed interfaces.
var magicNames = map[string]bool{"Unwrap": true, "Is": true, "As": true, "Timeout": true, "Temporary": true}

type decl struct {
	kind, name, container string
	typeID                string // the id of the type or interface of a method or interface method
	pos                   Pos    // from the first configuration that declares it
}

type posKey struct {
	file      string
	line, col int
}

// A role is one resolution of an identifier: a use (Info.Uses) or a definition
// (Info.Defs). id is the id of a module declaration, or "" for any other object. ext is
// true for a use of an object that is declared outside the module. embed is true for the
// use of a type through an embedded field that the type names (a selector or a key).
type role struct {
	def   bool
	ext   bool
	embed bool
	id    string
}

type codeSite struct {
	name    string
	present uint32   // bit i: the identifier is in the build of configs[i]
	roles   [][]role // the roles of the identifier, by configuration index
}

func (c *codeSite) add(ci int, r role) {
	for _, have := range c.roles[ci] {
		if have == r {
			return
		}
	}
	c.roles[ci] = append(c.roles[ci], r)
}

type textSite struct {
	name, in string // in: "comment" or "string"
}

type relResult struct {
	rel string
	ok  bool
}

type extractor struct {
	roots   []string // the tree root, and its form with symlinks resolved
	configs []string

	decls         map[string]*decl
	rel           map[string]map[string]bool            // type id → ids of the module interfaces that the type or its pointer implements
	methodOf      map[string]map[string]map[string]bool // type id → method name → ids of the methods that the name selects (extPrefix: outside the module)
	ifaceNames    map[string]map[string]bool            // module interface id → names of its method set
	libSuper      map[string]map[string]bool            // module type id → library interfaces (and "error") that the type or its pointer implements
	libIfaceNames map[string]map[string]bool            // library interface id → names of its method set
	libImpl       map[string]map[string]bool            // module interface id → library types that implement it
	cross         map[string]map[string]bool            // type id → module interfaces that it satisfies by method names and signature strings (crossVariant)
	links         map[string]map[string]bool            // method id → the methods that a conversion or an assertion links to it (linker.pair, x.viaAssertions)
	code          map[posKey]*codeSite
	unbuiltCode   map[posKey]string // the code words of the files that no configuration builds
	text          map[posKey]*textSite
	fileCfg       map[string]uint32 // file → configurations whose build has it
	generated     map[string]bool   // file → it has a "Code generated" header
	src           map[string][]byte // file → content
	relCache      map[string]relResult

	// The facts of case 4 (x.viaAssertions), with the type keys of linker.typeKey, so that a
	// fact of one load meets the facts of each other load.
	toIface     map[string]map[string]bool   // interface → the non-interface types that a conversion gives to it
	fromIface   map[string]map[string]bool   // interface → the interfaces whose values a conversion gives to it
	asserted    map[string]map[string]bool   // interface with a method → the interfaces that an assertion on its value asks for
	assertGives map[string]map[string]bool   // interface → the types that an assertion on its value asks for and that it can hold
	msets       map[string][]map[string]msel // type → its method set in each load and package variant: method key → method

	// Indexes for the families, made by records().
	selectedBy     map[string]map[string][]string // method name → method id → type ids whose method set selects it
	implementersOf map[string][]string            // interface id → type ids that implement it
	oneStepMemo    map[string][]string

	st stats
}

type stats struct {
	loads    []string
	aliases  map[string]bool
	generic  map[string]bool
	kinds    map[string]int
	classes  map[string]int
	rels     map[string]int // required sites by rel
	external map[string]int // records with a non-empty external list, by kind
	dncImpls int            // implementers entries with the class dnc
	crossImp int            // of these, the entries across package variants
	dncIface int            // interface records with such an entry
	noConfig int            // sites with no configuration (in a file that no configuration builds)
	unbuilt  []string       // the files that no configuration builds

	links     int             // pairs of linked method declarations
	paramConv map[string]bool // the type pairs of the conversions with a type parameter on one side (no link)
	narrow    int             // method records whose coupled family is smaller than the family
	optional  map[string]int  // optional sites by rel
	mixed     int             // uses that resolve to a coupled member and to another member (in two configurations)
	case4     int             // links that only case 4 gives (x.viaAssertions)
	case4Edge int             // of these, the links with a conversion edge that an assertion also gives
}

func (s *stats) print(w io.Writer, total time.Duration) {
	for _, l := range s.loads {
		fmt.Fprintln(w, l)
	}
	fmt.Fprintf(w, "records: %s\n", countLine(s.kinds))
	fmt.Fprintf(w, "sites: %s\n", countLine(s.classes))
	fmt.Fprintf(w, "required sites by rel: %s\n", countLine(s.rels))
	fmt.Fprintf(w, "records with external entries: %s\n", countLine(s.external))
	fmt.Fprintf(w, "implementers with the class dnc: %d (%d across package variants), in %d interface records\n", s.dncImpls, s.crossImp, s.dncIface)
	fmt.Fprintf(w, "links between method declarations: %d\n", s.links)
	fmt.Fprintf(w, "links that only case 4 gives (an assertion on a value of an interface with a method): %d, %d with a conversion edge that an assertion also gives\n", s.case4, s.case4Edge)
	fmt.Fprintf(w, "conversions with a type parameter on one side (no link): %d type pairs\n", len(s.paramConv))
	fmt.Fprintf(w, "method records with a coupled family smaller than the family: %d\n", s.narrow)
	fmt.Fprintf(w, "optional sites by rel: %s\n", countLine(s.optional))
	fmt.Fprintf(w, "required uses with a member outside the coupled family in another configuration: %d\n", s.mixed)
	fmt.Fprintf(w, "files that no configuration builds: %d %v\n", len(s.unbuilt), s.unbuilt)
	fmt.Fprintf(w, "sites with no configuration: %d\n", s.noConfig)
	fmt.Fprintf(w, "type aliases (no record): %d\n", len(s.aliases))
	fmt.Fprintf(w, "generic types (no implements check): %d\n", len(s.generic))
	fmt.Fprintf(w, "time: %.1fs\n", total.Seconds())
}

func countLine(m map[string]int) string {
	var keys []string
	sum := 0
	for k, n := range m {
		keys = append(keys, k)
		sum += n
	}
	sort.Strings(keys)
	parts := []string{fmt.Sprint(sum)}
	for _, k := range keys {
		parts = append(parts, fmt.Sprintf("%s %d", k, m[k]))
	}
	return strings.Join(parts, ", ")
}

// extract loads the module at tree one time for each configuration (GOOS) and returns its
// key records, sorted by id.
func extract(tree string, configs []string) ([]Record, *stats, error) {
	if len(configs) == 0 || len(configs) > 32 {
		return nil, nil, fmt.Errorf("give 1 to 32 configurations")
	}
	seen := map[string]bool{}
	for _, c := range configs {
		if seen[c] {
			return nil, nil, fmt.Errorf("configuration %s two times", c)
		}
		seen[c] = true
	}
	abs, err := filepath.Abs(tree)
	if err != nil {
		return nil, nil, err
	}
	roots := []string{abs}
	if real, err := filepath.EvalSymlinks(abs); err == nil && real != abs {
		roots = append(roots, real)
	}
	x := &extractor{
		roots:         roots,
		configs:       configs,
		decls:         map[string]*decl{},
		rel:           map[string]map[string]bool{},
		methodOf:      map[string]map[string]map[string]bool{},
		ifaceNames:    map[string]map[string]bool{},
		libSuper:      map[string]map[string]bool{},
		libIfaceNames: map[string]map[string]bool{},
		libImpl:       map[string]map[string]bool{},
		cross:         map[string]map[string]bool{},
		links:         map[string]map[string]bool{},
		code:          map[posKey]*codeSite{},
		unbuiltCode:   map[posKey]string{},
		text:          map[posKey]*textSite{},
		fileCfg:       map[string]uint32{},
		generated:     map[string]bool{},
		src:           map[string][]byte{},
		relCache:      map[string]relResult{},
		toIface:       map[string]map[string]bool{},
		fromIface:     map[string]map[string]bool{},
		asserted:      map[string]map[string]bool{},
		assertGives:   map[string]map[string]bool{},
		msets:         map[string][]map[string]msel{},
		oneStepMemo:   map[string][]string{},
		st: stats{
			aliases:   map[string]bool{},
			generic:   map[string]bool{},
			kinds:     map[string]int{},
			classes:   map[string]int{},
			rels:      map[string]int{},
			external:  map[string]int{},
			paramConv: map[string]bool{},
			optional:  map[string]int{},
		},
	}
	for ci := range configs {
		if err := x.load(ci); err != nil {
			return nil, nil, err
		}
	}
	x.viaAssertions()
	if err := x.readUnbuilt(); err != nil {
		return nil, nil, err
	}
	return x.records(), &x.st, nil
}

// typeEntry is one module named type of one load, in one package variant.
type typeEntry struct {
	id      string
	named   *types.Named
	iface   *types.Interface // nil for a type that is no interface
	generic bool
	pkg     *packages.Package
	variant string          // "" for a plain package, else the test build, e.g. "p.test"
	names   map[string]bool // the method names of the method set (of *T for a type that is no interface)
}

func variantOf(p *packages.Package) string {
	if i := strings.Index(p.ID, " ["); i >= 0 && strings.HasSuffix(p.ID, "]") {
		return p.ID[i+2 : len(p.ID)-1]
	}
	return ""
}

func (x *extractor) load(ci int) error {
	goos := x.configs[ci]
	start := time.Now()
	cfg := &packages.Config{
		Mode:  loadMode,
		Dir:   x.roots[0],
		Tests: true,
		Env:   append(os.Environ(), "GOOS="+goos, "GOARCH=amd64", "GOWORK=off"),
	}
	initial, err := packages.Load(cfg, "./...")
	if err != nil {
		return fmt.Errorf("%s: load: %w", goos, err)
	}
	var all []*packages.Package
	var errs []string
	packages.Visit(initial, nil, func(p *packages.Package) {
		all = append(all, p)
		for _, e := range p.Errors {
			errs = append(errs, fmt.Sprintf("%s: %s", p.ID, e))
		}
	})
	if len(errs) > 0 {
		sort.Strings(errs)
		more := ""
		if len(errs) > 50 {
			more = fmt.Sprintf("\n... and %d more", len(errs)-50)
			errs = errs[:50]
		}
		return fmt.Errorf("%s: %d load or type errors:\n%s%s", goos, len(errs), strings.Join(errs, "\n"), more)
	}
	if len(initial) == 0 {
		return fmt.Errorf("%s: no package below %s", goos, x.roots[0])
	}
	fset := initial[0].Fset

	// The module packages: the packages of the patterns and each variant of them.
	modPaths := map[string]bool{}
	for _, p := range initial {
		modPaths[p.PkgPath] = true
	}
	if err := x.readSources(initial, fset); err != nil {
		return err
	}
	objID := map[types.Object]string{}
	var entries []*typeEntry
	variantPkgs := map[string][]*packages.Package{}
	for _, p := range all {
		if !modPaths[p.PkgPath] || p.Types == nil {
			continue
		}
		if v := variantOf(p); v != "" {
			variantPkgs[v] = append(variantPkgs[v], p)
		}
		entries = append(entries, x.declare(p, fset, objID)...)
	}
	for _, te := range entries {
		x.methods(te, objID, modPaths)
	}
	x.implements(entries, variantPkgs)
	x.crossVariant(entries)
	x.library(all, modPaths, entries)
	for _, p := range initial {
		x.sites(p, fset, ci, objID, modPaths)
	}
	if err := x.findLinks(initial, fset, objID); err != nil {
		return fmt.Errorf("%s: %w", goos, err)
	}
	x.st.loads = append(x.st.loads, fmt.Sprintf("config %s: %d packages of the patterns, %d in the graph, %.1fs",
		goos, len(initial), len(all), time.Since(start).Seconds()))
	return nil
}

// readSources reads each module file of the load one time; the columns need the bytes of
// the line.
func (x *extractor) readSources(initial []*packages.Package, fset *token.FileSet) error {
	for _, p := range initial {
		for _, f := range p.Syntax {
			abs := fset.File(f.Pos()).Name()
			rel, ok := x.relFile(abs)
			if !ok || x.src[rel] != nil {
				continue
			}
			b, err := os.ReadFile(abs)
			if err != nil {
				return err
			}
			x.src[rel] = b
		}
	}
	return nil
}

func (x *extractor) relFile(abs string) (string, bool) {
	if r, ok := x.relCache[abs]; ok {
		return r.rel, r.ok
	}
	res := relResult{}
	if abs != "" {
		for _, root := range x.roots {
			rel, err := filepath.Rel(root, abs)
			if err == nil && !filepath.IsAbs(rel) && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
				res = relResult{filepath.ToSlash(rel), true}
				break
			}
		}
	}
	x.relCache[abs] = res
	return res.rel, res.ok
}

// position gives the position of p in the tree, with the column in UTF-16 code units. ok
// is false for a position outside the tree.
func (x *extractor) position(fset *token.FileSet, p token.Pos) (Pos, bool) {
	tp := fset.PositionFor(p, false)
	rel, ok := x.relFile(tp.Filename)
	if !ok {
		return Pos{}, false
	}
	src := x.src[rel]
	if src == nil {
		panic("gokeys: no source for " + rel)
	}
	return Pos{rel, tp.Line, charCol(src, tp.Offset, tp.Column)}, true
}

func (x *extractor) addDecl(id string, d decl) {
	if _, ok := x.decls[id]; !ok {
		x.decls[id] = &d
	}
}

// declare records the package-level functions, the named types, their methods and the
// methods of the interfaces of one module package, and maps their objects to ids.
func (x *extractor) declare(p *packages.Package, fset *token.FileSet, objID map[types.Object]string) []*typeEntry {
	path := p.Types.Path()
	scope := p.Types.Scope()
	var entries []*typeEntry
	for _, n := range scope.Names() {
		obj := scope.Lookup(n)
		pos, ok := x.position(fset, obj.Pos())
		if !ok {
			continue
		}
		id := "go:" + path + "." + n
		switch o := obj.(type) {
		case *types.Func:
			objID[o] = id
			x.addDecl(id, decl{kind: "func", name: n, pos: pos})
		case *types.TypeName:
			if o.IsAlias() {
				x.st.aliases[id] = true
				continue
			}
			named, ok := o.Type().(*types.Named)
			if !ok {
				continue
			}
			objID[o] = id
			te := &typeEntry{id: id, named: named, generic: named.TypeParams().Len() > 0, pkg: p, variant: variantOf(p)}
			if te.generic {
				x.st.generic[id] = true
			}
			if it, ok := named.Underlying().(*types.Interface); ok {
				te.iface = it
				x.addDecl(id, decl{kind: "interface", name: n, pos: pos})
				for i := 0; i < it.NumExplicitMethods(); i++ {
					x.declareMethod(it.ExplicitMethod(i), id, n, "iface_method", fset, objID)
				}
			} else {
				x.addDecl(id, decl{kind: "type", name: n, pos: pos})
				for i := 0; i < named.NumMethods(); i++ {
					x.declareMethod(named.Method(i), id, n, "method", fset, objID)
				}
			}
			entries = append(entries, te)
		}
	}
	return entries
}

func (x *extractor) declareMethod(m *types.Func, typeID, typeName, kind string, fset *token.FileSet, objID map[types.Object]string) {
	if m.Name() == "_" {
		return
	}
	pos, ok := x.position(fset, m.Pos())
	if !ok {
		return
	}
	id := typeID + "." + m.Name()
	objID[m] = id
	x.addDecl(id, decl{kind: kind, name: m.Name(), container: typeName, typeID: typeID, pos: pos})
}

func addTo[V comparable](m map[string]map[V]bool, k string, v V) {
	s := m[k]
	if s == nil {
		s = map[V]bool{}
		m[k] = s
	}
	s[v] = true
}

// extMethodID names a method that is declared outside the module: <pkg path>.<Type>.<m>
// ("error.Error" for the method of the universe type error).
func extMethodID(f *types.Func) string {
	typ := "?"
	if recv := f.Type().(*types.Signature).Recv(); recv != nil {
		t := recv.Type()
		if p, ok := t.(*types.Pointer); ok {
			t = p.Elem()
		}
		if n, ok := t.(*types.Named); ok {
			typ = n.Origin().Obj().Name()
		}
	}
	if f.Pkg() == nil {
		return typ + "." + f.Name()
	}
	return f.Pkg().Path() + "." + typ + "." + f.Name()
}

// methods reads the method set of one type: each name and the method that it selects (a
// promoted method selects the method of the embedded type).
func (x *extractor) methods(te *typeEntry, objID map[types.Object]string, modPaths map[string]bool) {
	var ms *types.MethodSet
	if te.iface != nil {
		ms = types.NewMethodSet(te.named)
	} else {
		ms = types.NewMethodSet(types.NewPointer(te.named))
	}
	te.names = map[string]bool{}
	byName := x.methodOf[te.id]
	if byName == nil {
		byName = map[string]map[string]bool{}
		x.methodOf[te.id] = byName
	}
	for i := 0; i < ms.Len(); i++ {
		f, ok := ms.At(i).Obj().(*types.Func)
		if !ok {
			continue
		}
		f = f.Origin()
		te.names[f.Name()] = true
		if te.iface != nil {
			addTo(x.ifaceNames, te.id, f.Name())
		}
		id := objID[f]
		if id == "" {
			if f.Pkg() != nil && modPaths[f.Pkg().Path()] {
				continue // a module method with no record (an unnamed interface in the module)
			}
			id = extPrefix + extMethodID(f)
		}
		addTo(byName, f.Name(), id)
	}
}

func hasAll(have, want map[string]bool) bool {
	for n := range want {
		if !have[n] {
			return false
		}
	}
	return true
}

// implementsCheck reports whether u (or *u, for a type that is no interface) implements the
// interface i. An interface implements itself.
func implementsCheck(u, i *typeEntry) bool {
	if u.id == i.id {
		return true
	}
	if u.generic || i.generic {
		return false
	}
	if u.iface != nil {
		return types.Implements(u.named, i.iface)
	}
	return types.Implements(u.named, i.iface) || types.Implements(types.NewPointer(u.named), i.iface)
}

// implements fills x.rel. types.Implements compares objects of one type check, so each
// pair comes from one universe: the plain packages, or one test build (its variant packages
// and the plain packages that they import).
func (x *extractor) implements(entries []*typeEntry, variantPkgs map[string][]*packages.Package) {
	byName := nameIndex(entries)
	pairs := func(i *typeEntry, pool func(*typeEntry) bool) {
		for _, u := range rarest(byName, entries, i.names) {
			if pool(u) && hasAll(u.names, i.names) && !x.rel[u.id][i.id] && implementsCheck(u, i) {
				addTo(x.rel, u.id, i.id)
			}
		}
	}
	plain := func(u *typeEntry) bool { return u.variant == "" }
	for _, i := range entries {
		if i.iface != nil && i.variant == "" {
			pairs(i, plain)
		}
	}
	builds := make([]string, 0, len(variantPkgs))
	for b := range variantPkgs {
		builds = append(builds, b)
	}
	sort.Strings(builds)
	for _, b := range builds {
		reach := map[*packages.Package]bool{}
		var walk func(*packages.Package)
		walk = func(p *packages.Package) {
			if reach[p] {
				return
			}
			reach[p] = true
			for _, q := range p.Imports {
				walk(q)
			}
		}
		for _, p := range variantPkgs[b] {
			walk(p)
		}
		inBuild := func(u *typeEntry) bool { return u.variant == b || (u.variant == "" && reach[u.pkg]) }
		ofBuild := func(u *typeEntry) bool { return u.variant == b }
		for _, i := range entries {
			if i.iface == nil || !inBuild(i) {
				continue
			}
			if i.variant == b {
				pairs(i, inBuild)
			} else {
				pairs(i, ofBuild) // a pair of two plain types is done above
			}
		}
	}
}

// nameIndex maps each method name to the entries whose method set has it.
func nameIndex(entries []*typeEntry) map[string][]*typeEntry {
	byName := map[string][]*typeEntry{}
	for _, te := range entries {
		for n := range te.names {
			byName[n] = append(byName[n], te)
		}
	}
	return byName
}

// rarest gives the candidates for an interface with the method names names: the entries
// with its rarest name (all entries for an empty method set).
func rarest(byName map[string][]*typeEntry, all []*typeEntry, names map[string]bool) []*typeEntry {
	list := all
	first := true
	for n := range names {
		if l := byName[n]; first || len(l) < len(list) {
			list, first = l, false
		}
	}
	return list
}

// crossVariant fills x.cross: the pairs of a module type or interface u and a module
// interface i with a non-empty method set, where the method set of u (of *u for a type that
// is no interface) has each method of i with the same signature string. It compares the
// entries of any two package variants, also the pairs that no universe of implements holds
// (types.Implements finds two variants of one package type different). records() keeps the
// pairs that x.rel does not have.
func (x *extractor) crossVariant(entries []*typeEntry) {
	byName := nameIndex(entries)
	memo := map[*typeEntry]map[string]string{}
	sigs := func(te *typeEntry) map[string]string {
		s, ok := memo[te]
		if !ok {
			s = methodSigs(te)
			memo[te] = s
		}
		return s
	}
	for _, i := range entries {
		if i.iface == nil || i.generic || len(i.names) == 0 {
			continue
		}
		for _, u := range rarest(byName, entries, i.names) {
			if u.generic || u.id == i.id || x.rel[u.id][i.id] || x.cross[u.id][i.id] || !hasAll(u.names, i.names) {
				continue
			}
			us, ok := sigs(u), true
			for k, s := range sigs(i) {
				if us[k] != s {
					ok = false
					break
				}
			}
			if ok {
				addTo(x.cross, u.id, i.id)
			}
		}
	}
}

// methodSigs gives the method set of te (of *te for a type that is no interface): the key of
// each method (its name; the package path and the name for an unexported name) → the
// signature string of the method.
func methodSigs(te *typeEntry) map[string]string {
	var t types.Type = te.named
	if te.iface == nil {
		t = types.NewPointer(te.named)
	}
	ms := types.NewMethodSet(t)
	out := make(map[string]string, ms.Len())
	for k := 0; k < ms.Len(); k++ {
		sel := ms.At(k)
		key := sel.Obj().Name()
		if !token.IsExported(key) && sel.Obj().Pkg() != nil {
			key = sel.Obj().Pkg().Path() + "." + key
		}
		out[key] = sigString(sel.Type().(*types.Signature))
	}
	return out
}

// sigString writes a method signature with no receiver, no parameter names and the full
// package path of each named type, so that the two variants of one package type give the
// same string. Parameter names inside a parameter type (a func or interface type) stay.
func sigString(sig *types.Signature) string {
	unnamed := func(t *types.Tuple) *types.Tuple {
		vars := make([]*types.Var, t.Len())
		for k := range vars {
			vars[k] = types.NewParam(token.NoPos, nil, "", t.At(k).Type())
		}
		return types.NewTuple(vars...)
	}
	s := types.NewSignatureType(nil, nil, nil, unnamed(sig.Params()), unnamed(sig.Results()), sig.Variadic())
	return types.TypeString(s, (*types.Package).Path)
}

type libIface struct {
	id    string
	iface *types.Interface
	names map[string]bool
}

type libType struct {
	id    string
	named *types.Named
	names map[string]bool
}

// library fills x.libSuper and x.libImpl from the named types of the loaded packages
// outside the module (the standard library included) and the universe type error. A
// package outside the module never imports a module package, so its objects are the same
// in each universe of the load.
func (x *extractor) library(all []*packages.Package, modPaths map[string]bool, entries []*typeEntry) {
	var ifaces []*libIface
	var libTypes []*libType
	for _, p := range all {
		if modPaths[p.PkgPath] || p.Types == nil {
			continue
		}
		scope := p.Types.Scope()
		for _, n := range scope.Names() {
			tn, ok := scope.Lookup(n).(*types.TypeName)
			if !ok || tn.IsAlias() {
				continue
			}
			named, ok := tn.Type().(*types.Named)
			if !ok || named.TypeParams().Len() > 0 {
				continue
			}
			id := p.Types.Path() + "." + n
			if it, ok := named.Underlying().(*types.Interface); ok {
				if !it.IsMethodSet() || it.NumMethods() == 0 {
					continue
				}
				li := &libIface{id: id, iface: it, names: map[string]bool{}}
				for i := 0; i < it.NumMethods(); i++ {
					li.names[it.Method(i).Name()] = true
					addTo(x.libIfaceNames, id, it.Method(i).Name())
				}
				ifaces = append(ifaces, li)
				continue
			}
			ms := types.NewMethodSet(types.NewPointer(named))
			if ms.Len() == 0 {
				continue
			}
			lt := &libType{id: id, named: named, names: map[string]bool{}}
			for i := 0; i < ms.Len(); i++ {
				lt.names[ms.At(i).Obj().Name()] = true
			}
			libTypes = append(libTypes, lt)
		}
	}
	errIface := types.Universe.Lookup("error").Type().Underlying().(*types.Interface)
	ifaces = append(ifaces, &libIface{id: "error", iface: errIface, names: map[string]bool{"Error": true}})
	addTo(x.libIfaceNames, "error", "Error")

	ifByName := map[string][]*libIface{}
	for _, l := range ifaces {
		for n := range l.names {
			ifByName[n] = append(ifByName[n], l)
		}
	}
	typesByName := map[string][]*libType{}
	for _, t := range libTypes {
		for n := range t.names {
			typesByName[n] = append(typesByName[n], t)
		}
	}
	for _, u := range entries {
		if u.generic {
			continue
		}
		if u.iface == nil {
			// The library interfaces that u or *u implements.
			ptr := types.NewPointer(u.named)
			tried := map[*libIface]bool{}
			for n := range u.names {
				for _, l := range ifByName[n] {
					if tried[l] || x.libSuper[u.id][l.id] {
						continue
					}
					tried[l] = true
					if hasAll(u.names, l.names) && (types.Implements(u.named, l.iface) || types.Implements(ptr, l.iface)) {
						addTo(x.libSuper, u.id, l.id)
					}
				}
			}
			continue
		}
		if u.iface.NumExplicitMethods() == 0 {
			continue // no interface method record has this interface
		}
		// The library types that implement the interface u.
		var list []*libType
		first := true
		for n := range u.names {
			if l := typesByName[n]; first || len(l) < len(list) {
				list, first = l, false
			}
		}
		for _, t := range list {
			if x.libImpl[u.id][t.id] || !hasAll(t.names, u.names) {
				continue
			}
			if types.Implements(t.named, u.iface) || types.Implements(types.NewPointer(t.named), u.iface) {
				addTo(x.libImpl, u.id, t.id)
			}
		}
	}
}

func idOf(objID map[types.Object]string, obj types.Object) string {
	if obj == nil {
		return ""
	}
	if f, ok := obj.(*types.Func); ok {
		obj = f.Origin()
	}
	return objID[obj]
}

// embeddedTypeID gives the id of the module type that names an embedded field, or "".
func embeddedTypeID(objID map[types.Object]string, v *types.Var) string {
	t := v.Origin().Type()
	if p, ok := t.(*types.Pointer); ok {
		t = p.Elem()
	}
	if n, ok := t.(*types.Named); ok {
		return objID[n.Origin().Obj()]
	}
	return ""
}

// sites records each identifier of each module file of one package (with its roles in this
// configuration) and, one time for each file, each word in its comments and strings.
func (x *extractor) sites(p *packages.Package, fset *token.FileSet, ci int, objID map[types.Object]string, modPaths map[string]bool) {
	info := p.TypesInfo
	for _, f := range p.Syntax {
		rel, ok := x.relFile(fset.File(f.Pos()).Name())
		if !ok {
			continue
		}
		src := x.src[rel]
		x.fileCfg[rel] |= 1 << ci
		if _, done := x.generated[rel]; !done {
			x.generated[rel] = ast.IsGenerated(f)
			for _, w := range scanWords(src) {
				if w.In != "code" {
					x.text[posKey{rel, w.Line, w.Col}] = &textSite{w.Text, w.In}
				}
			}
		}
		ast.Inspect(f, func(n ast.Node) bool {
			id, ok := n.(*ast.Ident)
			if !ok || id.Name == "_" {
				return true
			}
			tp := fset.PositionFor(id.Pos(), false)
			k := posKey{rel, tp.Line, charCol(src, tp.Offset, tp.Column)}
			cs := x.code[k]
			if cs == nil {
				cs = &codeSite{name: id.Name, roles: make([][]role, len(x.configs))}
				x.code[k] = cs
			}
			cs.present |= 1 << ci
			if obj := info.Uses[id]; obj != nil {
				ext := obj.Pkg() == nil || !modPaths[obj.Pkg().Path()]
				cs.add(ci, role{id: idOf(objID, obj), ext: ext})
				// A selector or a key that names an embedded field names its type.
				if v, ok := obj.(*types.Var); ok && v.Embedded() {
					if tid := embeddedTypeID(objID, v); tid != "" {
						cs.add(ci, role{id: tid, embed: true})
					}
				}
			}
			if obj, ok := info.Defs[id]; ok {
				cs.add(ci, role{def: true, id: idOf(objID, obj)})
			}
			return true
		})
	}
}

// findLinks adds the links of one load (see linker.pair) and records the facts of case 4 (see
// x.viaAssertions). satisfy.Finder gives the conversions of a value to an interface type in
// the module files of each package (and each type assertion whose type is assignable to the
// interface); linker.asserts gives each type assertion and each case of a type switch. An id
// does not depend on the configuration, so a link of one load counts in each configuration.
// A panic of satisfy is an error.
func (x *extractor) findLinks(initial []*packages.Package, fset *token.FileSet, objID map[types.Object]string) (err error) {
	lk := &linker{x: x, fset: fset, objID: objID, seen: map[msetKey]bool{}}
	cur := ""
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("links of %s: %v", cur, r)
		}
	}()
	for _, p := range initial {
		if p.TypesInfo == nil {
			continue
		}
		var files []*ast.File
		for _, f := range p.Syntax {
			if _, ok := x.relFile(fset.File(f.Pos()).Name()); ok {
				files = append(files, f)
			}
		}
		if len(files) == 0 {
			continue
		}
		cur = p.ID
		var fd satisfy.Finder
		fd.Find(p.TypesInfo, files)
		for c := range fd.Result {
			lk.pair(c.LHS, c.RHS)
			lk.convert(c.LHS, c.RHS)
		}
		lk.asserts(p.TypesInfo, files)
	}
	return nil
}

// linker adds the links of one load to x.links, and the facts of case 4 of the load to x.
type linker struct {
	x     *extractor
	fset  *token.FileSet
	objID map[types.Object]string
	ms    typeutil.MethodSetCache
	seen  map[msetKey]bool // the method sets of the load in x.msets
}

// msel is one method of a method set for case 4: its id ("" for a method with no record) and
// its signature string (sigString).
type msel struct{ id, sig string }

// msetKey names a method set of one load: the type key, and the type name of the package
// variant (nil for a type with no name). A type of a package and of its test variant can have
// different method sets.
type msetKey struct {
	key string
	obj types.Object
}

// pair adds the links of a value of type v that goes to the interface type j: for each method
// of the method set of j, the method that the method set of v selects with its name (for a
// promoted method, the method of the embedded type), and the method of j. A link joins two
// different module declarations that have a record; a library method and a method of an
// unnamed interface have none. A pair with a type parameter on one side gives no link, and
// the statistics count it.
func (lk *linker) pair(j, v types.Type) {
	if isTypeParam(j) || isTypeParam(v) {
		lk.x.st.paramConv[lk.typeKey(j)+" = "+lk.typeKey(v)] = true
		return
	}
	jm := lk.ms.MethodSet(j)
	if jm.Len() == 0 {
		return
	}
	vm := lk.ms.MethodSet(v)
	for i := 0; i < jm.Len(); i++ {
		m := jm.At(i).Obj()
		sel := vm.Lookup(m.Pkg(), m.Name())
		if sel == nil {
			continue
		}
		a, b := idOf(lk.objID, sel.Obj()), idOf(lk.objID, m)
		if a == "" || b == "" || a == b {
			continue
		}
		if !lk.x.links[a][b] {
			lk.x.st.links++
		}
		addTo(lk.x.links, a, b)
		addTo(lk.x.links, b, a)
	}
}

// asserts adds the links of each type assertion x.(U) and of each case U of a type switch on
// x, where x has an interface type: for a concrete U the links of pair(the type of x, U), for
// an interface U the links of pair(U, the type of x), that is of each name that both have. A
// type of x with an empty method set (any) gives no link. For an interface U it also records
// the assertion for case 4 (linker.assert), and for a U that the type of x can hold the pair
// that satisfy also records as a conversion.
func (lk *linker) asserts(info *types.Info, files []*ast.File) {
	one := func(xt, u types.Type) {
		if xt == nil || u == nil || isTypeParam(xt) || !types.IsInterface(xt) {
			return
		}
		if types.IsInterface(u) && !isTypeParam(u) {
			lk.pair(u, xt)
			lk.assert(xt, u)
		} else {
			lk.pair(xt, u)
		}
		if !isTypeParam(u) && types.AssignableTo(u, xt) {
			addTo(lk.x.assertGives, lk.typeKey(xt), lk.typeKey(u))
		}
	}
	for _, f := range files {
		ast.Inspect(f, func(n ast.Node) bool {
			switch n := n.(type) {
			case *ast.TypeAssertExpr:
				if n.Type != nil { // x.(type) of a type switch has no type
					one(info.TypeOf(n.X), info.TypeOf(n.Type))
				}
			case *ast.TypeSwitchStmt:
				var a *ast.TypeAssertExpr
				switch s := n.Assign.(type) {
				case *ast.ExprStmt:
					a, _ = ast.Unparen(s.X).(*ast.TypeAssertExpr)
				case *ast.AssignStmt:
					if len(s.Rhs) == 1 {
						a, _ = ast.Unparen(s.Rhs[0]).(*ast.TypeAssertExpr)
					}
				}
				if a == nil {
					return true
				}
				xt := info.TypeOf(a.X)
				for _, cc := range n.Body.List {
					for _, e := range cc.(*ast.CaseClause).List {
						if tv, ok := info.Types[e]; ok && tv.IsType() { // not the case nil
							one(xt, tv.Type)
						}
					}
				}
			}
			return true
		})
	}
}

// convert records a conversion of a value of type v to the interface type j (a constraint of
// satisfy) for case 4: an edge of x.toIface with the method set of v, or of x.fromIface.
func (lk *linker) convert(j, v types.Type) {
	if isTypeParam(j) || isTypeParam(v) {
		return
	}
	jk, vk := lk.typeKey(j), lk.typeKey(v)
	if types.IsInterface(v) {
		addTo(lk.x.fromIface, jk, vk)
		return
	}
	addTo(lk.x.toIface, jk, vk)
	lk.methodSet(v, vk)
}

// assert records an assertion x.(u) or a type switch case u for case 4, where x has the
// interface type xt and u is an interface type. An xt with an empty method set (any) gives
// no fact: the limit of case 4.
func (lk *linker) assert(xt, u types.Type) {
	if lk.ms.MethodSet(xt).Len() == 0 {
		return
	}
	uk := lk.typeKey(u)
	addTo(lk.x.asserted, lk.typeKey(xt), uk)
	lk.methodSet(u, uk)
}

// methodSet adds the method set of t (with the type key k) to x.msets, one time for each load
// and package variant.
func (lk *linker) methodSet(t types.Type, k string) {
	u := types.Unalias(t)
	if p, ok := u.(*types.Pointer); ok {
		u = types.Unalias(p.Elem())
	}
	sk := msetKey{key: k}
	if n, ok := u.(*types.Named); ok {
		sk.obj = n.Obj()
	}
	if lk.seen[sk] {
		return
	}
	lk.seen[sk] = true
	ms := lk.ms.MethodSet(t)
	out := make(map[string]msel, ms.Len())
	for i := 0; i < ms.Len(); i++ {
		sel := ms.At(i)
		key := sel.Obj().Name()
		if !token.IsExported(key) && sel.Obj().Pkg() != nil {
			key = sel.Obj().Pkg().Path() + "." + key
		}
		out[key] = msel{idOf(lk.objID, sel.Obj()), sigString(sel.Type().(*types.Signature))}
	}
	lk.x.msets[k] = append(lk.x.msets[k], out)
}

// viaAssertions adds the links of case 4, after the last load: for each assertion x.(U) (or
// type switch case U) where x has an interface type J1 with a method, and each non-interface
// type V that a conversion gives to J1, or to an interface J0 whose values one or more
// conversions give to J1, and that implements U, the links of pair(U, V). The facts can come
// from different loads. V implements U when a method set of V has each method of a method set
// of U with the same signature string. satisfy also records an assertion x.(T) as a
// conversion of T to the type of x when the type can hold T, so the statistics count the new
// links that need such an edge (an upper bound: a conversion can give the same edge).
func (x *extractor) viaAssertions() {
	all := x.case4Pairs(nil)
	strict := x.case4Pairs(x.assertGives)
	for p := range all {
		if x.links[p[0]][p[1]] {
			continue // case 1, 2 or 3 gives this link
		}
		x.st.case4++
		x.st.links++
		if !strict[p] {
			x.st.case4Edge++
		}
	}
	for p := range all {
		addTo(x.links, p[0], p[1])
		addTo(x.links, p[1], p[0])
	}
}

// case4Pairs gives the links of case 4 as ordered id pairs, with no conversion edge in skip.
func (x *extractor) case4Pairs(skip map[string]map[string]bool) map[[2]string]bool {
	out := map[[2]string]bool{}
	for j1, us := range x.asserted {
		vs := map[string]bool{}
		seen := map[string]bool{j1: true}
		todo := []string{j1}
		for len(todo) > 0 {
			j := todo[len(todo)-1]
			todo = todo[:len(todo)-1]
			for v := range x.toIface[j] {
				if !skip[j][v] {
					vs[v] = true
				}
			}
			for j0 := range x.fromIface[j] {
				if !seen[j0] && !skip[j][j0] {
					seen[j0] = true
					todo = append(todo, j0)
				}
			}
		}
		for v := range vs {
			for u := range us {
				for _, vm := range x.msets[v] {
					for _, um := range x.msets[u] {
						if !hasMethods(vm, um) {
							continue
						}
						for k, m := range um {
							a, b := vm[k].id, m.id
							if a == "" || b == "" || a == b {
								continue
							}
							if a > b {
								a, b = b, a
							}
							out[[2]string{a, b}] = true
						}
					}
				}
			}
		}
	}
	return out
}

// hasMethods reports whether the method set v has each method of u with the same signature.
func hasMethods(v, u map[string]msel) bool {
	for k, m := range u {
		if vm, ok := v[k]; !ok || vm.sig != m.sig {
			return false
		}
	}
	return true
}

func isTypeParam(t types.Type) bool {
	_, ok := types.Unalias(t).(*types.TypeParam)
	return ok
}

// typeKey names a type in the statistics: a type parameter with the position of its
// declaration, another type with the full package paths.
func (lk *linker) typeKey(t types.Type) string {
	if tp, ok := types.Unalias(t).(*types.TypeParam); ok {
		if pos, ok := lk.x.position(lk.fset, tp.Obj().Pos()); ok {
			return fmt.Sprintf("%s@%s:%d:%d", tp.Obj().Name(), pos.File, pos.Line, pos.Col)
		}
		return tp.Obj().Name()
	}
	return types.TypeString(t, (*types.Package).Path)
}

// linkComponents numbers the components of the graph of the links: two methods get the same
// number when a chain of links joins them. A method with no link gets no number.
func (x *extractor) linkComponents() map[string]int {
	comp := map[string]int{}
	n := 0
	for id := range x.links {
		if _, done := comp[id]; done {
			continue
		}
		n++
		comp[id] = n
		todo := []string{id}
		for len(todo) > 0 {
			g := todo[len(todo)-1]
			todo = todo[:len(todo)-1]
			for h := range x.links[g] {
				if _, done := comp[h]; !done {
					comp[h] = n
					todo = append(todo, h)
				}
			}
		}
	}
	return comp
}

// coupledFamily gives the coupled family of a method or an interface method id with the
// family fam (sorted): its closure over the links (its component), cut to fam. The result
// always holds id, and it is sorted.
func coupledFamily(id string, fam []string, comp map[string]int) []string {
	c, linked := comp[id]
	out := []string{}
	for _, f := range fam {
		if cf, ok := comp[f]; f == id || linked && ok && cf == c {
			out = append(out, f)
		}
	}
	return out
}

// readUnbuilt reads each .go file of the tree (the files of gokeys idents) that no load holds,
// for example a file whose build constraints no configuration meets. Its code words go to
// x.unbuiltCode, its comment and string words to x.text.
func (x *extractor) readUnbuilt() error {
	files, err := goFiles(x.roots[0])
	if err != nil {
		return err
	}
	for _, rel := range files {
		if x.fileCfg[rel] != 0 {
			continue
		}
		src, err := os.ReadFile(filepath.Join(x.roots[0], filepath.FromSlash(rel)))
		if err != nil {
			return err
		}
		f, _ := parser.ParseFile(token.NewFileSet(), rel, src, parser.PackageClauseOnly|parser.ParseComments)
		x.generated[rel] = f != nil && ast.IsGenerated(f)
		x.st.unbuilt = append(x.st.unbuilt, rel)
		for _, w := range scanWords(src) {
			k := posKey{rel, w.Line, w.Col}
			if w.In == "code" {
				x.unbuiltCode[k] = w.Text
			} else {
				x.text[k] = &textSite{w.Text, w.In}
			}
		}
	}
	return nil
}

const (
	clForbidden = 1
	clUnproven  = 2
	clDecl      = 3
	clRequired  = 4
)

// classify gives the class of a site in one configuration and, for a use of the family,
// the use roles that resolve to family members. ext: the external list of the record is not
// empty. weak: the module methods whose use is unproven (crossVariant).
func classify(roles []role, fam map[string]bool, ext bool, weak map[string]bool) (int, []role) {
	cl := clForbidden
	var uses []role
	for _, r := range roles {
		switch {
		case r.id != "" && fam[r.id] && !r.def:
			uses = append(uses, r)
		case r.id != "" && fam[r.id]:
			cl = max(cl, clDecl)
		case !r.def && (r.ext && ext || r.id != "" && weak[r.id]):
			cl = max(cl, clUnproven)
		}
	}
	if len(uses) > 0 {
		return clRequired, uses
	}
	return cl, nil
}

func (x *extractor) configList(mask uint32) []string {
	out := []string{} // [] in the JSON for a file that no configuration builds
	for ci, c := range x.configs {
		if mask&(1<<ci) != 0 {
			out = append(out, c)
		}
	}
	return out
}

func sortedKeys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// oneStep gives the direct relatives of a method or interface method f with the name m:
// W = the module types whose method set selects f with m (the declaring type, and each type
// that gets f through an embedded field); hubs = the module interfaces with a method m that
// a type of W implements (an interface implements itself); the result is the module method
// m of each module type that implements a hub.
func (x *extractor) oneStep(id string) []string {
	if r, ok := x.oneStepMemo[id]; ok {
		return r
	}
	m := x.decls[id].name
	hubs := map[string]bool{}
	for _, w := range x.selectedBy[m][id] {
		for i := range x.rel[w] {
			if x.ifaceNames[i][m] {
				hubs[i] = true
			}
		}
	}
	out := map[string]bool{}
	for i := range hubs {
		for _, u := range x.implementersOf[i] {
			for g := range x.methodOf[u][m] {
				if !strings.HasPrefix(g, extPrefix) {
					out[g] = true
				}
			}
		}
	}
	r := sortedKeys(out)
	x.oneStepMemo[id] = r
	return r
}

// family gives the family of a record: itself for a function or a type; for a method or an
// interface method, the transitive closure of oneStep (a fixed point).
func (x *extractor) family(id string) []string {
	d := x.decls[id]
	if d.kind != "method" && d.kind != "iface_method" {
		return []string{id}
	}
	fam := map[string]bool{id: true}
	todo := []string{id}
	for len(todo) > 0 {
		g := todo[len(todo)-1]
		todo = todo[:len(todo)-1]
		for _, h := range x.oneStep(g) {
			if !fam[h] {
				fam[h] = true
				todo = append(todo, h)
			}
		}
	}
	return sortedKeys(fam)
}

// relOf gives the relation of the family member m to the record r: "self"; "super" (r is a
// method and m is a method of an interface that the receiver type of r implements); "sub"
// (r is an interface method and m is the method that a type which implements the interface
// of r has for this name); else "sibling".
func (x *extractor) relOf(r string, d *decl, m string) string {
	if m == r {
		return "self"
	}
	md := x.decls[m]
	switch d.kind {
	case "method":
		if md != nil && md.kind == "iface_method" && x.rel[d.typeID][md.typeID] {
			return "super"
		}
	case "iface_method":
		for _, u := range x.implementersOf[d.typeID] {
			if x.methodOf[u][d.name][m] {
				return "sub"
			}
		}
	}
	return "sibling"
}

var relRank = map[string]int{"self": 5, "embedded": 4, "super": 3, "sub": 2, "sibling": 1}

// coupling gives the entries of the external list of one family member.
func (x *extractor) coupling(id string) []string {
	d := x.decls[id]
	out := map[string]bool{}
	switch d.kind {
	case "method":
		for _, w := range x.selectedBy[d.name][id] {
			for l := range x.libSuper[w] {
				if x.libIfaceNames[l][d.name] {
					out["super:"+l+"."+d.name] = true
				}
			}
		}
		if magicNames[d.name] {
			out["magic:"+d.name] = true
		}
	case "iface_method":
		for t := range x.libImpl[d.typeID] {
			out["impl:"+t] = true
		}
		for _, u := range x.implementersOf[d.typeID] {
			if ud := x.decls[u]; ud == nil || ud.kind != "type" {
				continue
			}
			for g := range x.methodOf[u][d.name] {
				if strings.HasPrefix(g, extPrefix) {
					out["impl:"+strings.TrimPrefix(g, extPrefix)+" via "+u] = true
				}
			}
		}
	}
	return sortedKeys(out)
}

func (x *extractor) records() []Record {
	codeByName := map[string][]posKey{}
	for k, cs := range x.code {
		codeByName[cs.name] = append(codeByName[cs.name], k)
	}
	textByName := map[string][]posKey{}
	for k, ts := range x.text {
		textByName[ts.name] = append(textByName[ts.name], k)
	}
	unbuiltByName := map[string][]posKey{}
	for k, name := range x.unbuiltCode {
		unbuiltByName[name] = append(unbuiltByName[name], k)
	}
	x.selectedBy = map[string]map[string][]string{}
	for u, byName := range x.methodOf {
		for m, ids := range byName {
			for id := range ids {
				if strings.HasPrefix(id, extPrefix) {
					continue
				}
				if x.selectedBy[m] == nil {
					x.selectedBy[m] = map[string][]string{}
				}
				x.selectedBy[m][id] = append(x.selectedBy[m][id], u)
			}
		}
	}
	x.implementersOf = map[string][]string{}
	for u, is := range x.rel {
		for i := range is {
			x.implementersOf[i] = append(x.implementersOf[i], u)
		}
	}
	for _, us := range x.implementersOf {
		sort.Strings(us)
	}
	// The pairs of crossVariant that the normal rule does not give; they do not change the
	// families.
	crossOf := map[string][]string{} // interface id → type ids
	for u, is := range x.cross {
		for i := range is {
			if !x.rel[u][i] {
				crossOf[i] = append(crossOf[i], u)
			}
		}
	}
	couplingMemo := map[string][]string{}
	comp := x.linkComponents()

	ids := make([]string, 0, len(x.decls))
	for id := range x.decls {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	recs := make([]Record, 0, len(ids))
	for _, id := range ids {
		d := x.decls[id]
		fam := x.family(id)
		famSet := map[string]bool{}
		relFor := map[string]string{}
		for _, f := range fam {
			famSet[f] = true
			relFor[f] = x.relOf(id, d, f)
		}
		external := []string{}
		if d.kind == "method" || d.kind == "iface_method" {
			ext := map[string]bool{}
			for _, f := range fam {
				c, ok := couplingMemo[f]
				if !ok {
					c = x.coupling(f)
					couplingMemo[f] = c
				}
				for _, e := range c {
					ext[e] = true
				}
			}
			external = sortedKeys(ext)
		}
		hasExt := len(external) > 0
		// The coupled family of a method or an interface method. A use whose family members
		// are all outside it is optional. For a function or a type it is the family.
		var coupled []string
		inCoupled := famSet
		if d.kind == "method" || d.kind == "iface_method" {
			coupled = coupledFamily(id, fam, comp)
			inCoupled = map[string]bool{}
			for _, c := range coupled {
				inCoupled[c] = true
			}
			if len(coupled) < len(fam) {
				x.st.narrow++
			}
		}
		// weak: the methods with this name of the interfaces that a type which selects this
		// method satisfies only across package variants. A use of one is unproven.
		weak := map[string]bool{}
		if d.kind == "method" || d.kind == "iface_method" {
			for _, w := range x.selectedBy[d.name][id] {
				for i := range x.cross[w] {
					if x.rel[w][i] {
						continue
					}
					for g := range x.methodOf[i][d.name] {
						if !strings.HasPrefix(g, extPrefix) {
							weak[g] = true
						}
					}
				}
			}
		}

		sites := []Site{}
		for _, k := range codeByName[d.name] {
			cs := x.code[k]
			best := 0
			var cfgs []string
			var members []role
			for ci, c := range x.configs {
				if cs.present&(1<<ci) == 0 {
					continue
				}
				cl, uses := classify(cs.roles[ci], famSet, hasExt, weak)
				if cl > best {
					best, cfgs, members = cl, nil, nil
				}
				if cl == best {
					cfgs = append(cfgs, c)
					members = append(members, uses...)
				}
			}
			s := Site{File: k.file, Line: k.line, Col: k.col, Class: "forbidden", Why: "decoy", Configs: cfgs}
			switch best {
			case clRequired:
				s.Class, s.Why = "required", "use"
				some, all := false, true
				for _, m := range members {
					r := relFor[m.id]
					if m.embed {
						r = "embedded"
					}
					if relRank[r] > relRank[s.Rel] {
						s.Rel = r
					}
					if inCoupled[m.id] {
						some = true
					} else {
						all = false
					}
				}
				if !some {
					s.Class, s.Optional = "dnc", true // the why stays "use", the rel stays
				} else if !all {
					x.st.mixed++
				}
			case clDecl:
				s.Class, s.Why = "dnc", "decl"
			case clUnproven:
				s.Class, s.Why = "dnc", "unproven"
			}
			if x.generated[k.file] && best != clDecl {
				s.Class, s.Why = "dnc", "generated" // a use keeps its rel
			}
			sites = append(sites, s)
		}
		for _, k := range textByName[d.name] {
			why := x.text[k].in
			if x.generated[k.file] {
				why = "generated"
			}
			sites = append(sites, Site{File: k.file, Line: k.line, Col: k.col, Class: "dnc", Why: why, Configs: x.configList(x.fileCfg[k.file])})
		}
		for _, k := range unbuiltByName[d.name] {
			sites = append(sites, Site{File: k.file, Line: k.line, Col: k.col, Class: "dnc", Why: "unproven", Configs: []string{}})
		}
		sort.Slice(sites, func(a, b int) bool {
			sa, sb := sites[a], sites[b]
			if sa.File != sb.File {
				return sa.File < sb.File
			}
			if sa.Line != sb.Line {
				return sa.Line < sb.Line
			}
			return sa.Col < sb.Col
		})
		for _, s := range sites {
			x.st.classes[s.Class+"/"+s.Why]++
			if s.Class == "required" {
				x.st.rels[s.Rel]++
			}
			if s.Optional {
				x.st.optional[s.Rel]++
			}
			if len(s.Configs) == 0 {
				x.st.noConfig++
			}
		}
		// The types that implement an interface record; and, as dnc, the other module
		// interfaces whose method set satisfies it (not for an empty method set, which each
		// interface satisfies) and the types and interfaces that satisfy it only across
		// package variants.
		impls := []Implementer{}
		if d.kind == "interface" {
			dnc := 0
			for _, u := range x.implementersOf[id] {
				ud := x.decls[u]
				switch {
				case ud == nil:
				case ud.kind == "type":
					impls = append(impls, Implementer{u, ud.pos.File, ud.pos.Line, ud.pos.Col, "required"})
				case ud.kind == "interface" && u != id && len(x.ifaceNames[id]) > 0:
					impls = append(impls, Implementer{u, ud.pos.File, ud.pos.Line, ud.pos.Col, "dnc"})
					dnc++
				}
			}
			for _, u := range crossOf[id] {
				ud := x.decls[u]
				impls = append(impls, Implementer{u, ud.pos.File, ud.pos.Line, ud.pos.Col, "dnc"})
				dnc++
				x.st.crossImp++
			}
			sort.Slice(impls, func(a, b int) bool { return impls[a].ID < impls[b].ID })
			x.st.dncImpls += dnc
			if dnc > 0 {
				x.st.dncIface++
			}
		}
		x.st.kinds[d.kind]++
		if hasExt {
			x.st.external[d.kind]++
		}
		recs = append(recs, Record{
			ID: id, Lang: "go", Kind: d.kind, Name: d.name, Container: d.container, Decl: d.pos,
			Family: fam, Coupled: coupled, Sites: sites, Implementers: impls, External: external, Source: "go/types",
		})
	}
	return recs
}
