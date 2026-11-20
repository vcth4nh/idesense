# Captured ground truth: openrefine

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **openrefine: no link from JavaScript to Java through Rhino.** The `controller.js` files
  call Java through `Packages.com.google.refine...` of Rhino. IntelliJ does not resolve
  these names: `def-RefineServlet.registerCommand-from-js` gives the error "Could not resolve
  symbol definition", and `usage-RefineServlet.registerCommand-from-js` gives no usage. In
  IntelliJ, Go to Declaration does nothing at that position, and Find Usages says "Nothing
  found". The error row needs the two-step bless (see "Rows that pin an expected error").
- **openrefine: Java usage rows with no `warnings` entry (#175).** The Java usage rows have
  no `warnings` entry now: the tool searches the method itself and does not read
  `primaryElements` of the handler. The usage lists did not change: Find Usages of
  `Row.getCellValue` shows 45 results, and the tool gives 20 production and 25 test usages.
  The row `usage-StandardReconConfig.batchRecon-override-mixed` (`StandardReconConfig.java:570:24`)
  gives 10 usages. 9 usages have no `match`: they are calls on a `StandardReconConfig`
  receiver. `ReconOperation.java:309:51` has `BASE`: the call `_reconConfig.batchRecon(...)`
  is on a field of the base type `ReconConfig`. The `notes` entry names
  `ReconConfig#batchRecon` (`ReconConfig.java:119:33`). That base declaration as an anchor
  gives the same 10 usages. This row has no window observation of its own; IntelliJ IDEA
  searches the deepest super methods of a Java method (see the fixture entry).
