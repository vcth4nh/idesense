# Captured ground truth: Kotlin fixture

These results of the Kotlin fixture look wrong, but the IDE returns the same. Do not change
a probe to "fix" one. The notes that cover more than one language are in
[../GROUND-TRUTH.md](../GROUND-TRUTH.md).

- **Kotlin `qualifiedName` uses `#` for methods** (e.g. `demo.Shape#area`):
  correct — matches IntelliJ's "Copy Reference" format and is consistent
  with Java.
