# Captured ground truth: exposed

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **exposed: a library item is a source file in a definition and a `.class` file in a
  hierarchy.** `ide_find_definition` into a library gives the file in the sources jar:
  `LoggerFactory.java` (`canary-def-LoggerFactory.getLogger-into-dependency`),
  `Builders.common.kt` (`def-withContext-into-kotlin-dependency`) and `UUID.java` of the JDK
  (`def-JavaUUID-via-import-alias`). `ide_type_hierarchy`, `ide_find_super_methods` and
  `ide_call_hierarchy` give the `.class` file of the same libraries, for example
  `AbstractPlatformTransactionManager.class` in `canary-hier-super-SpringTransactionManager`,
  also when the sources jar is there. The product `openrefine` shows the same (see
  `live-test/real-products/_setup/openrefine/notes.md`, "Setup").
- **exposed: files of `samples/` and `documentation-website/` are in the results.** These
  folders hold separate Gradle builds with their own settings files, and IntelliJ does not
  import them as modules. Their files are still project files under the project root. So
  `find-file-EntityClass.kt` gives `BaseEntityClass.kt` of
  `documentation-website/Writerside/snippets/`, `find-file-CommentRepository.kt` gives a file
  of `samples/`, and the `OFFSET` search gives
  `documentation-website/Writerside/topics/Breaking-Changes.md`. Find in Files of IntelliJ IDEA
  (In Project) also counts that Markdown file in its 13 matches for `OFFSET`.
- **exposed: `hier-callee-JdbcPreparedStatementImpl.executeMultiple-java` has two callees
  only.** The tool gives `execute()` and `getMoreResults(int)` of `java.sql`. The body of the
  method also reads `statement.resultSet` and `statement.updateCount` (Java getters as Kotlin
  properties), and calls constructors and `listOf`. The Callees view of IntelliJ IDEA
  2026.3 (IU-263.7307.200) shows the same two callees. For constructor callees in Kotlin, see
  the note on `hier-callee-makeDefault` in `live-test/fixtures/_snapshots/GROUND-TRUTH.md`.
- **exposed: `hier-caller-ExposedSQLException.causedByQueries-bysymbol` has `maxDepth` 1.**
  The first level has two callers, `logSQLException` and `ExposedSQLException.toString()`, as
  in the Callers view of IntelliJ IDEA. At depth 2, the callers of `toString()` are the calls
  of `toString()` on any receiver: files of the Kotlin standard library and many project
  files. That result was cut at 200 nodes, its children differed between two equal runs, a
  warm call took 43 s, and one call of a product run hit the request timeout of 60 s. The
  Callers view of IntelliJ IDEA did not load the callers of `toString()` in 38 s either. Do
  not make the row deeper.
- **exposed: `def-Select-via-typealias` goes to the type alias.** `Queries.kt:47` calls
  `Select(...)`, and `Select` is the type alias of `Table.kt:29` (`typealias Select = Slice`).
  Go to Declaration of IntelliJ IDEA lands on the name of the alias at 29:11, as the tool does.
  The `qualifiedName` `org.jetbrains.exposed.v1.core.Select` is an approved deviation: the IDE
  gives no qualified name for a Kotlin type alias (see "The qualified name of a Kotlin type
  alias" in `docs/ARCHITECTURE.md`).
- **exposed: the `OFFSET` rows with a `context`.** Find in Files for `OFFSET` (In Project,
  Match case, Words) gives 13 matches: 4 with the filter "Except Comments and String Literals",
  3 with "In Comments" and 6 with "In String Literals". `search-text-OFFSET-code`,
  `search-text-OFFSET-comments` and `search-text-OFFSET-strings` give the same lines. The 4
  lines of `search-text-OFFSET-code` are text in two Markdown files and in two HTML pages below
  `docs/api/`.
- **exposed: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `impls-IColumnType`, `impls-Expression-paged` | #277 | each object expression drops out: 70 of the 71 implementations that Go to Implementation lists for `IColumnType`, 160 of the 189 subtypes of `Expression` |
