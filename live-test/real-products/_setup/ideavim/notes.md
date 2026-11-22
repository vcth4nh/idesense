# ideavim

- Repository: https://github.com/JetBrains/ideavim
- Pin: tag `2.46.0`, commit `4792d0e9f2a790d4ed4f0697a8565d08dbeebc1b`, committed 2026-08-18
- License: MIT (`LICENSE.txt`)
- IDE: IntelliJ IDEA (port 29170)
- Build: Gradle 9.6.1 (wrapper), Kotlin 2.3.20, IntelliJ Platform Gradle Plugin 2.16.0,
  `ideaVersion=2026.1` and `javaVersion=21` in `gradle.properties`. Each module sets a Java 21
  toolchain.
- Gradle projects: 23. Three ANTLR grammars (`.g4`). `vim-engine` generates its Vimscript
  parser into `vim-engine/build/generated-src/antlr/main`, a source root of the module.
- Languages: 1,969 Kotlin files (292,215 lines) and 14 Java source files (3,001 lines; 12 of
  them in the root module). `.idea/fileTemplates` has 2 more Java files. 12 tracked KSP output
  files (JSON) are in `*/src/main/resources/ksp-generated/`.
- The checkout tracks `.idea/gradle.xml` and `.idea/misc.xml`. Both name a JDK (see
  "Requirements").

## Requirements

The values in this section come from IntelliJ IDEA 2026.3 (IU-263.7307.200) on 2026-11-22.

### A JetBrains Runtime 21 in `~/.jdks/jbr-21*`

The tracked `.idea/gradle.xml` sets the Gradle JVM `jbr-21`. The IDE looks for a JDK with this
name (`JdkAuto`: "Looking for a local SDK for JDK with name jbr-21", the requirement
`jbr && it >= 21`). It finds a JetBrains Runtime 21 in `~/.jdks` and adds it with that name
(`idea.log`: "Adding SDK: jbr-21 JavaSDK", "Automatically set Sdk SdkLookup{JDK, name=jbr-21,
...} to ~/.jdks/jbr-21.0.11").

How a machine gets it: an IDE with a window offers the download. When no local JDK meets the
requirement, the first open shows the dialog "Download SDK? IntelliJ IDEA 2026.3 wants to
download JetBrains Runtime 21.0.11 (230 MB)". "Download" installs it into
`~/.jdks/jbr-21.0.11` (320 MB on the disk). `bootstrap.sh` stops with an error when no folder
`~/.jdks/jbr-21*` exists.

While that download runs, a save can write an empty Gradle JVM into the tracked `gradle.xml`
(`<option name="gradleJvm" />`). For a `gradleJvm` name that is not in the JDK table, the IDE
sets the value to null before the lookup, and sets the found name after it
(`GradleProjectSettingsUpdater$Util.fixupUnknownSdk`, `intellij.gradle.jar`, IU-263.7307.200).
The next save after the sync writes `jbr-21` again. With the JDK already in `~/.jdks`, the
lookup ends in less than 3 s.

### A JDK `jbr-21` in the JDK table of a `serverMode` IDE before its first open

The IDE in `serverMode` needs an entry with the name `jbr-21` in `options/jdk.table.xml` of its
configuration folder before the first open of the product. Without it the Gradle sync failed
two times, at the first open and after a restart. The log of each start has the same order:

1. "Looking for a local SDK for JDK with name jbr-21"
2. "Adding SDK: jbr-21 JavaSDK" and "Automatically set Sdk SdkLookup{JDK, name=jbr-21, ...} to
   ~/.jdks/jbr-21.0.11"
3. 4 s to 5 s later: "Gradle JVM (jbr-21) isn't resolved: ...SdkLookupProvider$SdkInfo$Undefined"
   (`LocalGradleExecutionAware`), and "Gradle (ideavim): Execution RESOLVE_PROJECT:<n> is
   failed", 38 ms to 67 ms after the start of the sync.

The IDE then starts no other sync, and the product has no Kotlin module. A restart does not
help: the JDK table does not keep the added SDK from one start to the next. This is a reading
of `idea.log`. The cause inside the IDE is not established (no bytecode check).

How to add the entry: an IDE with a window writes it. A windowed IntelliJ IDEA with the same
configuration added `jbr-21` at the open and saved it into `options/jdk.table.xml` after its
sync ("Saving global entities ... SdkEntity to files"). Copy that `<jdk>` element (name
`jbr-21`, home `$USER_HOME$/.jdks/jbr-21.0.11`, 69 class roots, 69 source roots) into
`options/jdk.table.xml` of the `serverMode` IDE while that IDE is down. Keep a backup of the
file. With the entry, the sync worked at the next start: 25 s, on `~/.jdks/jbr-21.0.11`.

With no JDK in `~/.jdks`, a `serverMode` IDE is not tested.

### `.idea/misc.xml` in `ideOwnedFiles`

`products.json` lists `.idea/misc.xml` in `ideOwnedFiles`. A run accepts a change of this file
and prints "IDE-owned file differs from the pin: .idea/misc.xml".

The reason: the fleet IntelliJ IDEA has the plugin Mise (`com.github.l34130.mise` 6.0.2). At
the first open it set the project JDK to `openjdk-21 (mise)` and so rewrote the tracked file
(`project-jdk-name="corretto-21"` became `"openjdk-21 (mise)"`). Its `postStartupActivity`
`MiseProjectJdkSetup` calls `ProjectRootManager.setProjectSdk` (`mise-6.0.2.jar`). A restart
did not write the file again.

In a windowed IntelliJ IDEA with the same plugins, the plugin did not set the project JDK (the
reason is not known). There `misc.xml` keeps the project JDK `corretto-21`, and no local JDK
met the requirement `corretto && it >= 21`. The IDE shows the editor banner "JDK "corretto-21"
is missing" with a download link, and no dialog. The file stays unchanged, and the modules get
the JetBrains Runtime: the definition of `java.awt.Color` goes to `src.zip` of
`~/.jdks/jbr-21.0.11`. An IDE with no Mise plugin is not tested.

### The Maven project `.teamcity/pom.xml`

The tracked `misc.xml` links `.teamcity/pom.xml` (the TeamCity build configuration in Kotlin
DSL) as a Maven project. At each open the IDE imports it as the module `IdeaVim_dsl`
(`MavenProjectsManager.onProjectStartup`) and starts a Maven server. The pom names the
repository `https://ideavim.teamcity.com/app/dsl-plugins-repository`, the TeamCity server of
the product. So the Maven server of the IDE can contact the server of the product:

- Windowed IDE, first open with an empty Maven cache: the Maven server
  (`RemoteMavenServer36`) had connections to that server (port 443) for 8 min 14 s. It wrote
  1,701 files (17.7 MB) into `~/.m2/repository`, 1,114 of them below `org/jetbrains/teamcity`.
- `serverMode` IDE: the import took 2.5 s, and the call to the Maven server failed
  (`java.rmi.UnmarshalException`). No connection to the server of the product was open after
  the import, and `~/.m2` got no new file.

The setup does not unlink this project: the link is in a tracked file. No row uses the module
`IdeaVim_dsl`, and no row names a file below `.teamcity/`.

### One `ide_restart` after the first good sync

After the first good Gradle sync of a new system folder, restart the IDE one time with
`ide_restart`, before the first harness switch (#276; the steps are in
[exposed/notes.md](../exposed/notes.md), "Setup step: one graceful restart after the first
sync"). The sync has ended when `idea.log` has "Gradle (ideavim): Execution
RESOLVE_PROJECT:<n> is finished" with no "is failed" before it.

Evidence on 2026-11-22: the restart wrote `external_build_system/modules/` (70 files) and
`project/` into `<system dir>/projects/ideavim.<hash>/`. At the next start the IDE loaded the
workspace model from its cache ("Workspace model loaded from cache"), started no sync, and its
scans ended 16 s after the restart call. The rows ran with no new sync.

## Setup

Run `bootstrap.sh`. It needs mise and a JetBrains Runtime 21 in `~/.jdks` (see
"Requirements").

- The JDK of Gradle. The root `build.gradle.kts` stops the build unless Gradle runs on a JDK 21
  (`currentJavaVersion != javaVersion`). The script installs `openjdk-21.0.2` with mise (user
  scope, no global version) and runs the Gradle wrapper on it.
- The script runs the init script `resolve-dependencies.init.gradle`, which resolves the
  external modules of the compile and runtime classpaths and of the Kotlin compiler plugins,
  and `:vim-engine:generateGrammarSource`. It builds no project jar and runs no KSP task: the
  KSP tasks write the tracked files of `ksp-generated/`. The ANTLR output is the same after a
  second run (`--rerun`, SHA-256 of the 20 files).
- The IntelliJ Platform Gradle Plugin downloads IntelliJ IDEA 2026.1 two times and extracts
  both into `~/.gradle/caches/9.6.1/transforms`: the installer for 12 projects, and the Maven
  archive for `tests/long-running-tests` and `tests/property-tests` (`useInstaller = false`).
- `--no-daemon` and `-Xmx2g`: `gradle.properties` sets no heap limit.
- The script changes no tracked file. It compares the tracked files before the Gradle run with
  the tracked files after it, because an IDE can already have changed `.idea/misc.xml` (see
  "Requirements"). It stops with an error when the Gradle run changed a tracked file.

Times and disk on 2026-11-22: the first run took 11 min 42 s and added 9.9 GB to the disk
(`~/.gradle/caches/9.6.1` +8,549 MB, `~/.gradle/caches/modules-2` +1,916 MB). A second run of
`generateGrammarSource` took 1 min. A run after the open of the product in the IDE (with the
changed `misc.xml`) took 14.7 s, ended with "ideavim: ready", and changed no tracked file.

## The open in IntelliJ IDEA

Measured on 2026-11-22 with IntelliJ IDEA 2026.3 (IU-263.7307.200), plugin 2.1.1-dev.31, heap
limit 2 GB.

| IDE | Sync | Index and smart mode |
|---|---|---|
| Windowed, first open: empty Maven cache, no JetBrains Runtime 21 | 9 min 31 s | not measured |
| Windowed, new system folder, warm caches | 16 s | smart 2 min 9 s after the start; 2 lines "Low memory signal received (gc overloaded: false)" during the index; 1.31 GB heap in use after the index |
| `serverMode` (fleet), with the `jbr-21` entry | 25 s | index of the new modules 78.8 s (`UnindexedFilesIndexer`); smart 2 min 10 s after the start |

- The fleet configuration has no key `decompiler.legal.notice.accepted`. Without it, the text
  of a library `.class` file is the stub of `ClsFileImpl.decompile` ("compiled code"), not the
  decompiler output (`IdeaDecompiler.getText`, `java-decompiler.jar`, IU-263.7307.200).
- A product run of the 67 rows (7 of them parked) takes 10 s to 11 s. The parked row
  `find-class-AnAction-libraries-scope` gives `internal_error` at each run (#316). The IDE does
  not log each such failure: the product runs with this row wrote no SEVERE line, and direct
  calls with other queries wrote some entries of 6 SEVERE lines each. The rule of the IDE
  logger is not established.
- The fixture rows with the product open (2026-11-22): `java` 144 passed, `kotlin` 119 passed.

## Heap

The fleet IntelliJ IDEA (limit 2 GB) with the product next to the `java` and `kotlin` fixture
projects, 2026-11-22:

- 1.44 GB in use after the first sweep of the rows, 1.12 GB after a full GC; RSS 5.0 GB.
- The callers of `offsetToBufferPosition` at depth 2 took 93.45 s and gave 73,726 bytes. All 21
  lines "Low memory signal received" of that session came during this one call. That row is
  not in the suite. Depth 1 takes 0.9 s.
- One more line "Low memory signal received (gc overloaded: false)" came during the bless run.
  After it the heap had 1.86 GB in use, 1.05 GB of it in the young generation; RSS 5.3 GB.
- No `java.lang.OutOfMemoryError`, no index rebuild and no heap dump.

## Disk

The product on 2026-11-22, from the first bootstrap to the bless: `~/.gradle/caches/9.6.1`
+8,738 MB, `~/.gradle/caches/modules-2` +2,309 MB, `~/.m2` +112 MB, `~/.jdks` +320 MB, the
system folder of the fleet IntelliJ IDEA +1,114 MB, the checkout 90 MB; about 12.7 GB.
