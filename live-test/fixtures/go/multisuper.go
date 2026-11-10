package main

// Interface-satisfaction topology: the shapes a Go method's super set and a
// type's hierarchy can take — same-signature interfaces, embedding chains,
// struct-embedding promotion, and stdlib-interface satisfaction.
type IRender interface {
	Name() string
}

type IDisplay interface {
	Name() string
}

// Triple's single Name method implicitly satisfies both IRender and IDisplay
// — one method with two same-signature interface supers.
type Triple struct{}

func (t *Triple) Name() string { return "triple" }

// Pattern 1: Interface embedding chain (3 levels, no new methods)
// The chain is exercised from both ends — subtypes looking down from IBase,
// supertypes looking up from ILeaf; ChainImpl's Chain satisfies all three.
type IBase interface {
	Chain() string
}

type IMid interface {
	IBase
}

type ILeaf interface {
	IMid
}

type ChainImpl struct{}

func (c *ChainImpl) Chain() string { return "chain" }

// Pattern 2: Interface embedding with new methods at each level
type IBaseM interface {
	Base() string
}

type IMidM interface {
	IBaseM
	Mid() string
}

type IFull interface {
	IMidM
	Full() string
}

type FullImpl struct{}

func (f *FullImpl) Base() string { return "base" }
func (f *FullImpl) Mid() string  { return "mid" }
func (f *FullImpl) Full() string { return "full" }

// Pattern 3: Struct embedding (method promotion + override)
type Inner struct{}

func (i Inner) Hello() string { return "inner" }

type Outer struct{ Inner }

func (o Outer) Hello() string { return "outer" }

// Pattern 4: Stdlib interface satisfaction (fmt.Stringer)
type Greeter struct{}

func (g Greeter) String() string { return "greeter" }

// Additional interfaces to deepen multi-super coverage.
// Go uses structural typing: these declarations alone make existing
// types satisfy more interfaces simultaneously (no struct changes needed).

// IPower gives FullImpl.Full a second satisfied interface (alongside IFull).
type IPower interface {
	Full() string
}

// IGreetable and ISpeaker give Outer.Hello (and Inner.Hello) two interface
// satisfactions on top of struct-embedding promotion/shadowing.
type IGreetable interface {
	Hello() string
}

type ISpeaker interface {
	Hello() string
}

// INamer and ITextual give Greeter.String two extra satisfied interfaces
// in addition to fmt.Stringer (three total).
type INamer interface {
	String() string
}

type ITextual interface {
	String() string
}
