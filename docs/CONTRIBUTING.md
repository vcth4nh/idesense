# Contributing

How to build, test, change and release the IdeSense plugin. This file is for each maintainer,
human or agent. The goal, the scope and the design principles are in
[PRINCIPLES.md](PRINCIPLES.md). The mechanisms and the platform contracts are in
[ARCHITECTURE.md](ARCHITECTURE.md). The rules for an agent are in [AGENTS.md](../AGENTS.md).

## Doc ownership (where each topic lives)

Each fact has one home: the file of its reader. The map of the documents by reader is the table
"Where things live" in [AGENTS.md](../AGENTS.md). This file is the home of the process: build,
test, dev builds, dependencies, CI, issues, pull requests and release.

## Technology stack

Each version is in the file that this list names. Do not copy a version into a doc.

- **Language**: Kotlin on the JVM toolchain of `jvmToolchain` in `build.gradle.kts`.
- **Build**: Gradle with the Kotlin DSL. The wrapper version is in
  `gradle/wrapper/gradle-wrapper.properties` and in `gradleVersion` of `gradle.properties`.
- **Libraries and Gradle plugins**: `gradle/libs.versions.toml`.
- **IntelliJ Platform**: the build compiles against `platformType` and `platformVersion`, and
  the lowest IDE build is `pluginSinceBuild` (all in `gradle.properties`). The Plugin Verifier
  IDEs are in `pluginVerification` of `build.gradle.kts`.
- **HTTP server**: an embedded Ktor CIO server on a configurable port.
- **Protocol**: Model Context Protocol (MCP). The server negotiates the versions in
  `SUPPORTED_PROTOCOL_VERSIONS` of `McpConstants.kt`.

## Build and run

```bash
./gradlew buildPlugin                        # plugin zip: build/distributions/idesense-<version>.zip
./gradlew runIde                             # a sandbox IDE with the plugin
./gradlew test                               # all tests: the unit tests and the platform tests
./gradlew test --tests "*UnitTest*"          # the unit tests only
./gradlew test --tests "McpPluginUnitTest"   # one test class
./gradlew compileTestKotlin                  # compile all tests, run none
./gradlew check                              # all tests (the CI Test job)
./gradlew verifyPlugin                       # plugin structure and the Plugin Verifier
```

The run configurations in `.run/` start the same tasks: **Run Plugin** (`runIde`), **Run Tests**
(`check`, so also the platform tests) and **Run Verifications** (`verifyPlugin`).
`gradle.properties` turns on the build cache and the configuration cache.

## Dev builds

The plugin is not dynamically reloadable. Each code change needs a build, an install and an IDE
restart:

```
edit → ./gradlew buildPlugin -PpluginVersion=<version>-dev.NN → install → IDE restart
     → check serverInfo.version → live-test run → compare
```

- **Give the version on the command line.** Only the version tells one build from another:
  `serverInfo.version`, the jar name on the disk and `idea.log` show the version of a build and
  nothing else. So each build that goes into an IDE needs a new version. A `-P` property
  overrides `gradle.properties`, so no dev version lands on a branch. `pluginVersion` in
  `gradle.properties` changes only at a release.
- **`<version>` is the next patch version.** When `pluginVersion` is `X.Y.Z`, the dev builds are
  `X.Y.(Z+1)-dev.NN`.
- **`NN` is higher than each build that an IDE has or that is on the disk.** Read the version of
  each IDE and the zip names in `build/distributions/` of each checkout and worktree.
- **Prove the running build.** Read `serverInfo.version` after each restart (see
  [live-test/README.md](../live-test/README.md#prove-which-build-runs), "Prove which build runs").
- **Deploy.** The tools `ide_install_plugin` and `ide_restart` are off by default. The steps,
  the zip containment rule and the ports are in [live-test/README.md](../live-test/README.md),
  "Deploy a build to the IDEs".

## Add a tool

A tool class extends `AbstractMcpTool` and implements `doExecute()`, not `execute()`. The package
map and the backing mechanisms are in [ARCHITECTURE.md](ARCHITECTURE.md). A new tool must be in
the scope, and its result follows the design principles ([PRINCIPLES.md](PRINCIPLES.md)). The
principle "Text for the calling agent" is the rule for the text of `notes`, `warnings` and errors.

### Files that change together

The unit tests and one platform test pin the tool set. A new tool changes all of these files in
one pull request. The main paths start at `src/main/kotlin/com/github/vcth4nh/idesense/`, and the
test classes are in `src/test/kotlin/`.

| File | Change |
|---|---|
| `constants/ToolNames.kt` | A `const val`, and the name in `ALL`. `ALL` stays sorted (`ConstantsUnitTest`). |
| `tools/ToolRegistry.kt` | `register(...)` in `registerUniversalTools()`, or a `ConditionalTool` entry for a tool that needs a language provider. |
| `settings/McpSettings.kt` | The name in the default `disabledTools`, only for an opt-in tool. |
| `constants/ParamNames.kt` | Each new parameter name. |
| `docs/USAGE.md` | A `### ide_<name>` section with a parameter table. The table lists each schema property except `project_path`. Also a line in "Table of Contents" and a row in "Tool Availability by IDE". |
| `README.md` | A row in the tool table. Required for a tool that is on by default. |
| `docs/ARCHITECTURE.md` | A row in "Tool → backing mechanism". |
| `src/main/resources/skill/idesense/SKILL.md` | The name in the `TRIGGER` list of the front matter. The list holds exactly the tools that are on by default. |
| `src/main/resources/skill/idesense/references/tools-reference.md` | A `### ide_<name>` section with a "Returns" block. Required for a tool that is on by default. |
| `DocsDriftUnitTest` | The tool count in `testCanonicalCounts`, the instance in `allToolInstances()`, and the default-disabled set. |
| `ConstantsUnitTest` | The constant, and the list in `testToolNamesAllContainsEveryConstant`. |
| `ToolsUnitTest` | A schema test and a registration test. |
| `ToolExecutionIntegrationTest` | The name in `expectedTools` of `testAllToolsRegistered`. This is a platform test, so the filter for the unit tests does not run it. |
| `CHANGELOG.md` | An entry under `## [Unreleased]`. |
| `live-test/fixtures/_snapshots/<lang>/` | Input rows and expected rows for each language. See "Workflow for adding new probes" in [CONVENTIONS.md](../live-test/CONVENTIONS.md). |

### Input schema

Each tool builds its input schema with `SchemaBuilder` (`tools/schema/SchemaBuilder.kt`):

```kotlin
override val inputSchema = SchemaBuilder.tool()
    .projectPath()
    .file()
    .lineAndColumn()
    .intProperty("maxResults", "Maximum results to return. Default: 100, max: 500.")
    .enumProperty("matchMode", "How to match the query.", listOf("substring", "prefix", "exact"))
    .build()
```

For a property that the builder does not cover, use `.property(name, buildJsonObject { ... })`.

### PSI sync

`AbstractMcpTool.execute()` refreshes the VFS and commits the documents before `doExecute()`
only under two conditions: `requiresPsiSync` is `true` (the default), and the user turned on
`syncExternalChanges` (off by default). A tool that reads no PSI sets
`override val requiresPsiSync: Boolean = false`, as `GetIndexStatusTool` does.

## Response models

The result classes are in `tools/models/` (`ToolModels.kt`, `StructureModels.kt`). The result
JSON encodes default values, also a `null` (see "Platform Contracts and Traps" in
[ARCHITECTURE.md](ARCHITECTURE.md)).

A fixture row and an `exact` or `ordered` product row compare the whole normalized result (see
"Compare modes" in [CONVENTIONS.md](../live-test/CONVENTIONS.md)). Thus a new nullable field with
the default `null` adds `"<field>":null` to each such row of each tool that returns the class.
Each of these rows then needs a bless. For example, each `ide_find_usages` fixture row that is no
error holds the key `warnings`, in most rows as `"warnings":null`.

For a new optional field, follow "The JSON of a result encodes defaults" in "Platform Contracts
and Traps" of [ARCHITECTURE.md](ARCHITECTURE.md#platform-contracts-and-traps). Then only the rows
that get a value change. The docs drift test does not check result fields:
update the "Returns" blocks of `tools-reference.md` and the result descriptions of `USAGE.md`
by hand.

## Dependencies

Add a library to `gradle/libs.versions.toml`, and reference it in `build.gradle.kts` as
`libs.<name>`. The build files encode these rules. The table names the file that holds the
reason of each rule.

| Rule | Reason in |
|---|---|
| The plugin bundles no kotlinx-coroutines, because it must run on the coroutines of the IDE. Each Ktor and mockk dependency excludes the coroutines modules by name. A new dependency that pulls coroutines gets the same excludes. | `.github/dependabot.yml` (comment of the `io.ktor` rule); the excludes in `build.gradle.kts` |
| Ktor stays below the first version that needs a newer kotlinx-coroutines than the IDEs bundle. Lift the ignore rule when the coroutines of the platform catch up. | `.github/dependabot.yml`, ignore rule `io.ktor:*` |
| The IntelliJ Platform Gradle Plugin is pinned. Lift the version pin and the Dependabot ignore rule together. | `gradle/libs.versions.toml` (`intelliJPlatform`); `.github/dependabot.yml` |
| The Kotlin plugins change together, in the Dependabot group `kotlin`. A manual bump changes `kotlin` and `kotlinSerialization` together. | `.github/dependabot.yml`, group `kotlin` |
| A Gradle wrapper bump also changes `gradleVersion` in `gradle.properties`. `tasks.wrapper` reads this property, so with the old value the next `./gradlew wrapper` writes the old wrapper again. A Dependabot wrapper pull request does not change the property. | `build.gradle.kts`, `tasks.wrapper` |
| `verifyPlugin` fails only on compatibility problems (`failureLevel`). The hierarchy tools use internal API on purpose (open as #74). Keep this pin when you lift the pin of the IntelliJ Platform Gradle Plugin. | `build.gradle.kts`, `pluginVerification` |

Judge a dependency by its resolved version, not by the catalog. A transitive dependency can raise
a version above the catalog value:

```bash
./gradlew dependencyInsight --configuration runtimeClasspath --dependency <group>:<name>
```

To see what the plugin ships, list the zip: `unzip -l build/distributions/idesense-<version>.zip`.
The zip must hold no `kotlinx-coroutines` jar.

## Tests

### Test kinds

| Kind | Class name | Base class | Use for |
|---|---|---|---|
| Unit test | `*UnitTest` | `junit.framework.TestCase` | Serialization, schemas, data classes, registries, pure logic. No platform start. |
| Platform test | `*Test` | `BasePlatformTestCase` | A `project`, PSI, indexes, tool execution, project services. |

The class name selects the test filter, so a class name must agree with its base class. A unit
test starts no IntelliJ application. A test of a function that reads an extension point or gets
a service needs the application, so it is a platform test, also when it works with mocks. Both
kinds run on a development machine and in CI (`./gradlew check`). A platform test starts the
IntelliJ Platform inside the test process. The MCP server does not start in a test
(`McpServerService.initialize`). A platform test creates its source files in the test
(`myFixture.addFileToProject`).

**The light fixture has an in-memory VFS.** A platform test cannot assert a tool-level result
that needs a real file (for example `isError: false` for a file argument). Test the changed seam
directly, and leave the shape of the tool result to the live suite (see
`testFindUsagesSurfacesHandlerStageDegradationAsWarnings` in `ToolExecutionIntegrationTest`).
To make a platform extension fail in a test, register a test extension in the first position:

```kotlin
FindUsagesHandlerFactory.EP_NAME.getPoint(project)
    .registerExtension(throwingFactory, LoadingOrder.FIRST, testRootDisposable)
```

### Editing docs

`DocsDriftUnitTest` pins five docs to facts from the code: `README.md`, `docs/USAGE.md`,
`docs/ARCHITECTURE.md`, `SKILL.md` and `tools-reference.md`. It checks these facts:

- The tool count of `ToolNames.ALL`, and the default-disabled set of `McpSettings`.
- One `ide_*` section in `USAGE.md` for each tool. Its parameter table lists each schema
  property (`project_path` can be absent: it has a section of its own) and no other name,
  except the pagination names `limit`, `maxResults` and `cursor`.
- One row for each tool in the mechanism table of `ARCHITECTURE.md`.
- For each tool that is on by default: a `README.md` table row and a `tools-reference.md`
  section with "Returns". These two files name no unknown tool.
- The tool names in the `SKILL.md` front matter: exactly the tools that are on by default.

The test also checks `CHANGELOG.md`: each version heading exists one time (see "Traps" in
"Release").

The test does not check result field names, enum values, required flags, the language support
of a tool, or prose. Check these by hand against the classes in `tools/models/` and the schemas.

The test reads the documents at run time. The build declares the four documents outside
`src/` (`README.md`, `CHANGELOG.md`, `docs/USAGE.md` and `docs/ARCHITECTURE.md`) as inputs of the
`test` task (`pinnedDocs` in `build.gradle.kts`), and the skill files are inputs as resources. So
an edit of one of these documents runs the test again:

```bash
./gradlew test --tests "*DocsDriftUnitTest*"
```

Read the result in `build/test-results/test/TEST-*DocsDriftUnitTest.xml`
(`failures="0" errors="0"`).

After an edit of a tool description, run all unit tests. `ToolsUnitTest` asserts words of some
descriptions.

### See a new test fail first

A new test must fail on the old code first. Write the test before the correction, and run its
class (`./gradlew test --tests "<TestClass>"`). Make sure that the failed line is the intended
assertion. Then make the correction, and run the class again.

### A CI Test job that hangs

When the Test job stops at `> Task :test` with no output, a test thread waits forever. Get the
thread dumps before you stop a process: a kill first leaves a dead process with no stack. On a
test branch, add a temporary step that starts `./gradlew check` in the background, waits, and
then runs `jstack` for each JVM that `jps` lists. Also collect `free -m` and each
`hs_err_pid*.log` file. Open a draft pull request for the test branch. A push to a branch with
no pull request starts no Build run.

### Live tests

The live-test harness runs the tools against running IDEs and compares the results with blessed
snapshots. CI does not run it. For a change of tool behavior and for a release, run both suites
(`./live-test/run.py --suite all`): see "Run the suites against a new build" in
[live-test/README.md](../live-test/README.md). The commands, the deploy and the bless rules are
in that file and in [live-test/AGENTS.md](../live-test/AGENTS.md).

After a live run, read `idea.log` of each IDE (see "A defect that no row shows" in
[live-test/README.md](../live-test/README.md#troubleshooting)).

## Evidence for a platform claim

A claim about the IntelliJ Platform, a language plugin or an IDE needs evidence (see "Cite, do
not assert" in [AGENTS.md](../AGENTS.md)). Get the evidence in one of these ways:

- **Source.** Read `JetBrains/intellij-community` at the tag of the IDE build. For IntelliJ IDEA
  the tag is `idea/` and the build number without the product code. `build.txt` of the IDE
  installation holds the build number after the product code. For example, `IU-262.8665.337`
  gives the tag `idea/262.8665.337`.
- **Bytecode.** Run `javap -p -c -cp <jar> <class>` on a jar of the installed IDE (`lib/` or
  `plugins/<plugin>/lib/`). Use this for a language plugin that has no public source.
- **Decompiler.** IntelliJ IDEA has a decompiler jar. Run it with the bundled runtime of the IDE,
  because the toolchain JDK of the build cannot load its classes:

  ```bash
  <IDE>/jbr/bin/java -cp <IDE>/plugins/java-decompiler/lib/java-decompiler.jar \
    org.jetbrains.java.decompiler.main.decompiler.ConsoleDecompiler <class or jar> <output folder>
  ```

The citation names the class, the jar and the build number. For example:
`HierarchyBrowserBaseEx`, `lib/intellij.platform.lang.impl.jar`, IU-262.8665.337.

## CI

`.github/workflows/build.yml` (the workflow **Build**) runs on each pull request and on each
push to `main`. A new push to a pull request cancels the Build run in progress of that pull
request. A push to `main` cancels no run in progress, and the new run waits until that run
ends. Only one run can wait, so a newer push to `main` replaces the run that waits. The run of
the newer push tests both commits.

| Job | Runs | Does |
|---|---|---|
| Build | always | `./gradlew buildPlugin`; uploads the plugin as an artifact. |
| Test | always | `./gradlew check`: the unit tests and the platform tests. |
| Verify plugin | on a push to `main` only | `./gradlew verifyPlugin`. |
| Release draft | on a push to `main` only, after Build, Test and Verify plugin | Replaces the draft release (see "Release"). |

`release.yml` (the workflow **Release**) runs when a release is published. The consequences:

- A pull request that bumps a Gradle plugin gets no Verify plugin job. Its green checks do not
  cover this job. Run `./gradlew verifyPlugin` before the merge, and watch the first Build run
  on `main` after the merge.
- An infrastructure failure (a download, a runner) needs no commit. Run
  `gh run rerun <run id> --failed`. It runs the failed jobs again, and then the jobs that wait for
  them, for example Release draft. Find the run with `gh run list --workflow Build --branch main`:
  other workflows also run on `main`.

No job has a step that frees disk space, although the Build workflow of the
[IntelliJ Platform Plugin Template](https://github.com/JetBrains/intellij-platform-plugin-template)
has one (`jlumbroso/free-disk-space`). In November 2026 a runner had 86 GB of free disk before
that step, and the job Verify plugin needs about 16 GB for its IDE downloads. If a job fails with
a disk error, add the step again.

## Issues

### Issue forms

The repository has one issue form for each type, and blank issues are off
(`.github/ISSUE_TEMPLATE/config.yml`).

| Form | Title prefix | Label | Body headings, in this order |
|---|---|---|---|
| `bug-report.yml` | `[BUG] ` | `bug` | Description; Steps to reproduce; Expected vs actual behavior; IDE and version; Plugin version; IDE type; Relevant logs; Please confirm the following |
| `feature-request.yml` | `[FEATURE] ` | `enhancement` | Problem or motivation; Proposed solution; Alternatives considered; IDE / language context; Please confirm the following |
| `gap-report.yml` | `[GAP] ` | `gap` | IDE action or option; Evidence; What the tools do today; Proposed solution; Alternatives considered; IDE / language context; Please confirm the following |
| `performance.yml` | `[PERF] ` | `performance` | Description; Steps to reproduce; Expected vs actual behavior; IDE and version; Plugin version; IDE type; Relevant logs; Please confirm the following |
| `refactor.yml` | `[REFACTOR] ` | `refactor` | Problem or motivation; Proposed solution; Alternatives considered; IDE / language context; Please confirm the following |

From the command line, write the body with the `###` headings of the form. Put logs in a `bash`
code fence. Below `IDE type`, write one option of the form, and write `All IDEs` for a defect in
shared plugin code. The command gives the type label, the `severity:` label and the `component:`
labels (see "Labels").

```bash
gh issue create --title "[BUG] <summary>" --label bug --label "severity: <level>" \
  --label "component: <part>" --body-file <file>
```

### One issue for each defect

- One issue holds one defect or one request.
- Related parts get a parent issue and one sub-issue for each part. The description of a
  sub-issue starts with `Part of #<parent>.`. Link each sub-issue to its parent. The API takes the
  database id of the sub-issue, not its number:

  ```bash
  gh api -X POST repos/vcth4nh/idesense/issues/<parent>/sub_issues \
    -F sub_issue_id=$(gh api repos/vcth4nh/idesense/issues/<child> --jq .id)
  ```

  A `GET` of the same path lists the sub-issues.
- Unrelated parts get separate issues.

### Labels

Each issue has exactly one type label, exactly one `severity:` label and one or more `component:`
labels. An issue can also have the mark `deviation`. The sections below define the labels. The
description of a label on GitHub is the short form of its definition. Give the labels by the facts
of the tool and of the IDE, because the text of an issue can be wrong about them.

The labels give these filters for the issue list:

| Question | Filter |
|---|---|
| What is the next work? | `is:open label:bug`, then `label:gap`, then the other types |
| Which actions and options of the IDE can no tool call reach? | `is:open label:gap` |
| Which requests for a deviation from the IDE wait for the owner? | `is:open label:deviation` |
| Which issues are about one part of the repository? | `is:open label:"component: live-test"` |

### Type

| Label | Title prefix | Use for |
|---|---|---|
| `bug` | `[BUG] ` | A part that exists is wrong. A tool is wrong when a call that it accepts gives a result that differs from the IDE or from the documented result, when the call fails, or when the plugin causes an error or a warning in the log of the IDE. A test, the live-test harness, the build or a text can also be wrong. A text is wrong when it states a thing that is false, or when the reader cannot follow an instruction in it. |
| `gap` | `[GAP] ` | The IDE has an action or an option that no tool call can ask for. The correction adds a tool, a parameter or a parameter value. |
| `performance` | `[PERF] ` | A performance problem or an optimization. |
| `refactor` | `[REFACTOR] ` | A change of the structure of the plugin code with no change of behavior. A move to another API of the platform is maintenance, not a refactor. |
| `enhancement` | `[FEATURE] ` | A change that is none of the types above. Examples are the structure of a result, the guidance for the agent, test coverage, a document that lacks a part, and maintenance such as a move to a new API of the platform. |

When the request of an issue fits two types, the issue gets the type that is higher in the table.

To separate a `bug` from a `gap`, look at the call:

- When a call exists and its result differs from what the IDE shows for the same input, the issue
  is a `bug`. The result lacks an item or a signal that the IDE shows, or it holds a wrong value.
- When no call can ask for the action or the option of the IDE, the issue is a `gap`. An example is
  a toggle of an IDE tool window that no parameter of the tool sets.

A result that differs from the IDE on purpose is no bug, also when the owner did not approve the
difference yet. An issue that is only about such a result is an `enhancement` with the mark
`deviation`, also when its correction adds a parameter. But a tool that leaves out rows that the
IDE shows, with no signal in the result, has a `bug`, also when the cut is on purpose (see "No
silent drop" in [PRINCIPLES.md](PRINCIPLES.md)).

### Deviation

The mark `deviation` says that the issue, or a part of its request, is about a result that differs
from the IDE on purpose. A difference is on purpose when the code or a document says that it is
intended. Here a result is what a call returns for an input: the rows, the values of their fields,
an empty result or an error. A limit that cuts rows that the IDE shows is such a difference, and
so is a field or a mark on a row that the IDE does not show. Two kinds of issue get the mark:

- **A request.** The issue asks for a result that differs from the IDE on purpose. Or a tool has
  such a difference on purpose today, the list of the approved deviations has no entry for it, and
  the issue asks the owner to approve it or to remove it. Such a result needs the sign-off of the
  owner of the repository (see "Deviations" in [PRINCIPLES.md](PRINCIPLES.md)). Do not build the
  request before the owner decides. The decision is a comment on the issue, and the mark stays.
- **A report of an approved deviation.** The issue reports as a defect a difference that "Where a
  tool differs from the IDE on purpose" in
  [ARCHITECTURE.md](ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose) approves. Add the
  mark and a link to the entry, and close the issue as "not planned".

The body of a request ends with the section `### Decision for the owner`, after the sections of
its form. The section is a list with the items **The IDE**, **The tool today** or **The request**,
and **Choices**. The item **The IDE** states what the IDE shows, and whether this fact comes from
an observation or from the code. The choices have numbers, so that the owner can answer with a
number. The section makes clear which choice gives a result that differs from the IDE. An item
**Open points** follows when the body names open points, and one more item can give limits or
measurements of the body. The section holds only facts of the body, of the comments and of the
documents of the repository, and it recommends nothing. The section of a parent issue points to
the sub-issues that hold the decisions.

These cases get no mark:

- The issue reports a defect that is not on purpose, and a result that differs from the IDE is
  only one of the possible corrections, next to a correction with the result of the IDE. The
  correction with the result of the IDE is the default.
- The issue asks for a choice between two views, two options or two default states of the IDE. Each
  one is a result of the IDE.
- The issue is about a defect inside an approved deviation, for example a wrong value of a mark or
  a wrong note. Such an issue is a `bug`, also when the entry of the approved deviation cites it.
- The issue asks for a `notes` entry, a `warnings` entry or a flag for the whole result such as
  `truncated`, or for another form of a text field, for example a longer preview.
- An issue gets no mark as a record of a decision. The record of the approved deviations is that
  section of ARCHITECTURE.md.

### Component

A `component:` label names the part of the repository that the issue is about. It does not name
each part that the correction changes. A new parameter also needs documents and test rows, and its
issue has only `component: source`. An issue about two parts gets one label for each part.

| Label | Part |
|---|---|
| `component: source` | The plugin code in `src/main/`, without the skill folder: tools, MCP server, settings, tool window. The tool descriptions are in this code. |
| `component: skill` | The agent skill in `src/main/resources/skill/`. |
| `component: docs` | `README.md`, `AGENTS.md`, `CHANGELOG.md` and `docs/`. |
| `component: test` | The unit tests and the platform tests in `src/test/`. |
| `component: live-test` | All of `live-test/`: the harness, the fixture suite, the real-product suite and its documents. |
| `component: build` | The Gradle build, the GitHub workflows, the dependencies and the release. |

### Severity

The label descriptions are the rubric:

| Label | Use for |
|---|---|
| `severity: high` | A silent wrong or partial result on a default path, harm to the IDE, or a security defect |
| `severity: medium` | Wrong or degraded behavior with a signal or a workaround, or IDE error-log entries |
| `severity: low` | A rare trigger, an opt-in path, a cosmetic defect, a refactor, test coverage or a wish |

### Close, stale check, old numbers

- Close an issue when its correction is committed and validated on the working branch. Do not
  wait for the merge. In the close comment, name the commit and the cause. Also write `Closes #N`
  in the body of the pull request.
- For a stale check, search the cited symbol at `HEAD`, not the cited line: lines move. When an
  issue is partly out of date, add a comment `Triage <date> (main @ <sha>)` with the present
  `file:line`. Do not rewrite the issue. Close an issue as stale only with evidence that the
  behavior is gone.
- Numbers from before the rebrand to IdeSense refer to older trackers (the archived fork
  `vcth4nh/jetbrains-index-mcp-plugin` and its upstream `hechtcarmel/jetbrains-index-mcp-plugin`).
  This repository started again at #1, so an old number names another issue here. Such numbers
  are in the commit messages from before the commit
  `feat: rebrand fork to standalone IdeSense, release 1.0.0`, and in
  [CHANGELOG-before-rebrand.md](CHANGELOG-before-rebrand.md). The comments in `src/` have no old
  number: write no number of an older tracker into a comment.

## Pull requests

### Checklist

1. **Changelog.** A change of plugin behavior adds an entry under `## [Unreleased]` in
   `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com)). Use the sections `Added`,
   `Changed`, `Fixed` and `Removed`. Mark a breaking change with **Breaking** in its entry. Name
   the issue as `(#N)`. A change of only the live tests, the build or the docs needs no entry.
2. **No version change.** Do not change `pluginVersion`: it changes only in the release commit
   (see "Release"). A dev version stays on the command line (see "Dev builds").
3. **Code.** Follow the patterns of the code near your change. A new tool schema uses
   `SchemaBuilder`, and a new tool changes all files of "Add a tool".
4. **Tests.** Add tests for the new behavior.
5. **Docs.** Update the doc of each reader that the change touches (see "Doc ownership").
   After an edit of a pinned doc, run the drift test (see "Editing docs").
6. **Run the tests.** Run `./gradlew test --tests "*UnitTest*"` and each platform test class
   that your change touches, or all tests with `./gradlew test`. CI runs `./gradlew check`.
7. **Live tests.** For a change of tool behavior, run both suites (see "Live tests"). Bless under
   the bless rule of [live-test/AGENTS.md](../live-test/AGENTS.md). Commit the changed snapshots
   in the same pull request.
8. **IDE parity.** A result that differs from the IDE on purpose needs the sign-off of the
   owner of the repository (see "Mimic the IDE" in [PRINCIPLES.md](PRINCIPLES.md)) and an entry
   in "Where a tool differs from the IDE on purpose" in [ARCHITECTURE.md](ARCHITECTURE.md).
9. **Body.** Write `Closes #N` for each issue that the pull request corrects.

### Merge

Merge with a squash merge. The subject is the title of the pull request and its number:
`<title> (#<n>)`. Give the subject in the command:
`gh pr merge <n> --squash --subject "<title> (#<n>)"`. The titles use the Conventional Commits
form, for example `fix(tools): <summary>`.

### A stacked pull request after the squash merge of its base

The squash merge of the base adds one commit to `main`. The stacked pull request then shows
conflicts against `main`, because both sides changed the same lines. This procedure needs no
force push:

1. Change the base of the pull request: `gh pr edit <n> --base main`.
2. Run `git fetch origin`. Make sure that `main` is the old `main` plus the one squash commit.
   Make sure that the tree of `main` equals the head of the old base branch:
   `git diff --quiet origin/main <old base head>`.
   Make sure that the stacked branch contains that head:
   `git merge-base --is-ancestor <old base head> HEAD`. Stop if one of the checks fails: the
   merge of step 3 then drops changes of `main`.
3. On the stacked branch, run `git merge -s ours origin/main`. The merge keeps the tree of the
   stacked branch.
4. Push, and wait for the CI of the pull request.
5. Squash-merge with
   `gh pr merge <n> --squash --match-head-commit <sha> --subject "<title> (#<n>)" --body-file <file>`.

## Release

A release is a GitHub Release with the plugin zip. The version follows
[SemVer](https://semver.org): a patch for corrections, a minor version for new tools and
features, a major version for a breaking change (an entry with **Breaking**).

### Steps

1. **Bump.** On `main`, commit only the new `pluginVersion` in `gradle.properties`
   (`chore(release): bump pluginVersion to <version>`). Do not roll the changelog yet: the draft
   takes its notes from `## [Unreleased]`.
2. **Draft.** Push. The Build run on `main` ends with the job Release draft. This job deletes
   each draft release and creates a draft named `<version>` with the notes of `## [Unreleased]`
   (`getChangelog --unreleased`). For an infrastructure failure, see "CI".
3. **Validate.** Build the release zip at the bump commit with `./gradlew buildPlugin`, with no
   `-PpluginVersion`. Deploy it to all IDEs (see "Deploy a build to the IDEs" in
   [live-test/README.md](../live-test/README.md)). Run `./live-test/run.py --suite all` two times,
   with the checkout of each product. Each run must pass: the pass rule is in "Run the suites
   against a new build" of that file.
4. **Publish.** Read the draft notes. Then publish the draft:
   `gh release edit <version> --draft=false --latest`. Publish while the bump commit is the head
   of `main`: the draft targets `main`, and GitHub creates the tag at the publish.
5. **Zip.** The publish starts the workflow Release (`release.yml`). It checks out the tag, builds
   the plugin, and attaches `idesense-<version>.zip` to the release. Its step Publish Plugin
   uploads to the JetBrains Marketplace only when the secret `PUBLISH_TOKEN` exists, with the
   signing secrets. Without the secret, the workflow skips that step and still succeeds.
6. **Roll the changelog.** Add `## [<version>] - <YYYY-MM-DD>` directly below `## [Unreleased]`
   (two lines). Commit it as `docs(changelog): roll Unreleased into <version>`, and push.

**If the validation fails,** do not publish. Correct the defect with a pull request. Then start
again at step 1 with the next patch version, because only the version tells one build from
another. The Build run of the new bump commit replaces the draft, and the version that failed
gets no tag.

### Traps

- **Each version heading of `CHANGELOG.md` exists one time.** The changelog plugin merges two
  sections that have the same version, and the build takes the change notes of the plugin from the
  section of `pluginVersion` (`changeNotes` in `build.gradle.kts`). For this reason the changelog
  of the older project is in its own file, `docs/CHANGELOG-before-rebrand.md`. `DocsDriftUnitTest`
  fails when a version has a second heading.
- **Do not run `patchChangelog` for the roll.** It adds compare links with a `v` prefix (the
  default of `versionPrefix` in the changelog plugin), and the tags of this repository have no
  prefix (for example `2.1.0`). It also deletes text that is below the last section. CI runs it in
  the step Patch Changelog of `release.yml`, and before `publishPlugin`, which depends on it. These
  runs change only the CI checkout, so step 6 is a manual edit.
- **Each push to `main` after the publish creates a new draft with the same name.** Release draft
  reads `pluginVersion`, which still holds the released version. The draft does no harm, and the
  next run replaces it. To remove it, delete it by its release id:

  ```bash
  gh api repos/vcth4nh/idesense/releases --jq '.[] | select(.draft) | .id'
  gh api -X DELETE repos/vcth4nh/idesense/releases/<id>
  ```

  Do not use `gh release delete <version>`: the tag name selects the published release.
