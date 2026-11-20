# Captured ground truth: Java fixture

These results of the Java fixture look wrong, but the IDE returns the same. Do not change
a probe to "fix" one. The notes that cover more than one language are in
[../GROUND-TRUTH.md](../GROUND-TRUTH.md).

- **Java `find-symbol` for overridden methods**: collapses to the topmost
  super; concrete overrides on subclasses are not separately surfaced.
- **Java hierarchy node `name` is the bare member or class name** (IntelliJ
  2026.2+): call-hierarchy nodes read `describe()` / `Circle(double)`, and
  type-hierarchy nodes read `Cat` / `Enum constant 'INT'`. The tool keeps only
  the primary-text part of the IDE node. Since 2026.2 the IDE puts the class
  context (`Shape.`, `in Modern`) in the grey location part
  (`JavaHierarchyNodeDescriptor.appendLocationPath`), which the tool drops; the
  class stays in `qualifiedName` (`demo.Shape#describe`). Kotlin call
  hierarchies show the same for Java library callees (`append(String)`,
  `abs(int)`).
- **Java `super-LambdaHost-lambda.run-sam`**: returns the lambda's SAM as the
  `method` (`java.lang.Runnable#run`, empty `hierarchy`). Caret is on a lambda's
  `->`; the provider resolves the functional interface's single abstract method
  via `LambdaUtil.getFunctionalInterfaceMethod`, mirroring Ctrl+U. Resolved in
  #22 (was previously a `tool_error`).
