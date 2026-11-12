# openrefine

- Repository: https://github.com/OpenRefine/OpenRefine
- Pin: tag `3.10.1`, commit `bde8a36dc188f7846aeafc2910969e7d0fbc8e7c`, committed 2026-02-26
- License: BSD-3-Clause
- IDE: IntelliJ IDEA (port 29170)
- Language level: Java 11 (`java.minversion`), Maven builds with a JDK 11 to 21
- Maven modules: `modules/core`, `modules/grel`, `main`, `server`, `extensions` (7
  extensions), `packaging`, `benchmark`. IntelliJ reports 12 modules.

## Setup

Run `bootstrap.sh`. It needs Maven 3.9 or later and a JDK 11 to 21 for Maven. It takes
`mvn` from the `PATH`, else the newest Maven 3.9 that the Maven Wrapper has put in
`~/.m2/wrapper/dists`. Then it runs `mvn dependency:go-offline generate-sources`, gets one
sources jar (see the last item), and writes `.idea/misc.xml` when it is absent. There is no
lockfile to create: the POMs pin each dependency version and each plugin version, and no
POM has a version range.

- `generate-sources` is necessary. The localizer plugin writes Java classes into
  `target/generated-sources` (for example `FunctionDescription` and `OpenRefineMessage`),
  and about 300 source files use them. The build stops before `process-sources`: there a
  plugin sorts the imports of the tracked sources.
- `misc.xml` names the root POM in `MavenProjectsManager`. At the first open IntelliJ finds
  no Maven tree for this file and starts a full Maven sync. The module files go to the
  system folder of the IDE (`ExternalStorageConfigurationManager`), not into the checkout.
  The project SDK is the IDE JDK with the name `21`. The checkout tracks only
  `.idea/codeStyles`.
- Library sources. After each Maven sync, IntelliJ downloads the sources jar of each
  library: `MavenDownloadLibrarySourcesSyncListener.importFinished` starts the download when
  `MavenImportingSettings.isDownloadSourcesAutomatically()` is true, and the constructor of
  `MavenImportingSettings` sets it to true (bytecode of `intellij.maven.jar`, 262.8665). The
  setting is "Automatically download: Sources" in Settings > Build Tools > Maven > Importing.
  Until a sources jar is there, `ide_find_definition` into that library gives the `.class`
  file, and after it the `.java` file. So the bootstrap gets the sources jars that the
  expected rows name: `com.fasterxml.jackson.core:jackson-databind:<jackson.version>:sources`
  (2.20.1 at the pin), with `dependency:get` outside the checkout. Do not use
  `dependency:sources`: it resolves the sibling modules from the snapshot repository of the
  project and puts newer snapshot jars of `org.openrefine` into `~/.m2`.
- The other library files in the expected rows come from `ide_call_hierarchy` and
  `ide_type_hierarchy` (the JDK, `javax.servlet-api`, `jetty-server`). These tools give the
  `.class` file also when the sources jar is there, so a sources download does not change
  them.

Times on 2026-11-12: the first bootstrap ran `go-offline` in 394 s (about 340 MB into
`~/.m2`) and `generate-sources` in 135 s. A second run takes 6 to 8 s.

## Measured

IntelliJ IDEA 2026.2 (IU-262.8665.337), `-Xmx2048m`, plugin 2.1.1-dev.12, 2026-11-12.

| Item | Value |
|---|---|
| Switch: stop IntelliJ, mark the projects, start, all projects listed | 11 s |
| Ready after the switch, first open | 30 s |
| First Maven sync at the open | 17 s |
| First indexing: 48,725 files, then 27,424 files | 33 s from project open to smart mode |
| Library sources that IntelliJ downloads after the first open | about 142 jars in 5 minutes |
| Java fixture rows while `openrefine` is open | 142 passed |
| Kotlin fixture rows while `openrefine` is open | 117 passed |
| Resident memory of IntelliJ, two fixtures, before the switch | 3446 MB |
| Resident memory of IntelliJ, two fixtures plus `openrefine`, after the open | 3301 MB |
| Used heap after a full collection, after the open | 367 MB |

The used heap stays far below 1200 MB (60% of the limit), so IntelliJ keeps `-Xmx2048m`.

Facts about the switch:

- A second open takes 11 s for the switch and 15 s to readiness. IntelliJ scans the
  project again and indexes about 13,500 files.
- IntelliJ runs a full Maven sync at each open (8 s): the log says "MavenProjectsTree is
  inconsistent". IntelliJ writes no file into `.idea` of the checkout.
- IntelliJ reports smart mode for about 7 s at its start, before the Maven sync makes it
  dumb again. The index status alone is not a safe readiness signal. The canary gate covers
  it: after a switch it tries the canary rows again until the readiness time is used. In
  dumb mode, `ide_file_structure` gives a Java outline with no types and no error (#174).

## Import check

Done on 2026-11-12 with plugin 2.1.1-dev.12. The product is accepted.

| Call | Result |
|---|---|
| `ide_find_class`, query `Command` | the class `Command`, `Command.java:66` of `modules/core` |
| `ide_find_definition`, `PreviewExpressionCommand.java:231:41` | `ObjectNode.java` in the sources jar of `jackson-databind` 2.20.1 |
| `ide_find_usages`, `Project.java:67:14`, `pageSize` 100 | 100 usages, `totalCollected` 500 (the cap), `truncated` true |
| `ide_type_hierarchy`, `Command.java:66:23` | 99 subtypes |
| `ide_file_structure`, `Project.java` | a structure of 27 lines |

Comparison with IntelliJ itself. A second IntelliJ with a window opened a copy of the pin
that had no `.idea` folder, so that IntelliJ made the project model by itself:

- The tools give the same results on that import and on the fleet project with the written
  `misc.xml`: 12 calls of class search, symbol search, definitions into a dependency,
  usages, type hierarchies and file structure.
- Go to Implementation on `Command` shows "Choose Implementation of Command (99 found)".
  The tool gives 99 subtypes.
- Find Usages on the generated class `OpenRefineMessage` shows 14 results. The tool gives 14.
- Find Usages on `Project` shows 1,408 results. The tool stops at its cap of 500.

Project model facts that the probe rows rely on:

- The generated sources are source roots: a definition of `FunctionDescription` or
  `OpenRefineMessage` goes to `target/generated-sources` of its module.
- `main/src` and `main/tests/server/src` are a production root and a test root of the
  module `main`, so the usage scopes `project_production_files` and `project_test_files`
  split the usages.
- A definition into a library gives a `.class` file until IntelliJ has downloaded the
  sources jar of that library, and a `.java` file after it. The bootstrap gets the sources
  jar of jackson-databind, the only library of the definition rows.
- The Java outline of IntelliJ shows field initializers, which are source text, so the
  structure rows of Java files with initialized fields are `shape` rows.
  The structure of `ImportingUtilities.java` also has annotation remnants in its modifiers (#173).
