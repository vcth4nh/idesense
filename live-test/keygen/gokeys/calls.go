package main

import (
	"fmt"
	"go/ast"
	"go/token"
	"go/types"
	"io"
	"slices"
	"sort"
	"strings"
	"time"

	"golang.org/x/tools/go/packages"
	"golang.org/x/tools/go/ssa"
	"golang.org/x/tools/go/ssa/ssautil"
)

// CallRecord is one function declaration (*ast.FuncDecl) of a module file of the tree, with
// each use of its name. ID is the id of gokeys extract, "" when extract gives the declaration
// no record (init, the name _). Decl is the position of the name token, End the last line of
// the declaration.
type CallRecord struct {
	ID        string    `json:"id"`
	Lang      string    `json:"lang"`
	Kind      string    `json:"kind"`
	Name      string    `json:"name"`
	Container string    `json:"container"`
	Decl      Pos       `json:"decl"`
	End       int       `json:"end"`
	Configs   []string  `json:"configs"`
	Uses      []CallUse `json:"uses"`
}

// CallUse is one identifier that resolves to the declaration of its record. Call: the
// identifier is the function operand of a call expression. In: the decl position of the
// function declaration that holds the use, nil outside each function declaration. Lit: the use
// is inside a function literal.
type CallUse struct {
	File    string   `json:"file"`
	Line    int      `json:"line"`
	Col     int      `json:"col"`
	Call    bool     `json:"call"`
	In      *Pos     `json:"in"`
	Lit     bool     `json:"lit"`
	Configs []string `json:"configs"`
}

type callDecl struct {
	rec     CallRecord // with no configs and no uses
	present uint32     // bit i: the load of configs[i] has the declaration
	uses    map[Pos]*callUse
}

type callUse struct {
	call, lit bool
	in        *Pos
	present   uint32
}

type callStats struct {
	loads                                       []string
	records, noID, uses, callFalse, inNull, lit int
}

func (s *callStats) print(w io.Writer, total time.Duration) {
	for _, l := range s.loads {
		fmt.Fprintln(w, l)
	}
	fmt.Fprintf(w, "records: %d, with id \"\" %d\n", s.records, s.noID)
	fmt.Fprintf(w, "uses: %d, call false %d, in null %d, lit true %d\n", s.uses, s.callFalse, s.inNull, s.lit)
	fmt.Fprintf(w, "time: %.1fs\n", total.Seconds())
}

// extractCalls loads the module at tree one time for each configuration and gives a record for
// each function declaration of a module file, sorted by decl. With check it also takes the
// static calls of the SSA program of each load (ssaCalls).
func extractCalls(tree string, configs []string, check bool) ([]CallRecord, *callStats, []*ssaCheck, error) {
	x, err := newExtractor(tree, configs)
	if err != nil {
		return nil, nil, nil, err
	}
	decls := map[Pos]*callDecl{}
	st := &callStats{}
	var checks []*ssaCheck
	for ci, goos := range configs {
		start := time.Now()
		initial, all, fset, modPaths, err := x.loadPackages(ci, true)
		if err != nil {
			return nil, nil, nil, err
		}
		if err := x.readSources(initial, fset); err != nil {
			return nil, nil, nil, err
		}
		objID, _ := x.declareAll(all, fset, modPaths)
		here := map[Pos]bool{} // the declarations of this load
		for _, p := range initial {
			x.funcDecls(p, fset, objID, func(fd *ast.FuncDecl, obj *types.Func, pos Pos) {
				d := decls[pos]
				if d == nil {
					d = &callDecl{rec: x.callRecord(fd, obj, pos, fset, objID), uses: map[Pos]*callUse{}}
					decls[pos] = d
				}
				d.present |= 1 << ci
				here[pos] = true
			})
		}
		for _, p := range initial {
			x.callUses(p, fset, ci, decls)
		}
		if check {
			ch, err := x.ssaCalls(initial, fset, goos, here)
			if err != nil {
				return nil, nil, nil, err
			}
			checks = append(checks, ch)
		}
		st.loads = append(st.loads, loadLine(goos, len(initial), len(all), time.Since(start)))
	}
	keys := make([]Pos, 0, len(decls))
	for k := range decls {
		keys = append(keys, k)
	}
	sortPos(keys)
	recs := make([]CallRecord, 0, len(keys))
	for _, k := range keys {
		d := decls[k]
		r := d.rec
		r.Configs = x.configList(d.present)
		ups := make([]Pos, 0, len(d.uses))
		for u := range d.uses {
			ups = append(ups, u)
		}
		sortPos(ups)
		r.Uses = make([]CallUse, 0, len(ups))
		for _, up := range ups {
			u := d.uses[up]
			r.Uses = append(r.Uses, CallUse{File: up.File, Line: up.Line, Col: up.Col, Call: u.call, In: u.in, Lit: u.lit,
				Configs: x.configList(u.present)})
			st.uses++
			if !u.call {
				st.callFalse++
			}
			if u.in == nil {
				st.inNull++
			}
			if u.lit {
				st.lit++
			}
		}
		st.records++
		if r.ID == "" {
			st.noID++
		}
		recs = append(recs, r)
	}
	return recs, st, checks, nil
}

func cmpPos(a, b Pos) int {
	if a.File != b.File {
		return strings.Compare(a.File, b.File)
	}
	if a.Line != b.Line {
		return a.Line - b.Line
	}
	return a.Col - b.Col
}

func sortPos(ps []Pos) { slices.SortFunc(ps, cmpPos) }

// treePos gives the position of p in a module file of the load (x.position), or false for a
// position outside these files.
func (x *extractor) treePos(fset *token.FileSet, p token.Pos) (Pos, bool) {
	if !p.IsValid() {
		return Pos{}, false
	}
	rel, ok := x.relFile(fset.PositionFor(p, false).Filename)
	if !ok || x.src[rel] == nil {
		return Pos{}, false
	}
	return x.position(fset, p)
}

// funcDecls calls fn for each function declaration of each module file of the package p.
func (x *extractor) funcDecls(p *packages.Package, fset *token.FileSet, objID map[types.Object]string,
	fn func(fd *ast.FuncDecl, obj *types.Func, pos Pos)) {
	for _, f := range p.Syntax {
		if _, ok := x.relFile(fset.File(f.Pos()).Name()); !ok {
			continue
		}
		for _, d := range f.Decls {
			fd, ok := d.(*ast.FuncDecl)
			if !ok {
				continue
			}
			obj, ok := p.TypesInfo.Defs[fd.Name].(*types.Func)
			if !ok {
				continue
			}
			if pos, ok := x.treePos(fset, fd.Name.Pos()); ok {
				fn(fd, obj, pos)
			}
		}
	}
}

// callRecord gives the record head of a function declaration: the id of extract (idOf), the
// kind, the name, the container (the type of the receiver, for a receiver through an alias the
// named type, as extract) and the last line.
func (x *extractor) callRecord(fd *ast.FuncDecl, obj *types.Func, pos Pos, fset *token.FileSet, objID map[types.Object]string) CallRecord {
	r := CallRecord{ID: idOf(objID, obj), Lang: "go", Kind: "func", Name: fd.Name.Name, Decl: pos,
		End: fset.PositionFor(fd.End(), false).Line}
	if recv := obj.Type().(*types.Signature).Recv(); recv != nil {
		r.Kind = "method"
		t := types.Unalias(recv.Type())
		if p, ok := t.(*types.Pointer); ok {
			t = types.Unalias(p.Elem())
		}
		if n, ok := t.(*types.Named); ok {
			r.Container = n.Origin().Obj().Name()
		}
	}
	return r
}

// calleeIdents gives the identifiers that are the function operand of a call expression in f:
// f(x), p.f(x), v.m(x), T.m(v, x), (*T).m(v, x), with parentheses around the operand or with
// explicit type arguments (f[int](x)).
func calleeIdents(f *ast.File) map[*ast.Ident]bool {
	out := map[*ast.Ident]bool{}
	ast.Inspect(f, func(n ast.Node) bool {
		c, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		switch e := callOperand(c).(type) {
		case *ast.Ident:
			out[e] = true
		case *ast.SelectorExpr:
			out[e.Sel] = true
		}
		return true
	})
	return out
}

// callOperand gives the function operand of the call c with no parentheses around it and with
// no index expression (explicit type arguments).
func callOperand(c *ast.CallExpr) ast.Expr {
	e := c.Fun
	for {
		e = ast.Unparen(e)
		switch ix := e.(type) {
		case *ast.IndexExpr:
			e = ix.X
			continue
		case *ast.IndexListExpr:
			e = ix.X
			continue
		}
		return e
	}
}

// callUses adds the uses of configuration ci in the module files of the package p: each
// identifier that resolves (types.Info.Uses; for a generic function or method, its origin) to
// a function declaration of the load.
func (x *extractor) callUses(p *packages.Package, fset *token.FileSet, ci int, decls map[Pos]*callDecl) {
	info := p.TypesInfo
	for _, f := range p.Syntax {
		if _, ok := x.relFile(fset.File(f.Pos()).Name()); !ok {
			continue
		}
		callee := calleeIdents(f)
		for _, d := range f.Decls {
			var in *Pos
			if fd, ok := d.(*ast.FuncDecl); ok {
				if pos, ok := x.treePos(fset, fd.Name.Pos()); ok {
					in = &pos
				}
			}
			lit := 0
			var stack []bool // for each node of the path: it is a function literal
			ast.Inspect(d, func(n ast.Node) bool {
				if n == nil {
					if stack[len(stack)-1] {
						lit--
					}
					stack = stack[:len(stack)-1]
					return true
				}
				_, isLit := n.(*ast.FuncLit)
				stack = append(stack, isLit)
				if isLit {
					lit++
				}
				id, ok := n.(*ast.Ident)
				if !ok {
					return true
				}
				obj, ok := info.Uses[id].(*types.Func)
				if !ok {
					return true
				}
				dpos, ok := x.treePos(fset, obj.Origin().Pos())
				if !ok || decls[dpos] == nil {
					return true // no function declaration of the tree (an interface method, a library function)
				}
				upos, ok := x.treePos(fset, id.Pos())
				if !ok {
					return true
				}
				u := decls[dpos].uses[upos]
				if u == nil {
					u = &callUse{call: callee[id], lit: lit > 0, in: in}
					decls[dpos].uses[upos] = u
				}
				u.present |= 1 << ci
				return true
			})
		}
	}
}

// The callers that the check excludes on the SSA side: no call of the source.
const (
	clsPackageInit = "package initializer"
	clsWrapper     = "wrapper"
	clsThunk       = "thunk"
	clsBound       = "bound method wrapper"
	clsInstWrapper = "instantiation wrapper"
)

var exclClasses = []string{clsPackageInit, clsWrapper, clsThunk, clsBound, clsInstWrapper}

// The prefixes of ssa.Function.Synthetic of the excluded callers (go/ssa: create.go,
// wrappers.go, instantiate.go).
var exclPrefix = map[string]string{
	"package initializer":       clsPackageInit,
	"wrapper for ":              clsWrapper,
	"thunk for ":                clsThunk,
	"bound method wrapper for ": clsBound,
	"instantiation wrapper of ": clsInstWrapper,
}

type callPair struct{ caller, callee Pos }

// exclCall is one static call of an excluded caller to a function declaration of the tree.
// self is the declaration at the position of the caller's own name (a wrapper, a thunk and a
// bound method wrapper have the position of the method that they wrap), selfOK false when it
// has none (the package initializer).
type exclCall struct {
	self   Pos
	selfOK bool
	callee Pos
}

// ssaCheck holds the static calls of the SSA program of one configuration.
type ssaCheck struct {
	config   string
	pairs    map[callPair]bool     // (caller declaration, callee declaration)
	excluded map[string][]exclCall // class → the calls of the excluded callers to a declaration of the tree
	calls    int                   // the static calls of the visited functions
	toDecl   int                   // of these, the calls of a function declaration of the tree
	toLit    int                   // the calls of a function literal (no declaration)
	dur      time.Duration
}

// ssaFunc is one function of the SSA visit (ssaVisit): the function, its outer function, and
// the class of an excluded caller or "".
type ssaFunc struct {
	fn    *ssa.Function
	outer *ssa.Function
	cls   string
}

// ssaVisit builds the SSA program of the loaded packages (ssautil.Packages, the default
// builder mode) and gives each function that it visits: the function of each function
// declaration of the packages of the patterns, each package initializer, the functions of
// ssautil.AllFunctions, and each function literal and each function that an instruction of a
// visited function names. The outer function of a function literal (or of a yield function of
// a range-over-func loop) is the outermost function that holds it, and the outer function of
// an instance is its origin. In the default builder mode an instance is an instantiation
// wrapper, whose body only calls the origin: as a caller it is excluded. A panic of the SSA
// builder is an error.
func ssaVisit(initial []*packages.Package) (out []ssaFunc, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("ssa: %v", r)
		}
	}()
	prog, pkgs := ssautil.Packages(initial, ssa.BuilderMode(0))
	prog.Build()

	seen := map[*ssa.Function]bool{}
	var fns []*ssa.Function
	var visit func(fn *ssa.Function)
	visit = func(fn *ssa.Function) {
		if fn == nil || seen[fn] {
			return
		}
		seen[fn] = true
		fns = append(fns, fn)
		for _, a := range fn.AnonFuncs {
			visit(a)
		}
		var buf [10]*ssa.Value
		for _, b := range fn.Blocks {
			for _, instr := range b.Instrs {
				for _, op := range instr.Operands(buf[:0]) {
					if g, ok := (*op).(*ssa.Function); ok {
						visit(g)
					}
				}
			}
		}
	}
	for i, p := range initial {
		sp := pkgs[i]
		if sp == nil {
			continue
		}
		visit(sp.Func("init"))
		for _, f := range p.Syntax {
			for _, d := range f.Decls {
				if fd, ok := d.(*ast.FuncDecl); ok {
					if obj, ok := p.TypesInfo.Defs[fd.Name].(*types.Func); ok {
						visit(prog.FuncValue(obj))
					}
				}
			}
		}
	}
	all := ssautil.AllFunctions(prog)
	rest := make([]*ssa.Function, 0, len(all))
	for fn := range all {
		rest = append(rest, fn)
	}
	sort.Slice(rest, func(i, j int) bool { return rest[i].String() < rest[j].String() })
	for _, fn := range rest {
		visit(fn)
	}
	for _, fn := range fns {
		outer := fn
		for outer.Parent() != nil {
			outer = outer.Parent()
		}
		cls := ""
		for prefix, c := range exclPrefix {
			if strings.HasPrefix(outer.Synthetic, prefix) {
				cls = c
			}
		}
		if o := outer.Origin(); o != nil && cls == "" {
			outer = o
		}
		out = append(out, ssaFunc{fn: fn, outer: outer, cls: cls})
	}
	return out, nil
}

// ssaCalls takes each call instruction with a static callee (CallCommon.StaticCallee) of the
// functions of ssaVisit, as golang.org/x/tools/go/callgraph/static does. A function maps to a
// declaration by the position of its name: a caller by its outer function, and a callee
// instance by its origin. A called function literal is no declaration. here holds the
// declarations of this load. A panic is an error.
func (x *extractor) ssaCalls(initial []*packages.Package, fset *token.FileSet, goos string, here map[Pos]bool) (ch *ssaCheck, err error) {
	start := time.Now()
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("%s: ssa: %v", goos, r)
		}
	}()
	fns, err := ssaVisit(initial)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", goos, err)
	}

	declMemo := map[*ssa.Function]Pos{}
	declOK := map[*ssa.Function]bool{}
	declOf := func(fn *ssa.Function) (Pos, bool) {
		if ok, done := declOK[fn]; done {
			return declMemo[fn], ok
		}
		pos, ok := x.treePos(fset, fn.Pos())
		ok = ok && here[pos]
		declMemo[fn], declOK[fn] = pos, ok
		return pos, ok
	}

	ch = &ssaCheck{config: goos, pairs: map[callPair]bool{}, excluded: map[string][]exclCall{}}
	for _, f := range fns {
		caller, callerOK := declOf(f.outer)
		for _, b := range f.fn.Blocks {
			for _, instr := range b.Instrs {
				site, ok := instr.(ssa.CallInstruction)
				if !ok {
					continue
				}
				g := site.Common().StaticCallee()
				if g == nil {
					continue
				}
				ch.calls++
				if g.Parent() != nil {
					ch.toLit++
					continue
				}
				if o := g.Origin(); o != nil {
					g = o
				}
				callee, ok := declOf(g)
				if !ok {
					continue
				}
				ch.toDecl++
				switch {
				case f.cls != "":
					ch.excluded[f.cls] = append(ch.excluded[f.cls], exclCall{self: caller, selfOK: callerOK, callee: callee})
				case callerOK:
					ch.pairs[callPair{caller, callee}] = true
				}
			}
		}
	}
	ch.dur = time.Since(start)
	return ch, nil
}

// syntaxPairs gives the pairs (in, the record) of each use with call true and in not null in
// the configuration config.
func syntaxPairs(recs []CallRecord, config string) map[callPair]bool {
	out := map[callPair]bool{}
	for _, r := range recs {
		for _, u := range r.Uses {
			if u.Call && u.In != nil && slices.Contains(u.Configs, config) {
				out[callPair{*u.In, r.Decl}] = true
			}
		}
	}
	return out
}

// printCheck compares, for each configuration, the pairs of the syntax with the pairs of the
// SSA program and prints the counts, at most 20 pairs of each one-sided class, and the counts
// of the SSA side. It reports whether both sides are equal in each configuration.
func printCheck(w io.Writer, recs []CallRecord, checks []*ssaCheck) bool {
	names := map[Pos]string{}
	for _, r := range recs {
		n := r.Name
		if r.Container != "" {
			n = r.Container + "." + n
		}
		names[r.Decl] = n
	}
	equal := true
	for _, ch := range checks {
		syn := syntaxPairs(recs, ch.config)
		both := 0
		var onlySyn, onlySSA []callPair
		for p := range syn {
			if ch.pairs[p] {
				both++
			} else {
				onlySyn = append(onlySyn, p)
			}
		}
		for p := range ch.pairs {
			if !syn[p] {
				onlySSA = append(onlySSA, p)
			}
		}
		fmt.Fprintf(w, "check %s: pairs: both %d, only syntax %d, only ssa %d\n", ch.config, both, len(onlySyn), len(onlySSA))
		for _, side := range []struct {
			label string
			list  []callPair
		}{{"only syntax", onlySyn}, {"only ssa", onlySSA}} {
			slices.SortFunc(side.list, func(a, b callPair) int {
				if c := cmpPos(a.caller, b.caller); c != 0 {
					return c
				}
				return cmpPos(a.callee, b.callee)
			})
			for i, p := range side.list {
				if i == 20 {
					fmt.Fprintf(w, "  %s: ... and %d more\n", side.label, len(side.list)-20)
					break
				}
				fmt.Fprintf(w, "  %s: caller %s:%d %s -> callee %s:%d %s\n", side.label,
					p.caller.File, p.caller.Line, names[p.caller], p.callee.File, p.callee.Line, names[p.callee])
			}
		}
		var excl []string
		for _, c := range exclClasses {
			excl = append(excl, fmt.Sprintf("%s %d", c, len(ch.excluded[c])))
		}
		fmt.Fprintf(w, "check %s: ssa %.1fs: static calls %d, to a function declaration of the tree %d, to a function literal %d; "+
			"excluded callers (calls to a declaration of the tree): %s\n",
			ch.config, ch.dur.Seconds(), ch.calls, ch.toDecl, ch.toLit, strings.Join(excl, ", "))
		if len(onlySyn)+len(onlySSA) > 0 {
			equal = false
		}
	}
	return equal
}
