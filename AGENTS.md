# IdeSense

An IntelliJ Platform plugin that exposes an MCP server giving coding agents the IDE's
code-analysis engines — indexing, navigation, cross-references, diagnostics — with no
human-in-the-IDE interaction required. The IDE is not used to edit, build, or run code on the
agent's behalf; a minimal set of index-backed refactorings (rename, move file) is retained.
Works across JetBrains IDEs (IntelliJ IDEA, PyCharm, WebStorm, GoLand, PhpStorm, RubyMine,
CLion, RustRover, DataGrip, Android Studio).

## Rules for an agent

- **Mimic the IDE → Escalate.** Each tool returns what the IDE's own action or tool window
  shows for the same input. That is the default. Two cases need more than the code:
  - *The result can be judged only against the IDE.* Establish what the IDE shows: observe the
    running IDE, or ask the maintainer to do it. Do not decide from the code alone, and do not
    bless a result on a guess.
  - *Mirroring the IDE would withhold information that is more useful to the calling agent.*
    Stop and ask the maintainer. Do not decide silently.

  The design principle and the approved deviations are in
  [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Text for the calling agent.** A `notes` entry, a `warnings` entry or an error message in a
  tool result says what the result holds and why, in terms of the code: the symbol, its
  position, the effect on the result. It names no dialog, question, button or window of the
  IDE, because the calling agent has no IDE window. The reason for IDE parity goes into
  `docs/USAGE.md`, the changelog, the GitHub issue and the code comments.
- **Cite, do not assert.** A claim about the IntelliJ Platform, a language plugin or an IDE
  needs its evidence: the source or the bytecode (class, jar, build number), or an observation
  of the running IDE. Where an item shows in the IDE UI is a question for the running IDE, not
  for `plugin.xml`. Check the report of a subagent against the source before you use it.
- **Never run platform tests yourself** (`*Test` extending `BasePlatformTestCase`) — CI runs
  them. Unit tests (`*UnitTest`) are fine.
- **Dev builds.** IntelliJ treats an equal version string as a no-op install, so each build
  that goes into an IDE needs a new version. Give it on the command line:
  `./gradlew buildPlugin -PpluginVersion=<version>-dev.NN`. Take a number above each build that
  an IDE has or that is on the disk. No `-dev.NN` value lands on `main`. Details:
  [CONTRIBUTING.md](docs/CONTRIBUTING.md).
- **Live tests use shared IDEs.** Read [live-test/AGENTS.md](live-test/AGENTS.md) before a live
  run, a bless, or a change of a row or of a fixture file.
- **Docs are pinned to the code.** After an edit of `README.md`, `docs/USAGE.md`,
  `docs/ARCHITECTURE.md` or the skill files, force a real run of the docs drift test
  ([CONTRIBUTING.md](docs/CONTRIBUTING.md), "Editing docs").

## Where things live

Each fact has one home: the file of its reader.

| Reader | File | Content |
|---|---|---|
| User of the plugin | [README.md](README.md), [docs/USAGE.md](docs/USAGE.md) | Install, configuration, tool reference |
| Agent that uses the tools | [SKILL.md](src/main/resources/skill/idesense/SKILL.md), [tools-reference.md](src/main/resources/skill/idesense/references/tools-reference.md) | Tool selection and return shapes; shipped with the plugin |
| Agent that works on this repository | this file, [live-test/AGENTS.md](live-test/AGENTS.md) | The rules that an agent needs in each session |
| Maintainer | [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Build, test, dev loop, dependencies, CI, issues, pull requests, release |
| Maintainer | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design rules, backing mechanisms, platform contracts |
| Maintainer | [live-test/README.md](live-test/README.md), [live-test/CONVENTIONS.md](live-test/CONVENTIONS.md) | The live-test harness: commands, IDE operation, row and fixture conventions |

A new fact goes to the file of its reader, not to this file. A fact about one machine or one
person (a path, a host name, an account) goes to no tracked file.
