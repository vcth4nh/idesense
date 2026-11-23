# spring-framework

- Repository: https://github.com/spring-projects/spring-framework
- Pin: tag `v7.0.9`, commit `82a6b40b9366ec181ededdad282b307ee5381a52`, committed 2026-08-14
- License: Apache-2.0 (`LICENSE.txt`)
- IDE: IntelliJ IDEA (port 29170)
- Build: Gradle 9.7.0 (wrapper), Kotlin 2.2.21. `buildSrc/.../JavaConventions.java` sets the
  Java toolchain 25 and the release 17 for each project. `.sdkmanrc` names `java=25-librca`.
  `settings.gradle` has no toolchain resolver.
- Gradle projects: 27 `include` lines in `settings.gradle`.
- Languages: 9,210 Java files, 388 Kotlin files, 17 Groovy files, 13 AspectJ files (`.aj`).
- Source sets that are not `main` or `test`: `testFixtures` in many projects, `jmh`, and the
  multi-release source sets `main/java21` and `main/java24` of `spring-core`.
- The checkout tracks one file below `.idea/`: `.idea/icon.svg`. Its `.gitignore` ignores the
  rest of `.idea`, and `.gradle` and `build`.
- The build has no lockfile. `framework-platform/framework-platform.gradle` pins each version
  with fixed BOMs. `dependencies.lock` in this folder holds the resolved modules (see "Setup").

## Requirements

The values in this section come from IntelliJ IDEA 2026.3 (IU-263.7307.200) on 2026-11-22.

### A JDK 25 from mise, for Gradle and for the Gradle JVM of the IDE

Gradle finds no JDK 25 that mise installed: the build has no toolchain resolver, and the
toolchain detection of Gradle does not read the mise folder. So Gradle must run on a JDK 25,
and then that JDK is the toolchain. `bootstrap.sh` installs `java@openjdk-25.0.2` with mise in
the user scope and sets no global version. `mise current java` in the checkout still gives the
default of mise (JDK 21): mise does not read `.sdkmanrc`.

The IDE takes the Gradle JVM from `.idea/gradle.xml`: `#GRADLE_LOCAL_JAVA_HOME` reads
`java.home` of `.gradle/config.properties` (`GradleLocalPropertiesFile`, `intellij.gradle.jar`).
`bootstrap.sh` writes that file at each run. The IDE log of the sync has "Instructing gradle to
use java from" the mise folder `openjdk-25.0.2`.

### No new entry in the JDK table

The modules need a JDK 25 (the toolchain of `JavaConventions.java`). The JDK table of the IDE
needs no entry by hand: the Gradle import finds the JDK and adds the entries itself.

- Gradle runs on the JDK of `java.home` in `.gradle/config.properties` (see above).
- After the Gradle part of the sync, the IDE looks for a local JDK 25 (`JdkAuto`, "Looking for a
  local SDK for JDK with name null"). Its list of local JDKs ("The following local JDKs were
  found") holds the JDKs of the mise folder, also the mise symlinks `openjdk-25` and
  `openjdk-25.0`. Then `UnknownMissingSdkFixLocal` logs "Automatically set Sdk
  SdkLookup{JDK, withVersionFilter} to" `~/.local/share/mise/installs/java/openjdk-25`, the first
  JDK 25 of that list. The IDE saves the table ("Saving global entities ... SdkEntity").
- After the open the table has two entries:
  - `25`, home `~/.local/share/mise/installs/java/openjdk-25` (a symlink of mise to
    `openjdk-25.0.2`), version "25.0.2".
  - `25 (2)`, home `~/.local/share/mise/installs/java/openjdk-25.0.2`, version "Oracle OpenJDK
    25.0.2". This home is the Gradle JVM. `idea.log` does not show which step adds this entry.
- 98 module files of the Gradle model name `25 (2)`, 33 name `25`; both point to the same JDK.
  The JDK classes of the `java21` and `java24` source sets resolve into `src.zip` of
  `openjdk-25.0.2` (`ClassFile`, `Thread.ofVirtual`). Why the import adds two names is not
  examined.

A fresh IDE on another machine needs mise and one run of `bootstrap.sh` before the first open.
The script installs `java@openjdk-25.0.2` and writes `.gradle/config.properties`. Evidence: the
fleet IntelliJ IDEA in `serverMode` and a windowed IntelliJ IDEA with a copy of the fleet
configuration both had no JDK 25 in the table before the open. Both added the two entries and
ended the sync with no error. Unlike `ideavim`, this product needs no entry before the first
open.

Not tested:

- An IDE with a new, empty configuration. Each tested IDE had a copy of the fleet configuration,
  with other JDKs in its table.
- A JDK 25 from another source than mise, and a machine where the IDE does not find the mise
  folder.
- An operating system other than Linux.

### The Mise plugin and `.idea/misc.xml`

The fleet IntelliJ IDEA has the plugin Mise (`com.github.l34130.mise`). At the first open it set
the project JDK to `openjdk-21 (mise)` in `.idea/misc.xml` (with `languageLevel="JDK_25"`). The
checkout does not track that file, so `git status --porcelain --untracked-files=no` stays
empty and `products.json` needs no `ideOwnedFiles`. The modules use their own JDK 25 (see
above). The JDK table gives the version "Oracle OpenJDK 21.0.2" for `openjdk-21 (mise)`. At
each open, `idea.log` has an INFO line of `ExternalJavaConfigurationService`: `.sdkmanrc` names
`25-librca`, and "Project JDK doesn't match (Oracle OpenJDK 21.0.2)". This line is no error:
it compares `.sdkmanrc` with the project JDK, and the modules do not use the project JDK. The
IDE also writes the ignored files `.idea/.name` (the project name `spring`),
`compiler.xml`, `kotlinc.xml`, `vcs.xml` and `workspace.xml`.

### The repack jars and the XJC classes

- `spring-core.gradle` repackages JavaPoet (`javapoetVersion = "0.10.0"`) and Objenesis
  (`objenesisVersion = "3.5"`) into `spring-core/build/libs/spring-javapoet-repack-0.10.0.jar`
  and `spring-objenesis-repack-3.5.jar`, and uses both jars as `api(files(...))`. Without them
  the IDE cannot resolve the packages `org.springframework.javapoet` and
  `org.springframework.objenesis`. `bootstrap.sh` runs `:spring-core:javapoetRepackJar` and
  `:spring-core:objenesisRepackJar`.
- `spring-oxm.gradle` generates JAXB classes from `src/test/schema` with the task `xjc` and adds
  the output folder `spring-oxm/build/generated/sources/xjc/java` as a test source root. This is
  the "pre-compile step" that the old `import-into-intellij-idea.md` of the product names.
  `bootstrap.sh` runs `:spring-oxm:xjc`. The Gradle sync of the IDE makes that folder a source
  root of `spring.spring-oxm.test`.

### The AspectJ files

The 13 `.aj` files of `spring-aspects` have the file type TEXT in IntelliJ IDEA 2026.3: the
editor shows plain text, `ide_file_structure` gives "No structure view available for language
'TEXT'", and `ide_find_class` finds no aspect. File search and text search find them. No row
needs a class of an `.aj` file.

### One `ide_restart` after the first good sync

After the first good Gradle sync of a new system folder, restart the IDE one time with
`ide_restart`, before the first harness switch (#276; the steps are in
[exposed/notes.md](../exposed/notes.md), "Setup step: one graceful restart after the first
sync"). Evidence on 2026-11-22: the restart wrote `external_build_system/modules/` (131 files)
and `project/` into `<system dir>/projects/spring-framework.<hash>/`. At the next start the IDE
loaded the workspace model from its cache ("Workspace model loaded from cache", 545 project
libraries) and started no sync.

The proof across a later harness switch (2026-11-22, plugin 2.1.1-dev.35): `--close-products`
closed the product, and the fleet IDE opened other products. Then a harness switch opened the
product again in a new IDE process. `idea.log` of that start has these facts:

- "Load workspace model from cache" for the project `spring`, and the initial load of 545
  project libraries.
- No line of the Gradle plugin (`#o.j.p.g.`) and no sync.
- The scan of the project: 540,348 files, 3 of them for indexing.
- The project was in smart mode 7 s after the start. Two short dumb modes came later: 61 ms at
  19 s (the 3 files), and 52 ms at 61 s (in each project of the IDE).

## Setup

Run `bootstrap.sh`. It needs mise.

- The script runs the Gradle wrapper on the JDK 25 of mise with `--no-daemon`,
  `--no-configuration-cache`, `--no-build-cache`, `--no-scan`, `--max-workers=4` and
  `-Xmx2g`. The build applies the Develocity plugin, which publishes a build scan only for an
  authenticated user; `--no-scan` keeps it off in each case.
- The init script `resolve-dependencies.init.gradle` adds the task `resolveDependenciesForIde`
  to each project. It resolves the external modules of the compile and runtime classpaths and of
  the Kotlin compiler plugins, and writes them to a list. It builds no project jar.
- The first run writes the sorted list to `dependencies.lock` (490 modules). A later run stops
  when its list differs. The repack inputs (JavaPoet, Objenesis) are not in the list: the
  versions in `spring-core.gradle` pin them.
- The script writes `.gradle/config.properties`, and `.idea/gradle.xml` and `.idea/misc.xml`
  when they are absent (the form that the IDE writes). It stops with an error when a tracked
  file changed.

Times and disk on 2026-11-22: the first run took 5 min 35 s (Gradle 9.7.0 download included).
It added `~/.gradle/caches/9.7.0` (500 MB), the wrapper distribution (164 MB),
`~/.gradle/caches/modules-2` +461 MB, and 245 MB of build output in the checkout. A second run
after the open of the product in the IDE took 19.4 s, gave the same module list, ended with
"spring-framework: ready" and changed no tracked file.

## The open in IntelliJ IDEA

Measured on 2026-11-22 with IntelliJ IDEA 2026.3 (IU-263.7307.200), plugin 2.1.1-dev.31, heap
limit 2 GB.

| IDE | Sync | Smart mode after the start |
|---|---|---|
| Windowed, copy of the fleet configuration, new system folder | 8 min 48 s | about 10 min 30 s |
| `serverMode` (fleet), first open | 33 s | 2 min 22 s |
| `serverMode` (fleet), after `ide_restart` | no sync (model from the cache) | 7 s |

- The windowed IDE downloaded 457 source jars in the sync. After a full GC it used 1.04 GB of
  heap, and its log has 2 lines "Low memory signal".
- The first open of the fleet IDE indexed 422,504 files in 82 s.

- No row pins a position in a compiled class. The fleet configuration has no key
  `decompiler.legal.notice.accepted`, so the text of a `.class` file is the stub of
  `ClsFileImpl` ("compiled code"), not the decompiler output. The definition of `ClassName` in
  the JavaPoet repack jar goes to line 7, column 20 of that stub. The text, and so the line and
  the column, depend on the decompiler consent. A user opens a `.class` file in an editor, and
  the IDE shows the legal notice of the decompiler. The button "Accept" writes the key
  (`IdeaDecompiler$LegalBurden.beforeFileOpened`, `java-decompiler.jar`). The key goes to the
  application `PropertiesComponent`, that is the component `PropertyService` in
  `options/other.xml` of the configuration folder (`AppPropertyService`,
  `intellij.platform.ide.impl.jar`). No tracked file controls that state. The jar is in the
  project (`spring-core/build/libs/`), so the harness keeps its relative path, and it drops the
  line and the column of each result in a `.class` file ("Path normalization" in
  `live-test/CONVENTIONS.md`). So the row `def-ClassName-into-javapoet-repack` compares the
  file, the name, the kind and the qualified name. `canary-usage-Objenesis-from-repack` also
  covers the repack jars.
- The canary rows and the sources of their targets:
  - `canary-def-Mono-into-reactor`: `Mono.java` of `reactor-core` 3.8.7 (sources jar).
    `framework-platform.gradle` imports `reactor-bom` 2025.0.7, and `dependencies.lock` has
    `io.projectreactor:reactor-core:3.8.7`. The harness keeps only the file name of a library
    path.
  - `canary-def-FlightType-into-xjc`: the XJC output of `spring-oxm` (see "Requirements").
  - `canary-usage-Objenesis-from-repack`: `SpringObjenesis implements Objenesis`. It resolves
    only with the Objenesis repack jar (version 3.5 in `spring-core.gradle`).
  - `canary-find-class-VirtualThreadDelegate`: two classes, in `main/java` and `main/java21`.
    Both source sets must be in the model.
- `def-Nullable-into-jspecify` goes to `Nullable.java` of JSpecify 1.0.0 (`dependencies.lock`).
- A product run of the 78 rows of the first sweep took 12 s to 19 s (plugin 2.1.1-dev.31). The
  first call of each hierarchy row after the open took at most 0.54 s. `ide_type_hierarchy` of
  `BeanPostProcessor` at the default depth took 2.45 s.
- The bless and the verify runs ran on plugin 2.1.1-dev.35. A run of all rows before the bless
  gave the same result as dev.31 for each of the 76 rows that both builds ran. The two verify
  runs of the 79 rows (72 compared, 7 parked) took 13 s and 12 s.
- The fixture rows with the product open: `java` 144 passed, `kotlin` 119 passed.

## Heap

The fleet IntelliJ IDEA (limit 2 GB) with the product next to the `java` and `kotlin` fixture
projects, 2026-11-22:

- After the first open and index: 1.61 GB in use, 0.60 GB after a full GC; RSS 5.3 GB.
- After the sweep and three product runs: 1.56 GB in use, 1.05 GB after a full GC; RSS 4.9 GB.
- 3 lines "Low memory signal received" from the open to the end of the runs. No
  `java.lang.OutOfMemoryError`, no index rebuild and no heap dump.

## Disk

The product on 2026-11-22, from the first bootstrap to the end of the runs:
`~/.gradle/caches/9.7.0` +591 MB, `~/.gradle/caches/modules-2` +686 MB, the wrapper
distribution +164 MB, the system folder of the fleet IntelliJ IDEA +676 MB, the build output in
the checkout +246 MB; about 2.4 GB. A windowed IDE for the window checks used 2.0 GB more in
its own folders, and these folders were removed after use.
