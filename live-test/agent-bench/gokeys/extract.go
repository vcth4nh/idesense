package main

import (
	"fmt"
	"go/ast"
	"go/token"
	"go/types"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"golang.org/x/tools/go/packages"
)

// Record is one key record (the key model of Task 1, plus `external`). Each position is
// 1-based; the column counts UTF-16 code units.
type Record struct {
	ID           string        `json:"id"`
	Lang         string        `json:"lang"`
	Kind         string        `json:"kind"`
	Name         string        `json:"name"`
	Container    string        `json:"container"`
	Decl         Pos           `json:"decl"`
	Family       []string      `json:"family"`
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
// family member: "self", "super", "sub" or "sibling".
type Site struct {
	File    string   `json:"file"`
	Line    int      `json:"line"`
	Col     int      `json:"col"`
	Class   string   `json:"class"`
	Why     string   `json:"why"`
	Configs []string `json:"configs"`
	Rel     string   `json:"rel,omitempty"`
}

type Implementer struct {
	ID   string `json:"id"`
	File string `json:"file"`
	Line int    `json:"line"`
	Col  int    `json:"col"`
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
// true for a use of an object that is declared outside the module.
type role struct {
	def bool
	ext bool
	id  string
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
	code          map[posKey]*codeSite
	text          map[posKey]*textSite
	fileCfg       map[string]uint32 // file → configurations whose build has it
	generated     map[string]bool   // file → it has a "Code generated" header
	src           map[string][]byte // file → content
	relCache      map[string]relResult

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
}

func (s *stats) print(w io.Writer, total time.Duration) {
	for _, l := range s.loads {
		fmt.Fprintln(w, l)
	}
	fmt.Fprintf(w, "records: %s\n", countLine(s.kinds))
	fmt.Fprintf(w, "sites: %s\n", countLine(s.classes))
	fmt.Fprintf(w, "required sites by rel: %s\n", countLine(s.rels))
	fmt.Fprintf(w, "records with external entries: %s\n", countLine(s.external))
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
		code:          map[posKey]*codeSite{},
		text:          map[posKey]*textSite{},
		fileCfg:       map[string]uint32{},
		generated:     map[string]bool{},
		src:           map[string][]byte{},
		relCache:      map[string]relResult{},
		oneStepMemo:   map[string][]string{},
		st: stats{
			aliases:  map[string]bool{},
			generic:  map[string]bool{},
			kinds:    map[string]int{},
			classes:  map[string]int{},
			rels:     map[string]int{},
			external: map[string]int{},
		},
	}
	for ci := range configs {
		if err := x.load(ci); err != nil {
			return nil, nil, err
		}
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
	x.library(all, modPaths, entries)
	for _, p := range initial {
		x.sites(p, fset, ci, objID, modPaths)
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
	byName := map[string][]*typeEntry{}
	for _, te := range entries {
		for n := range te.names {
			byName[n] = append(byName[n], te)
		}
	}
	pairs := func(i *typeEntry, pool func(*typeEntry) bool) {
		list := entries
		first := true
		for n := range i.names {
			if l := byName[n]; first || len(l) < len(list) {
				list, first = l, false
			}
		}
		for _, u := range list {
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
						cs.add(ci, role{id: tid})
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

const (
	clForbidden = 1
	clUnproven  = 2
	clDecl      = 3
	clRequired  = 4
)

// classify gives the class of a site in one configuration and, for a use of the family,
// the family members that it resolves to. coupled: the external list of the record is not
// empty.
func classify(roles []role, fam map[string]bool, coupled bool) (int, []string) {
	cl := clForbidden
	var uses []string
	for _, r := range roles {
		switch {
		case r.id != "" && fam[r.id] && !r.def:
			uses = append(uses, r.id)
		case r.id != "" && fam[r.id]:
			cl = max(cl, clDecl)
		case !r.def && r.ext && coupled:
			cl = max(cl, clUnproven)
		}
	}
	if len(uses) > 0 {
		return clRequired, uses
	}
	return cl, nil
}

func (x *extractor) configList(mask uint32) []string {
	var out []string
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

var relRank = map[string]int{"self": 4, "super": 3, "sub": 2, "sibling": 1}

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
	couplingMemo := map[string][]string{}

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
		coupled := len(external) > 0

		sites := []Site{}
		for _, k := range codeByName[d.name] {
			cs := x.code[k]
			best := 0
			var cfgs []string
			var members []string
			for ci, c := range x.configs {
				if cs.present&(1<<ci) == 0 {
					continue
				}
				cl, uses := classify(cs.roles[ci], famSet, coupled)
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
				for _, m := range members {
					if relRank[relFor[m]] > relRank[s.Rel] {
						s.Rel = relFor[m]
					}
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
		}
		impls := []Implementer{}
		if d.kind == "interface" {
			for _, u := range x.implementersOf[id] {
				if ud := x.decls[u]; ud != nil && ud.kind == "type" {
					impls = append(impls, Implementer{u, ud.pos.File, ud.pos.Line, ud.pos.Col})
				}
			}
		}
		x.st.kinds[d.kind]++
		if coupled {
			x.st.external[d.kind]++
		}
		recs = append(recs, Record{
			ID: id, Lang: "go", Kind: d.kind, Name: d.name, Container: d.container, Decl: d.pos,
			Family: fam, Sites: sites, Implementers: impls, External: external, Source: "go/types",
		})
	}
	return recs
}
