package main

import (
	"fmt"
	"go/types"
	"io"
	"slices"
	"strings"
	"time"

	"golang.org/x/tools/go/packages"
	"golang.org/x/tools/go/ssa"
	"golang.org/x/tools/go/types/typeutil"
)

// graphCheck is the result of the SSA check of the graph (grapher.check), for printGraphCheck.
type graphCheck struct {
	goos      string
	dur       time.Duration
	pairs     map[graphPair]bool   // the call steps of the SSA form
	selects   map[ifaceSelect]bool // the methods that the types of a conversion select
	ifaces    []GraphIface         // the interface table that printGraphCheck compares the selections with
	noPos     []noPosCall          // the calls with a step and no position in a module file
	static    int                  // the calls with a static callee; a call of a thunk also counts in invoke
	invoke    int                  // the invoke calls of a method of a module interface and the calls of a thunk of one, with the calls of typeParam
	typeParam int                  // of the invoke calls, the calls through a type that mentions a type parameter
	initCalls int                  // the static calls of a package initializer to a function of the graph, at a position in a module file
	converted int                  // the operand types of the MakeInterface instructions with no type parameter
	outside   int                  // of these, the types outside the type list (grapher.concrete) that implement an interface of the table with a method
	paramOps  int                  // the operand types of the MakeInterface instructions that are or contain a type parameter
}

// noPosCall is a call with a step and no position: the decl of the outer function of its caller,
// and the decls of its callees.
type noPosCall struct {
	caller  Pos
	callees []Pos
}

// graphPair is one call step: the file and the line of the call, and the decl of the callee.
type graphPair struct {
	file   string
	line   int
	callee Pos
}

// ifaceSelect is the function of the graph (callee) that a type (typ, its type string) selects
// for a method of an interface of the table (method, the id of the interface method). generic:
// the type is an instance of a generic type, also behind a pointer.
type ifaceSelect struct {
	method  string
	callee  Pos
	typ     string
	generic bool
}

// check builds the SSA form of the build (ssaVisit) and gives the SSA side of the check. The
// steps come from the calls of the functions whose outer function is a function of the graph,
// with the same excluded callers as ssaCalls (checkCall). Of the excluded callers, the check
// counts the calls of a package initializer to a function of the graph (initCall). The
// selections come from the operand types of the MakeInterface instructions of each function of
// the visit (selections). ifaces is the table that printGraphCheck compares the selections with.
func (g *grapher) check(initial []*packages.Package, goos string, entries []*typeEntry, ifaces []GraphIface) (*graphCheck, error) {
	start := time.Now()
	fns, err := ssaVisit(initial)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", goos, err)
	}
	ch := &graphCheck{goos: goos, pairs: map[graphPair]bool{}, selects: map[ifaceSelect]bool{}, ifaces: ifaces}
	if len(fns) == 0 {
		ch.dur = time.Since(start)
		return ch, nil // no function: no call and no conversion
	}
	prog := fns[0].fn.Prog
	var converted typeutil.Map // the operand types of the MakeInterface instructions
	var impls typeutil.Map     // interface type → the types of the type list that implement it
	for _, f := range fns {
		caller, inGraph := g.funcAt(f.outer.Pos())
		for _, b := range f.fn.Blocks {
			for _, instr := range b.Instrs {
				switch in := instr.(type) {
				case *ssa.MakeInterface:
					converted.Set(in.X.Type(), true)
				case ssa.CallInstruction:
					switch {
					case f.cls == "" && inGraph:
						g.checkCall(ch, prog, caller, in.Common(), &impls)
					case f.cls == clsPackageInit && g.initCall(in.Common()):
						ch.initCalls++
					}
				}
			}
		}
	}
	g.selections(ch, prog, &converted, entries)
	ch.dur = time.Since(start)
	return ch, nil
}

// initCall reports whether the call c of a package initializer is a static call of a function
// of the graph at a position in a module file. The call of each func init of the package has no
// position (go/ssa: buildPackageInit), so it does not count.
func (g *grapher) initCall(c *ssa.CallCommon) bool {
	callee := c.StaticCallee()
	if callee == nil {
		return false
	}
	_, ok := g.staticDecl(callee)
	_, posOK := g.x.treePos(g.fset, c.Pos())
	return ok && posOK
}

// staticDecl gives the decl of the static callee fn (of its origin for an instance), and whether
// it is a function of the graph. A function literal is none.
func (g *grapher) staticDecl(fn *ssa.Function) (Pos, bool) {
	if fn.Parent() != nil {
		return Pos{}, false
	}
	if o := fn.Origin(); o != nil {
		fn = o
	}
	return g.funcAt(fn.Pos())
}

// checkCall adds the steps of the call c, whose caller has the outer function with the decl
// caller. A static callee that is no function literal gives a step to its origin. An invoke of
// a method of a module interface, and a call of a thunk of one (I.M(v)), give a step to the
// method that the method set of *T selects, for each type T of the type list where T or *T
// implements the interface; such a call through a type that mentions a type parameter gives no
// step. Only a function of the graph is a callee. A call with a step and no position in a module
// file gives no pair: the check keeps its caller and its callees (noPos).
func (g *grapher) checkCall(ch *graphCheck, prog *ssa.Program, caller Pos, c *ssa.CallCommon, impls *typeutil.Map) {
	inv := c // the invoke call: c, or the call of the body of a thunk
	callee := c.StaticCallee()
	if callee != nil {
		ch.static++
		inv = nil
		if strings.HasPrefix(callee.Synthetic, "thunk for ") {
			inv = thunkInvoke(callee) // nil for a thunk of a concrete method
		}
	}
	var callees []Pos
	switch {
	case inv != nil && inv.IsInvoke() && g.module(inv.Method):
		ch.invoke++
		it := inv.Value.Type()
		if hasTypeParam(it) || hasTypeParam(it.Underlying()) {
			ch.typeParam++
			return
		}
		l, ok := impls.At(it).([]*implType)
		if !ok {
			iface := it.Underlying().(*types.Interface)
			for _, te := range g.concrete {
				if types.Implements(te.typ, iface) || types.Implements(types.NewPointer(te.typ), iface) {
					l = append(l, te)
				}
			}
			impls.Set(it, l)
		}
		for _, te := range l {
			sel := prog.MethodSets.MethodSet(types.NewPointer(te.typ)).Lookup(inv.Method.Pkg(), inv.Method.Name())
			if decl, ok := g.funcDecl(sel.Obj().(*types.Func)); ok {
				callees = append(callees, decl)
			}
		}
	case callee != nil:
		if decl, ok := g.staticDecl(callee); ok {
			callees = append(callees, decl)
		}
	}
	if len(callees) == 0 {
		return
	}
	pos, ok := g.x.treePos(g.fset, c.Pos())
	if !ok {
		slices.SortFunc(callees, cmpPos)
		ch.noPos = append(ch.noPos, noPosCall{caller: caller, callees: slices.Compact(callees)})
		return
	}
	for _, d := range callees {
		ch.pairs[graphPair{file: pos.File, line: pos.Line, callee: d}] = true
	}
}

// thunkInvoke gives the invoke call of the body of the thunk fn, or nil when the body has none.
func thunkInvoke(fn *ssa.Function) *ssa.CallCommon {
	for _, b := range fn.Blocks {
		for _, instr := range b.Instrs {
			if site, ok := instr.(ssa.CallInstruction); ok && site.Common().IsInvoke() {
				return site.Common()
			}
		}
	}
	return nil
}

// selections adds the function of the graph that each converted type X selects for each method
// of each interface of the table that X implements (the method set of X). It counts the types
// with no type parameter, and of these the types that implement an interface of the table with
// a method and that the type list does not hold (X, or the element type of the pointer X). It
// counts the types that are or contain a type parameter apart. The default builder mode builds
// a generic function body one time, with its type parameters, so the check never sees the type
// arguments of an instance: a type that the code converts only in a generic body, as a type
// argument, is no type of this source. (A value of a type parameter whose constraint has the
// underlying type of the target interface converts with ChangeType: it gives no operand.)
func (g *grapher) selections(ch *graphCheck, prog *ssa.Program, converted *typeutil.Map, entries []*typeEntry) {
	type tableIface struct {
		iface   *types.Interface
		methods []*types.Func // the explicit methods that a module file declares, as in ifaceTable
	}
	var table []tableIface
	for _, te := range entries {
		if te.iface == nil || te.generic {
			continue
		}
		ti := tableIface{iface: te.iface}
		for i := 0; i < te.iface.NumExplicitMethods(); i++ {
			m := te.iface.ExplicitMethod(i)
			if _, ok := g.x.treePos(g.fset, m.Pos()); ok {
				ti.methods = append(ti.methods, m)
			}
		}
		table = append(table, ti)
	}
	var list typeutil.Map
	for _, te := range g.concrete {
		list.Set(te.typ, true)
	}
	converted.Iterate(func(x types.Type, _ any) {
		param := hasTypeParam(x) || hasTypeParam(x.Underlying())
		if param {
			ch.paramOps++
		} else {
			ch.converted++
		}
		elem := x
		if p, ok := types.Unalias(x).(*types.Pointer); ok {
			elem = p.Elem()
		}
		named, ok := types.Unalias(elem).(*types.Named)
		generic := ok && named.TypeArgs().Len() > 0
		ms := prog.MethodSets.MethodSet(x)
		implementing := false
		for _, ti := range table {
			if len(ti.methods) == 0 || !types.Implements(x, ti.iface) {
				continue
			}
			implementing = true
			for _, m := range ti.methods {
				sel := ms.Lookup(m.Pkg(), m.Name())
				if decl, ok := g.funcDecl(sel.Obj().(*types.Func)); ok {
					ch.selects[ifaceSelect{method: idOf(g.objID, m), callee: decl, typ: x.String(), generic: generic}] = true
				}
			}
		}
		if !param && implementing && list.At(x) == nil && list.At(elem) == nil {
			ch.outside++
		}
	})
}

// printGraphCheck compares the steps of funcs (the entries direct, embedded and iface) with the
// pairs of the SSA side, and the selections of the SSA side with the interface table of ch. It
// prints the counts, at most 20 pairs of each one-sided class, the counts of the SSA side with
// at most 20 calls with no position, and at most 20 callees that the table lacks, each with the
// first type that selects it. A callee
// that only instances of a generic type select is counted apart (generic), and at most 20 of
// them follow: the table has no generic type. It reports whether both sides are equal and the
// table lacks no other callee.
func printGraphCheck(w io.Writer, funcs []GraphFunc, ch *graphCheck) bool {
	names := map[Pos]string{}
	syn := map[graphPair]bool{}
	for _, f := range funcs {
		n := f.Name
		if f.Container != "" {
			n = f.Container + "." + n
		}
		names[f.Decl] = n
		for _, c := range f.Calls {
			if c.Kind != "other" {
				syn[graphPair{file: f.Decl.File, line: c.Line, callee: *c.Callee}] = true
			}
		}
	}
	both := 0
	var onlySyn, onlySSA []graphPair
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
	fmt.Fprintf(w, "check %s: pairs: both %d, only syntax %d, only ssa %d\n", ch.goos, both, len(onlySyn), len(onlySSA))
	for _, side := range []struct {
		label string
		list  []graphPair
	}{{"only syntax", onlySyn}, {"only ssa", onlySSA}} {
		slices.SortFunc(side.list, func(a, b graphPair) int {
			if c := cmpPos(Pos{File: a.file, Line: a.line}, Pos{File: b.file, Line: b.line}); c != 0 {
				return c
			}
			return cmpPos(a.callee, b.callee)
		})
		var lines []string
		for _, p := range side.list {
			lines = append(lines, fmt.Sprintf("%s:%d -> callee %s:%d %s", p.file, p.line, p.callee.File, p.callee.Line, names[p.callee]))
		}
		printFirst20(w, side.label, lines)
	}
	fmt.Fprintf(w, "check %s: ssa %.1fs: static calls %d, invoke calls of module interface methods %d, "+
		"calls with no position %d, calls on a type parameter %d, calls from a package initializer to a function of the graph %d\n",
		ch.goos, ch.dur.Seconds(), ch.static, ch.invoke, len(ch.noPos), ch.typeParam, ch.initCalls)
	noPos := slices.Clone(ch.noPos)
	slices.SortFunc(noPos, func(a, b noPosCall) int {
		if c := cmpPos(a.caller, b.caller); c != 0 {
			return c
		}
		return slices.CompareFunc(a.callees, b.callees, cmpPos)
	})
	var noPosLines []string
	for _, c := range noPos {
		var callees []string
		for _, d := range c.callees {
			callees = append(callees, fmt.Sprintf("%s:%d %s", d.File, d.Line, names[d]))
		}
		noPosLines = append(noPosLines, fmt.Sprintf("caller %s:%d %s -> callee %s",
			c.caller.File, c.caller.Line, names[c.caller], strings.Join(callees, ", ")))
	}
	printFirst20(w, "no position", noPosLines)

	have := map[string]map[Pos]bool{} // interface method id → the methods of its implementer entries
	for _, gi := range ch.ifaces {
		for _, gm := range gi.Methods {
			for _, im := range gm.Impls {
				if im.Method != nil {
					addTo(have, gm.ID, *im.Method)
				}
			}
		}
	}
	// (interface method, callee) → the first type string: lacks for a type that is no instance of
	// a generic type, generic for a callee that only such instances select
	lacks, generic := map[ifaceSelect]string{}, map[ifaceSelect]string{}
	for s := range ch.selects {
		if have[s.method][s.callee] {
			continue
		}
		m := lacks
		if s.generic {
			m = generic
		}
		k := ifaceSelect{method: s.method, callee: s.callee}
		if t, ok := m[k]; !ok || s.typ < t {
			m[k] = s.typ
		}
	}
	for k := range lacks {
		delete(generic, k)
	}
	fmt.Fprintf(w, "check %s: types: converted to an interface %d, of these outside the type list %d, callees that the table lacks %d, "+
		"by an instance of a generic type %d, operands with a type parameter %d\n",
		ch.goos, ch.converted, ch.outside, len(lacks), len(generic), ch.paramOps)
	for _, side := range []struct {
		label string
		m     map[ifaceSelect]string
	}{{"lacks", lacks}, {"generic", generic}} {
		keys := make([]ifaceSelect, 0, len(side.m))
		for k := range side.m {
			keys = append(keys, k)
		}
		slices.SortFunc(keys, func(a, b ifaceSelect) int {
			if c := strings.Compare(a.method, b.method); c != 0 {
				return c
			}
			return cmpPos(a.callee, b.callee)
		})
		var lines []string
		for _, k := range keys {
			lines = append(lines, fmt.Sprintf("%s -> %s:%d %s, by the type %s", k.method, k.callee.File, k.callee.Line, names[k.callee], side.m[k]))
		}
		printFirst20(w, side.label, lines)
	}
	return len(onlySyn)+len(onlySSA)+len(lacks) == 0
}

// printFirst20 prints the line "  <label>: <line>" for each of the first 20 lines, and then
// "  <label>: ... and <k> more" for the rest.
func printFirst20(w io.Writer, label string, lines []string) {
	for i, l := range lines {
		if i == 20 {
			fmt.Fprintf(w, "  %s: ... and %d more\n", label, len(lines)-20)
			return
		}
		fmt.Fprintf(w, "  %s: %s\n", label, l)
	}
}
