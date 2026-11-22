# exposed

- Repository: https://github.com/JetBrains/Exposed
- Pin: tag `1.5.0`, commit `84361204b6639cad5696506a26595c97afac3531`, committed 2026-08-26
- License: Apache-2.0 (`LICENSE.txt`)
- IDE: IntelliJ IDEA (port 29170)
- Build: Gradle 8.14.4 (wrapper), Kotlin 2.3.20, `jvmToolchain(17)` in each module
- Gradle projects: the root and 25 included projects of `settings.gradle.kts`, and `buildSrc`.
  `samples/` (6 builds) and `documentation-website/` (3 builds) have their own
  `settings.gradle.kts` and are not part of the root build. IntelliJ does not import them.
- Languages: 634 Kotlin files (about 132,000 lines) outside `samples/` and
  `documentation-website/`, and no Java file. `docs/api/` holds 4,335 HTML files of the Dokka
  output (126 MB).

## Setup

Run `bootstrap.sh`. It needs mise. It installs the JDK `temurin-17.0.21.1+2` with mise (user
scope, no global version), runs the Gradle wrapper on that JDK to resolve the dependencies,
and writes three files that git ignores. There is no lockfile to create: the version catalog
`gradle/libs.versions.toml` pins each dependency version, and it has no dynamic version.

- The JDK. Each module sets `jvmToolchain(17)`, and `settings.gradle.kts` has no toolchain
  resolver. Gradle does not detect a JDK that mise installed, except the JVM that runs Gradle
  ("Detected by: Current JVM" in `./gradlew javaToolchains`). With Gradle on JDK 17 the
  toolchain is that JDK. With Gradle on a JDK 21, the toolchain is a JDK 17 that Gradle
  downloaded for another build into `~/.gradle/jdks`, and with no such JDK the sync fails.
- `.gradle/config.properties` gets `java.home=<that JDK 17>`, and `.idea/gradle.xml` sets the
  Gradle JVM to `#GRADLE_LOCAL_JAVA_HOME`. IntelliJ reads `java.home` of
  `<project>/.gradle/config.properties` for this value (`GradleLocalPropertiesFile` and
  `GradleJvmGradleLocalJavaHomeResolver` in `intellij.gradle.jar`, IU-263.7307.200). The
  script writes this file at each run, because the path is a fact of the machine.
- `.idea/gradle.xml` links the root build. `.idea/misc.xml` keeps the module files in the
  system folder of the IDE (`ExternalStorageConfigurationManager`). The script writes these
  two files only when they are absent. The checkout tracks four other files in `.idea`
  (`detekt.xml`, `externalDependencies.xml`, `icon.svg`, `vcs.xml`), and its `.gitignore`
  ignores the rest of `.idea` and `.gradle/`.
- The Gradle run uses `--no-daemon` and `-Xmx1g`: the build sets no heap limit
  (`org.gradle.jvmargs=-Dfile.encoding=UTF-8`), and a Gradle process with no limit grew to
  3.4 GB here. `-Pkotlin.compiler.execution.strategy=in-process` compiles `buildSrc` with no
  Kotlin daemon.

Times on 2026-11-22: the first Gradle run took 6 min 25 s (Gradle 8.14.4 download, `buildSrc`,
the dependencies). A second bootstrap run takes 16 s.

## The Gradle project in IntelliJ

Seen on IntelliJ IDEA 2026.3 (IU-263.7307.200) in `serverMode`, plugin 2.1.1-dev.23 and
2.1.1-dev.24:

- Link and sync. `.idea/gradle.xml` links the root build. At the first open IntelliJ has no
  Gradle data for the project, so it starts a sync by itself (`idea.log`: `Gradle (exposed):
  Execution RESOLVE_PROJECT:0 is started`). A second IntelliJ with a window opened a copy of
  the pin with no `gradle.xml` and also started the sync by itself. After the sync IntelliJ
  writes the module list and `buildSrc` into `gradle.xml`, and `compiler.xml`, `misc.xml` and
  `workspace.xml` into `.idea`. Git ignores all of them.
- JDKs. IntelliJ adds the JDK of `java.home` to its JDK table and gives it to the modules: a
  definition of `java.util.UUID` goes to `src.zip` of that JDK 17. The project SDK is the JDK
  of `JAVA_HOME` in the environment of IntelliJ.
- Library sources. The first sync downloads the sources jar of each library (about 500 jars):
  the advanced setting "Download sources for project dependencies during the project import"
  (`gradle.download.sources`) is on by default (`plugin.xml` of `intellij.gradle.jar`,
  IU-263.7307.200). After the sync, `ide_find_definition` into a
  library gives the `.java` or `.kt` file of the sources jar. `ide_type_hierarchy`,
  `ide_call_hierarchy`, `ide_find_super_methods` and `ide_explain_symbol` give the `.class`
  file, as for the product `openrefine` (see `GROUND-TRUTH.md` of the product).
- Readiness. The harness reports the IDE ready before the sync ends (first open: ready after
  55 s, sync until 8 min 23 s). The canary rows cover it: after a switch the gate tries them
  again for the readiness time (900 s).
- Separate builds. `samples/` and `documentation-website/` are no Gradle modules. Their files
  are project files under the root, so `ide_find_file` and `ide_search_text` find them.

### Setup step: one graceful restart after the first sync

IntelliJ keeps the modules of a Gradle sync in its workspace model. It writes them to the
disk (`external_build_system/modules/` in `<system dir>/projects/exposed.<hash>/`) only at a
save of the project after the model commit. In `serverMode` no such save comes by itself, and
the harness stops IntelliJ with SIGTERM, which saves no project. Without the module files,
the next start removes the modules, and the product run gives `MISCONFIGURED`. Issue #276
tracks this defect of the harness.

So after the first Gradle sync of a new system folder (the first open of `exposed`, a new
IntelliJ version, a cleared system folder), restart IntelliJ one time gracefully before the
first harness switch:

1. Wait until the sync has ended (`idea.log`: `Gradle (exposed): Execution
   RESOLVE_PROJECT:<n> is finished`) and the IDE is smart.
2. Restart IntelliJ with `ide_restart`, or deploy a plugin build (a deploy uses
   `ide_restart`). Its exit path saves each project (`ApplicationImpl.exit` calls
   `saveAndCloseProjectsOnExit`, `lib/intellij.platform.ide.impl.jar`, IU-263.7307.200).
3. Check that `<system dir>/projects/exposed.<hash>/external_build_system/` holds `modules/`
   with 77 files and `project/`.

After that step the model survives a harness switch: two switches with SIGTERM kept the 77
files, and the canary rows resolved with no new sync (2.1.1-dev.24, 2026-11-22).

Facts behind the step, seen on IntelliJ IDEA 2026.3 (IU-263.7307.200):

- The only project save after a sync comes before the model commit (`idea.log`: `Saving
  Project(name=exposed, ...)` at 08:37:48.7, `External system: commit model` at 08:37:49.8).
  In 10 and in 14 minutes after a sync, `idea.log` has no later `Saving Project(name=exposed`
  entry, and `external_build_system/` holds only `project.dat`.
- A stop with SIGTERM saves nothing: `idea.log` goes from `Index dispose started` to `IDE
  SHUTDOWN` in less than 0.2 s, and no file of the project store changes.
- At the next start IntelliJ loads the model from the cache ("There are 417 libraries to
  load"), and then `Apply JPS storage (iml files)` removes the modules, because no module file
  is on the disk. No new sync starts. Then `ide_find_class` finds no project class and the two
  canary definitions fail. Seen after a harness switch and after a hard stop.
- The same with `ExternalStorageConfigurationManager` off: no `.iml` file came into `.idea`.
- In IntelliJ with a window, a save 54 s after the sync wrote the 77 module files.
- `ide_restart` at 10:49 saved the project at 10:49:04, and `modules/` and `project/` have
  that time.

To repair a lost model: open another product of IntelliJ (`--open-product openrefine`), move
`external_build_system`, `project-model-cache` and `cache-state.xml` out of
`<system dir>/projects/exposed.<hash>/`, and open `exposed` again. IntelliJ syncs again (8 to
47 s when the Gradle caches are full). Then do the setup step above.

## Measured

IntelliJ IDEA 2026.3 (IU-263.7307.200), `-Xmx2048m`, plugin 2.1.1-dev.23, 2026-11-22.

| Item | Value |
|---|---|
| Switch: stop IntelliJ, mark the projects, start, all projects listed | 11 to 22 s |
| Ready after the switch, first open (the sync still runs) | 55 s |
| First Gradle sync, with the download of the library sources | 8 min 23 s |
| First indexing: 43,178 files, after the sync 187,521 and 180,373 library files | 9 min 39 s from the start to smart mode |
| Gradle sync with full caches, after a repair | 8 to 47 s |
| Java fixture rows while `exposed` is open | 144 passed |
| Kotlin fixture rows while `exposed` is open | 119 passed |
| Resident memory of IntelliJ, two fixtures, before the switch | 2,668 MB |
| Resident memory of IntelliJ, two fixtures plus `exposed`, after the open | 3,893 MB (3,336 MB after a full collection) |
| Used heap after a full collection, after the open | 443 MB |
| Checkout after the bootstrap and the open, without `.git` | 143 MB |

The used heap stays far below 1200 MB (60% of the limit), so IntelliJ keeps `-Xmx2048m`.

## Import check

Done on 2026-11-22 with plugin 2.1.1-dev.23 on the fleet IntelliJ, after the first sync.

| Call | Result |
|---|---|
| `ide_find_class`, query `EntityClass` | the class `EntityClass`, `EntityClass.kt:30` of `exposed-dao` |
| `ide_find_definition`, `SQLLog.kt:17:35` | `LoggerFactory.java` in the sources jar of `slf4j-api` 2.0.9 |
| `ide_find_usages`, `Transactions.kt:131:9`, `pageSize` 100 | 100 usages, `totalCollected` 286, `hasMore` true |
| `ide_type_hierarchy`, `ColumnType.kt:33:11` (`IColumnType`) | 71 subtypes |
| `ide_file_structure`, `Table.kt` | a structure of 247 lines |

Comparison with IntelliJ itself. A second IntelliJ with a window opened a copy of the pin
that had no `gradle.xml`, so that IntelliJ made the project model by itself:

- Find Usages on `transaction` (`Transactions.kt:131:9`) shows 286 results. The tool gives
  286.
- Go to Implementation on `IColumnType` shows "Choose Implementation of IColumnType (71
  found)". `ide_type_hierarchy` gives 71 subtypes. `ide_find_implementations` gives 70: it
  leaves out the object expression at `IdTable.kt:163`.
- Find in Files for `OFFSET` (In Project, Match case, Words) shows 13 matches in 13 files.
  `ide_search_text` gives the same 13 lines, one in each file.
- The Callees view of `executeMultiple` (`JdbcPreparedStatementImpl.kt:57`) shows
  `execute()` and `getMoreResults(int)`. The tool gives the same two callees.

Project model facts that the probe rows rely on:

- The canary rows: a definition into the library `slf4j-api` (version catalog
  `gradle/libs.versions.toml`, the lockfile of this build), a definition from `exposed-jdbc`
  into `exposed-core`, and a type hierarchy into the library `spring-tx` (6.2.19).
- `src/main` and `src/test` are production and test roots of each Gradle source set, so the
  usage scopes `project_production_files` and `project_test_files` split the usages.
- The Kotlin outline of IntelliJ shows the supertype call of an object expression with its
  arguments, for example a string literal. These arguments are source text, so the structure
  row of `EntityTests.kt`, which has such objects, is a `shape` row.
