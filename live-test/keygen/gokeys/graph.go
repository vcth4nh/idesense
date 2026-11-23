package main

import (
	"cmp"
	"errors"
	"flag"
	"fmt"
	"go/ast"
	"go/token"
	"go/types"
	"io"
	"slices"
	"strings"
	"time"

	"golang.org/x/tools/go/packages"
	"golang.org/x/tools/go/types/typeutil"
)

// GraphFunc is one function declaration (*ast.FuncDecl) of a module file of one build, with its
// calls sorted by position. ID, Kind, Name, Container, Decl and End are those of gokeys calls.
type GraphFunc struct {
	Rec       string      `json:"rec"` // "func"
	ID        string      `json:"id"`
	Kind      string      `json:"kind"`
	Name      string      `json:"name"`
	Container string      `json:"container"`
	Decl      Pos         `json:"decl"`
	End       int         `json:"end"`
	Calls     []GraphCall `json:"calls"`
}

// GraphCall is one entry of a call, at the identifier of the called function (callOperand), or
// at the left parenthesis when no identifier names it (grapher.callEntries). A call in a
// function literal belongs to the function declaration that holds the literal, with Lit true.
// Kind "direct": a call of a function of the graph; "embedded": such a call through an embedded
// field; "iface": a call of a method of a module interface, one entry for each callee
// (grapher.ifaceEntries); "other": a call that gives no step, with Callee nil. Iface is the id of
// the interface method of an "iface" entry, "" for a method of an unnamed interface.
type GraphCall struct {
	Line   int    `json:"line"`
	Col    int    `json:"col"`
	Callee *Pos   `json:"callee"`
	Kind   string `json:"kind"`
	Lit    bool   `json:"lit"`
	Iface  string `json:"iface"`
}

// GraphIface is one named, non-generic module interface of the build, with its explicit methods
// sorted by id.
type GraphIface struct {
	Rec     string        `json:"rec"` // "iface"
	ID      string        `json:"id"`
	Name    string        `json:"name"`
	Decl    Pos           `json:"decl"`
	Methods []GraphMethod `json:"methods"`
}

// GraphMethod is one explicit method of an interface, with its implementers sorted by type id.
type GraphMethod struct {
	ID    string      `json:"id"`
	Name  string      `json:"name"`
	Decl  Pos         `json:"decl"`
	Impls []GraphImpl `json:"impls"`
}

// GraphImpl is one implementer of an interface (grapher.implementers, implType) with the method
// that the method set of *T selects for the name. Method is nil when the module declares no
// function for it (a method of an embedded interface or of an embedded library type). Own is
// true when T declares the method itself.
type GraphImpl struct {
	Type     string `json:"type"`
	TypeDecl Pos    `json:"type_decl"`
	Method   *Pos   `json:"method"`
	Own      bool   `json:"own"`
}

// graphCheck is the result of the SSA check of the graph.
type graphCheck struct{}

type graphStats struct {
	load         string
	funcs, noID  int
	kinds        map[string]int // the call entries by kind
	ifaces       int
	generic      int            // the generic types that are no interface
	genericNames int            // of these, the types with each method name of a module interface
	types        map[string]int // the implementer types by kind (implType)
	implementing map[string]int // of these, the types that implement a module interface with a method
	typeParam    int            // the calls of a method of a module interface through a type that mentions a type parameter
	ifaceExpr    int            // the method expressions of an interface type (I.M(v)) with the kind iface
}

func (s *graphStats) print(w io.Writer, total time.Duration) {
	fmt.Fprintln(w, s.load)
	fmt.Fprintf(w, "functions: %d, with id \"\" %d\n", s.funcs, s.noID)
	fmt.Fprintf(w, "calls: %s\n", countLine(s.kinds))
	fmt.Fprintf(w, "interfaces: %d\n", s.ifaces)
	fmt.Fprintf(w, "generic types (no implementer): %d, %d with each method name of a module interface\n", s.generic, s.genericNames)
	fmt.Fprintf(w, "named types of a function body: %d, %d implement a module interface\n", s.types["local"], s.implementing["local"])
	fmt.Fprintf(w, "unnamed struct types with an embedded field: %d, %d implement a module interface\n", s.types["struct"], s.implementing["struct"])
	fmt.Fprintf(w, "calls through a type that mentions a type parameter (kind other): %d\n", s.typeParam)
	fmt.Fprintf(w, "method expressions of an interface type (I.M(v), kind iface): %d\n", s.ifaceExpr)
	fmt.Fprintf(w, "time: %.1fs\n", total.Seconds())
}

// cmdGraph: gokeys graph. It writes first each function, then each interface. Exit code 1 for
// an error.
func cmdGraph(args []string, stdout, stderr io.Writer) int {
	fl := flag.NewFlagSet("graph", flag.ContinueOnError)
	fl.SetOutput(stderr)
	tree := fl.String("tree", "", "root folder of the module")
	goos := fl.String("goos", "", "the GOOS of the build; GOARCH is amd64")
	out := fl.String("out", "", "output JSONL file")
	check := fl.Bool("check", false, "compare the calls with the SSA form of the build")
	if err := fl.Parse(args); err != nil {
		return 2
	}
	if *tree == "" || *goos == "" || *out == "" || fl.NArg() != 0 {
		fmt.Fprintln(stderr, usage)
		return 2
	}
	start := time.Now()
	funcs, ifaces, st, _, err := extractGraph(*tree, *goos, *check)
	if err != nil {
		fmt.Fprintln(stderr, "gokeys graph:", err)
		return 1
	}
	recs := make([]any, 0, len(funcs)+len(ifaces))
	for _, f := range funcs {
		recs = append(recs, f)
	}
	for _, i := range ifaces {
		recs = append(recs, i)
	}
	if err := writeJSONL(*out, recs); err != nil {
		fmt.Fprintln(stderr, "gokeys graph:", err)
		return 1
	}
	st.print(stdout, time.Since(start))
	return 0
}

// extractGraph loads the module at tree one time for the build goos (GOARCH amd64, no test
// file) and gives each function of the build with its calls, sorted by decl, and each named,
// non-generic module interface with its implementers, sorted by id.
func extractGraph(tree, goos string, check bool) ([]GraphFunc, []GraphIface, *graphStats, *graphCheck, error) {
	if check {
		return nil, nil, nil, nil, errors.New("-check is not implemented")
	}
	start := time.Now()
	x, err := newExtractor(tree, []string{goos})
	if err != nil {
		return nil, nil, nil, nil, err
	}
	initial, all, fset, modPaths, err := x.loadPackages(0, false)
	if err != nil {
		return nil, nil, nil, nil, err
	}
	if err := x.readSources(initial, fset); err != nil {
		return nil, nil, nil, nil, err
	}
	objID, entries := x.declareAll(all, fset, modPaths)
	g := &grapher{x: x, fset: fset, objID: objID, modPaths: modPaths, funcs: map[Pos]*GraphFunc{},
		impls: map[*types.Interface][]*implType{},
		st: &graphStats{kinds: map[string]int{"direct": 0, "embedded": 0, "iface": 0, "other": 0},
			types: map[string]int{}, implementing: map[string]int{}}}
	var generics []*types.Named
	for _, te := range entries {
		switch {
		case te.iface != nil: // an interface is no implementer
		case te.generic:
			generics = append(generics, te.named)
		default:
			g.concrete = append(g.concrete, newImplType(te.id, x.decls[te.id].pos, te.named, "package"))
		}
	}
	for _, p := range initial {
		impls, gen := g.localTypes(p)
		g.concrete = append(g.concrete, impls...)
		generics = append(generics, gen...)
	}
	g.concrete = append(g.concrete, g.structTypes(initial)...)
	for _, p := range initial {
		x.funcDecls(p, fset, objID, func(fd *ast.FuncDecl, obj *types.Func, pos Pos) {
			r := x.callRecord(fd, obj, pos, fset, objID)
			g.funcs[pos] = &GraphFunc{Rec: "func", ID: r.ID, Kind: r.Kind, Name: r.Name, Container: r.Container,
				Decl: r.Decl, End: r.End, Calls: []GraphCall{}}
		})
	}
	for _, p := range initial {
		g.calls(p)
	}
	funcs := make([]GraphFunc, 0, len(g.funcs))
	for _, f := range g.funcs {
		slices.SortFunc(f.Calls, cmpGraphCall)
		funcs = append(funcs, *f)
		if f.ID == "" {
			g.st.noID++
		}
		for _, c := range f.Calls {
			g.st.kinds[c.Kind]++
		}
	}
	slices.SortFunc(funcs, func(a, b GraphFunc) int { return cmpPos(a.Decl, b.Decl) })
	g.st.funcs = len(funcs)
	ifaces := g.ifaceTable(entries)
	g.st.ifaces = len(ifaces)
	for _, te := range g.concrete {
		g.st.types[te.kind]++
		if te.implementing {
			g.st.implementing[te.kind]++
		}
	}
	g.genericStats(generics, entries)
	g.st.load = loadLine(goos, len(initial), len(all), time.Since(start))
	return funcs, ifaces, g.st, nil, nil
}

// grapher holds the facts of one load for the graph.
type grapher struct {
	x        *extractor
	fset     *token.FileSet
	objID    map[types.Object]string
	modPaths map[string]bool
	funcs    map[Pos]*GraphFunc               // decl → the function of the graph
	concrete []*implType                      // the types that can implement an interface
	impls    map[*types.Interface][]*implType // interface → its implementers
	st       *graphStats
}

// implType is one type that can implement a module interface, with the method set of *T. Kind
// "package": a package-level named type, with the id of extract. Kind "local": a named type of
// a function body (grapher.localTypes). Kind "struct": an unnamed struct type with an embedded
// field (grapher.structTypes). No implType is an interface or a generic type.
type implType struct {
	id           string
	decl         Pos
	typ          types.Type // *types.Named, or *types.Struct for the kind "struct"
	mset         *types.MethodSet
	kind         string
	implementing bool // it implements a module interface with a method (grapher.implementers)
}

func newImplType(id string, decl Pos, t types.Type, kind string) *implType {
	return &implType{id: id, decl: decl, typ: t, mset: types.NewMethodSet(types.NewPointer(t)), kind: kind}
}

// localTypes gives each named type that a function body of the package p declares and that is
// no interface: the types that are not generic, with the id
// go:<package path>.<name>@<file>:<line>:<col> of the position of the name, and the generic types.
func (g *grapher) localTypes(p *packages.Package) (impls []*implType, generics []*types.Named) {
	for id, obj := range p.TypesInfo.Defs {
		tn, ok := obj.(*types.TypeName)
		if !ok || tn.IsAlias() || tn.Parent() == p.Types.Scope() {
			continue
		}
		named, ok := tn.Type().(*types.Named)
		if !ok || types.IsInterface(named) {
			continue // a type parameter, an interface
		}
		if named.TypeParams().Len() > 0 {
			generics = append(generics, named)
			continue
		}
		if pos, ok := g.x.treePos(g.fset, id.Pos()); ok {
			typeID := fmt.Sprintf("go:%s.%s@%s:%d:%d", p.Types.Path(), tn.Name(), pos.File, pos.Line, pos.Col)
			impls = append(impls, newImplType(typeID, pos, named, "local"))
		}
	}
	return impls, generics
}

// structTypes gives each unnamed struct type with an embedded field that is the type, or the
// element type of the pointer type, of a value expression or of a declared variable of the
// packages, one time for identical types. The id is struct@<file>:<line>:<col> of the first
// occurrence in file order; a second type with the first occurrence at the same position (an
// expression that starts with another one) gets #2, and so on.
func (g *grapher) structTypes(pkgs []*packages.Package) []*implType {
	type occurrence struct {
		pos Pos
		end token.Pos
		st  *types.Struct
	}
	var occs []occurrence
	add := func(n ast.Node, t types.Type) {
		t = types.Unalias(t)
		if p, ok := t.(*types.Pointer); ok {
			t = types.Unalias(p.Elem())
		}
		st, ok := t.(*types.Struct)
		if !ok {
			return
		}
		for i := 0; i < st.NumFields(); i++ {
			if st.Field(i).Embedded() {
				if pos, ok := g.x.treePos(g.fset, n.Pos()); ok {
					occs = append(occs, occurrence{pos, n.End(), st})
				}
				return
			}
		}
	}
	for _, p := range pkgs {
		for e, tv := range p.TypesInfo.Types {
			if tv.IsValue() {
				add(e, tv.Type)
			}
		}
		for id, obj := range p.TypesInfo.Defs {
			if v, ok := obj.(*types.Var); ok {
				add(id, v.Type())
			}
		}
	}
	slices.SortFunc(occs, func(a, b occurrence) int {
		if c := cmpPos(a.pos, b.pos); c != 0 {
			return c
		}
		if c := cmp.Compare(a.end, b.end); c != 0 {
			return c
		}
		return strings.Compare(a.st.String(), b.st.String())
	})
	var seen typeutil.Map
	used := map[string]int{}
	var out []*implType
	for _, o := range occs {
		if seen.At(o.st) != nil {
			continue
		}
		seen.Set(o.st, true)
		id := fmt.Sprintf("struct@%s:%d:%d", o.pos.File, o.pos.Line, o.pos.Col)
		used[id]++
		if n := used[id]; n > 1 {
			id += fmt.Sprintf("#%d", n)
		}
		out = append(out, newImplType(id, o.pos, o.st, "struct"))
	}
	return out
}

// calls adds the call entries of each function declaration of the module files of the package
// p. A call outside each function declaration gives nothing.
func (g *grapher) calls(p *packages.Package) {
	info := p.TypesInfo
	for _, f := range p.Syntax {
		if _, ok := g.x.relFile(g.fset.File(f.Pos()).Name()); !ok {
			continue
		}
		for _, d := range f.Decls {
			fd, ok := d.(*ast.FuncDecl)
			if !ok {
				continue
			}
			pos, ok := g.x.treePos(g.fset, fd.Name.Pos())
			gf := g.funcs[pos]
			if !ok || gf == nil {
				continue
			}
			ast.PreorderStack(fd, nil, func(n ast.Node, stack []ast.Node) bool {
				if call, ok := n.(*ast.CallExpr); ok {
					lit := slices.ContainsFunc(stack, func(a ast.Node) bool { _, ok := a.(*ast.FuncLit); return ok })
					gf.Calls = append(gf.Calls, g.callEntries(info, call, lit)...)
				}
				return true
			})
		}
	}
}

// callEntries gives the entries of the call expression call. When an identifier names the
// called function (callOperand: an identifier or a selector), the entries are at the
// identifier. Else a call that is no conversion (getF()(), x.(func())(), a call of a function
// literal) gives one entry other at its left parenthesis.
func (g *grapher) callEntries(info *types.Info, call *ast.CallExpr, lit bool) []GraphCall {
	var id *ast.Ident
	var sel *types.Selection // nil for no selector and for a qualified identifier
	switch e := callOperand(call).(type) {
	case *ast.Ident:
		id = e
	case *ast.SelectorExpr:
		id, sel = e.Sel, info.Selections[e]
	default:
		if info.Types[call.Fun].IsType() {
			return nil // a conversion
		}
		pos, ok := g.x.treePos(g.fset, call.Lparen)
		if !ok {
			return nil
		}
		return []GraphCall{{Line: pos.Line, Col: pos.Col, Kind: "other", Lit: lit}}
	}
	pos, ok := g.x.treePos(g.fset, id.Pos())
	if !ok {
		return nil
	}
	c := GraphCall{Line: pos.Line, Col: pos.Col, Kind: "other", Lit: lit}
	switch o := info.Uses[id].(type) {
	case *types.TypeName, *types.Builtin:
		return nil // a conversion, a builtin call
	case *types.Func:
		if recv := o.Signature().Recv(); recv != nil && types.IsInterface(recv.Type()) {
			return g.ifaceEntries(o, sel, c)
		}
		if decl, ok := g.funcDecl(o); ok {
			c.Callee, c.Kind = &decl, "direct"
			if sel != nil && len(sel.Index()) > 1 {
				c.Kind = "embedded"
			}
			return []GraphCall{c}
		}
		if !g.module(o) {
			return nil // a static call of a library function or method
		}
	}
	return []GraphCall{c} // a call of a function value
}

// ifaceEntries gives the entries of a call of the interface method m. A method of a library
// interface gives one entry other. So does a call whose dispatch type (dispatchType) mentions a
// type parameter: a type parameter, Getter[T], interface{ Get() T }. Else the call has one entry
// for each function of the graph that an implementer of the dispatch type selects for the name,
// and no entry when it has no such function.
func (g *grapher) ifaceEntries(m *types.Func, sel *types.Selection, c GraphCall) []GraphCall {
	if !g.module(m) {
		return []GraphCall{c}
	}
	d := dispatchType(sel)
	if hasTypeParam(d) || hasTypeParam(d.Underlying()) {
		g.st.typeParam++
		return []GraphCall{c}
	}
	c.Kind, c.Iface = "iface", idOf(g.objID, m)
	seen := map[Pos]bool{}
	var out []GraphCall
	for _, te := range g.implementers(d.Underlying().(*types.Interface)) {
		decl, _, ok := g.selected(te, m)
		if ok && !seen[decl] {
			seen[decl] = true
			e := c
			e.Callee = &decl
			out = append(out, e)
		}
	}
	if len(out) > 0 && sel.Kind() == types.MethodExpr {
		g.st.ifaceExpr++
	}
	return out
}

// dispatchType gives the type of the value that a call of the selection sel dispatches on: the
// receiver when it is an interface or a type parameter, else the type of the last embedded field
// on the path to the method. Its underlying type is an interface.
func dispatchType(sel *types.Selection) types.Type {
	t := sel.Recv()
	if types.IsInterface(t) {
		return t
	}
	path := sel.Index()
	for _, i := range path[:len(path)-1] {
		if p, ok := t.Underlying().(*types.Pointer); ok {
			t = p.Elem()
		}
		t = t.Underlying().(*types.Struct).Field(i).Type()
	}
	return t
}

// hasTypeParam reports whether t mentions a type parameter. A named type counts by its type
// arguments, a signature by its parameters and results, an interface by its methods.
func hasTypeParam(t types.Type) bool {
	switch t := t.(type) {
	case *types.TypeParam:
		return true
	case *types.Alias:
		return hasTypeParam(types.Unalias(t))
	case *types.Named:
		for i := 0; i < t.TypeArgs().Len(); i++ {
			if hasTypeParam(t.TypeArgs().At(i)) {
				return true
			}
		}
	case *types.Pointer:
		return hasTypeParam(t.Elem())
	case *types.Slice:
		return hasTypeParam(t.Elem())
	case *types.Array:
		return hasTypeParam(t.Elem())
	case *types.Chan:
		return hasTypeParam(t.Elem())
	case *types.Map:
		return hasTypeParam(t.Key()) || hasTypeParam(t.Elem())
	case *types.Tuple:
		for i := 0; i < t.Len(); i++ {
			if hasTypeParam(t.At(i).Type()) {
				return true
			}
		}
	case *types.Signature:
		return hasTypeParam(t.Params()) || hasTypeParam(t.Results())
	case *types.Struct:
		for i := 0; i < t.NumFields(); i++ {
			if hasTypeParam(t.Field(i).Type()) {
				return true
			}
		}
	case *types.Interface:
		for i := 0; i < t.NumMethods(); i++ {
			if hasTypeParam(t.Method(i).Type()) {
				return true
			}
		}
	}
	return false
}

// implementers gives the types of g.concrete where T or *T implements iface. It marks them as
// implementing when iface has a method.
func (g *grapher) implementers(iface *types.Interface) []*implType {
	if l, ok := g.impls[iface]; ok {
		return l
	}
	var l []*implType
	for _, te := range g.concrete {
		if types.Implements(te.typ, iface) || types.Implements(types.NewPointer(te.typ), iface) {
			l = append(l, te)
			te.implementing = te.implementing || iface.NumMethods() > 0
		}
	}
	g.impls[iface] = l
	return l
}

// selected gives the decl of the method that the method set of *T selects for the name of the
// interface method m, whether T declares it itself, and whether it is a function of the graph.
func (g *grapher) selected(te *implType, m *types.Func) (decl Pos, own, ok bool) {
	s := te.mset.Lookup(m.Pkg(), m.Name())
	decl, ok = g.funcDecl(s.Obj().(*types.Func))
	return decl, len(s.Index()) == 1, ok
}

// funcDecl gives the decl of the origin of f, and whether it is a function of the graph.
func (g *grapher) funcDecl(f *types.Func) (Pos, bool) {
	pos, ok := g.x.treePos(g.fset, f.Origin().Pos())
	return pos, ok && g.funcs[pos] != nil
}

func (g *grapher) module(obj types.Object) bool {
	return obj.Pkg() != nil && g.modPaths[obj.Pkg().Path()]
}

// ifaceTable gives each named, non-generic module interface with each explicit method that a
// module file declares, and its implementers.
func (g *grapher) ifaceTable(entries []*typeEntry) []GraphIface {
	out := []GraphIface{}
	for _, te := range entries {
		if te.iface == nil || te.generic {
			continue
		}
		gi := GraphIface{Rec: "iface", ID: te.id, Name: te.named.Obj().Name(), Decl: g.x.decls[te.id].pos, Methods: []GraphMethod{}}
		impls := g.implementers(te.iface)
		for i := 0; i < te.iface.NumExplicitMethods(); i++ {
			m := te.iface.ExplicitMethod(i)
			mpos, ok := g.x.treePos(g.fset, m.Pos())
			if !ok {
				continue // a method of a library interface (type I io.Writer)
			}
			gm := GraphMethod{ID: idOf(g.objID, m), Name: m.Name(), Decl: mpos, Impls: []GraphImpl{}}
			for _, u := range impls {
				decl, own, ok := g.selected(u, m)
				im := GraphImpl{Type: u.id, TypeDecl: u.decl, Own: own}
				if ok {
					im.Method = &decl
				}
				gm.Impls = append(gm.Impls, im)
			}
			slices.SortFunc(gm.Impls, func(a, b GraphImpl) int { return strings.Compare(a.Type, b.Type) })
			gi.Methods = append(gi.Methods, gm)
		}
		slices.SortFunc(gi.Methods, func(a, b GraphMethod) int { return strings.Compare(a.ID, b.ID) })
		out = append(out, gi)
	}
	slices.SortFunc(out, func(a, b GraphIface) int { return strings.Compare(a.ID, b.ID) })
	return out
}

// genericStats counts the generic types that are no interface (of the package level and of a
// function body), and of these the types whose method set (of *T) has each method name of a
// named, non-generic module interface with a method. The behavior of types.Implements is
// unspecified for an uninstantiated generic type, so a generic type is no implementer.
func (g *grapher) genericStats(generics []*types.Named, entries []*typeEntry) {
	for _, named := range generics {
		g.st.generic++
		ms := types.NewMethodSet(types.NewPointer(named))
		for _, ie := range entries {
			if ie.iface == nil || ie.generic || ie.iface.NumMethods() == 0 {
				continue
			}
			has := true
			for i := 0; i < ie.iface.NumMethods() && has; i++ {
				m := ie.iface.Method(i)
				has = ms.Lookup(m.Pkg(), m.Name()) != nil
			}
			if has {
				g.st.genericNames++
				break
			}
		}
	}
}

// cmpGraphCall orders the calls of a function by position, and the entries of one call by
// callee.
func cmpGraphCall(a, b GraphCall) int {
	if c := cmp.Compare(a.Line, b.Line); c != 0 {
		return c
	}
	if c := cmp.Compare(a.Col, b.Col); c != 0 {
		return c
	}
	switch {
	case a.Callee == nil && b.Callee == nil:
		return 0
	case a.Callee == nil:
		return -1
	case b.Callee == nil:
		return 1
	}
	return cmpPos(*a.Callee, *b.Callee)
}
