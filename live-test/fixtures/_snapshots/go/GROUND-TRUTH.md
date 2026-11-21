# Captured ground truth: Go fixture

These results of the Go fixture look wrong, but the IDE returns the same. Do not change
a probe to "fix" one. The notes that cover more than one language are in
[../GROUND-TRUTH.md](../GROUND-TRUTH.md).

- **Go `hier-type-*` resolves structural interfaces**: a struct (`Circle`,
  `Rectangle`, `Square`) lists the interfaces it implicitly satisfies as
  `supertypes` (`Drawable`, `Shape`), and an interface (`Drawable`, `Shape`)
  lists its implementers as `subtypes` — even though Go has no explicit
  `implements`. Types with neither (`baseShape`, `ShapeCollection`) return
  empty, as expected.
- **Go `qualifiedName` uses `package.Type.Method`** (e.g. `main.Circle.Area`,
  `main.Drawable.Draw`): GoLand registers no `QualifiedNameProvider` for Go, so
  `QualifiedNameUtil.goFallback` builds the FQN by reflection (`package.Function` /
  `package.Receiver.Method` / `package.Interface.method`). Nearly all Go elements
  resolve; a few positions still return `null`.
- **Go `super-Standalone.Compute-negative`**: a method satisfying no interface
  returns an empty `hierarchy` (method found, no super), matching
  Java/Python/Kotlin. Verified in GoLand: no gutter icon, Ctrl+U no-ops.
- **Go `super-IFull.Full` returns the interface method with an empty hierarchy (#135).** The
  rule is the same as for `super-Standalone.Compute-negative` and the Rust inherent method. At
  this position the Go to Super popup of GoLand says "Type 'IFull' Implements 3 Interfaces".
  The type result is in `super-IFull-type` (a position on the type name) and
  `super-IFull.IMidM-embedded` (a position on an embedded interface). Approved deviation: see
  "Where a tool differs from the IDE on purpose" in
  [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose).
- **Go `impls-Stamper.Stamp-promoted` has one row for two hits (#129).** `Pad` embeds `*Ink`
  and gets `Stamp` by promotion. GoLand's search gives the declared method of `Ink` and a second
  element for the promoted method (`GoLightMethodDeclaration`). That element has no text of
  its own, only the declared method as its navigation element, and it does not name `Pad`. The
  Choose Implementation popup of GoLand shows two equal rows `Ink` for this small result, and
  both rows open the declared method. For a long list, caddy `Validate` shows "1,933 found",
  the count of the tool. The type anchor (`impls-Stamper-promoted`) lists both `Ink` and `Pad`.
  Approved deviation: see "Where a tool differs from the IDE on purpose" in
  [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose).
- **Go `explain-Main-name` resolves a type with the name of its package.** GoLand's symbol
  index knows a symbol as `package.name`, so the text `Main` matches each symbol of the
  package `main`, and the popup ranks the type after dozens of them. The name anchors take
  each item with the exact name, wherever the popup ranks it (#131).
- **Go `file_structure` is package-scoped**: `file-structure-Normal` /
  `file-structure-Quirks` list *every* type in package `main` (each tagged
  with its origin file), not just the queried file's. Adding any `.go` fixture
  to the package changes these snapshots — re-bless them when you add Go
  fixtures (this is why they drift after `multisuper.go` / `*_super.go` land).
- **Go `find_usages` on a type counts the method receiver as a usage**:
  `usage-baseShape-embed` (find_usages of the `baseShape` struct) returns 20
  usages — the three embed sites (`Labeled` embed.go:9, `Circle` normal.go:38,
  `Rectangle` normal.go:51), the receiver declaration
  `func (b baseShape) Describe()` at normal.go:33, **plus 13 in `normal_test.go`**:
  6 `baseShape baseShape` field types, 1 `baseShape{}` literal, and 6
  composite-literal keys `baseShape: tt.fields.baseShape`. The receiver names the
  type, so GoLand counts it as a reference. Verified in GoLand (Find Usages lists the
  receiver). The keys name the embedded field (`ide_find_definition` on one
  resolves to the `ANONYMOUS_FIELD` at normal.go:38); GoLand 2026.1 did not list
  them (11 usages), 2026.2 does. The other 3 are the word `baseShape` in the
  fixture comments at normal.go:25, 28 and 29 (`usageType` `COMMENT`, see the note on
  #130 and #132 below). Not a tool artifact.
- **Go `find_usages` on a type leaves out the literal keys of a same-named field (#213).**
  When a struct has a named field with the name of a type (`CA *CA`), Find Usages of
  GoLand on the type also lists each composite literal key that names that field
  (`Issuer{CA: ca}`). The reference of a key is a `PsiMultiReference` with a field
  part and an identifier part, and `isReferenceTo` is true when one part matches
  (bytecode of `intellij.go.impl.jar`, build 262.8665; the facts are in the KDoc of
  `GoFindUsages.isFieldKeyOfType`). The tool leaves out a key that resolves to a named
  field declaration (`GoFieldDefinition`). A key that does not resolve stays, and the 6
  keys of the embedded field in `usage-baseShape-embed` stay. The fixture has no key of a
  named field with the name of a type, so no fixture row has such a `notes` entry. The
  caddy row `usage-caddytls.CA-field-keys` pins the rule. Approved deviation: see "Where
  a tool differs from the IDE on purpose" in
  [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose).
- **Go `find_usages` gives what the Find Usages action of GoLand lists (#130, #132).**
  For a method that implements an interface method, the result also has the
  usages of the interface method, and each of these usages has `match` `BASE`:
  `usage-area-libraries-scope` and `usage-Rectangle.Area-files-scope` list the
  `s.Area()` calls through `Shape` in `TotalArea` and `Largest` with `BASE`. The
  `notes` entry of the first page names the interface method
  (`main.Shape.Area (normal.go:21:2)`) and gives the count of the `BASE` usages.
  Approved deviation: see "Where a tool differs from the IDE on purpose" in
  [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose).
  A method with no super method gets no note (`usage-ShapeCollection.add`). A
  comment word that spells the name is a usage with `usageType` `COMMENT`, at the
  position of the word: the "Usage in comments" group of GoLand
  (`usage-Circle-struct`, `usage-Shape-iface`). `ide_explain_symbol` counts these
  usages in `usageCount`, and its `topUsages` lists the code usages first.
