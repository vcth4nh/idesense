# IdeSense

IdeSense is an IntelliJ Platform plugin with an MCP server. It gives coding agents the
code-analysis engines of the IDE (the index, navigation, cross-references, diagnostics), and
no person operates the IDE. The IDE does not edit, build or run code for the agent. The goal,
the scope and the design principles are in [docs/PRINCIPLES.md](docs/PRINCIPLES.md).

## Rules for an agent

- **Mimic the IDE → Escalate.** The design principles are in
  [docs/PRINCIPLES.md](docs/PRINCIPLES.md). Read them before you change what a tool returns or
  says: a result, a parameter, a note, a warning or an error text. The default is that each tool
  returns what the IDE's own action or tool window shows for the same input. Two cases need more
  than the code:
  - *The result can be judged only against the IDE.* Establish what the IDE shows: observe the
    running IDE (see "Throwaway IDE" in [live-test/README.md](live-test/README.md)), or ask the
    owner of the repository to do it. Do not decide from the code alone, and do not bless a
    result on a guess.
  - *Mirroring the IDE would withhold information that is more useful to the calling agent.*
    Stop and ask the owner of the repository. Do not decide silently.

  The approved deviations are in [ARCHITECTURE.md](docs/ARCHITECTURE.md), "Where a tool differs
  from the IDE on purpose".
- **Cite, do not assert.** A claim about the IntelliJ Platform, a language plugin or an IDE
  needs its evidence: the source or the bytecode (class, jar, build number), or an observation
  of the running IDE. Where an item shows in the IDE UI is a question for the running IDE, not
  for `plugin.xml`. Check the report of a subagent against the source before you use it.
- **Run the tests of your change.** Unit tests (`*UnitTest`) and platform tests (`*Test`
  extending `BasePlatformTestCase`) both run on your machine. Run each test class that your
  change touches, and make a new test fail on the old code first. CI runs all tests
  ([CONTRIBUTING.md](docs/CONTRIBUTING.md), "Tests").
- **Dev builds.** Only the version tells one build from another, so each build that goes into
  an IDE needs a new version. Give it on the command line, never in `gradle.properties`:
  `./gradlew buildPlugin -PpluginVersion=<version>-dev.NN`. No `-dev.NN` value lands on `main`.
  Details: [CONTRIBUTING.md](docs/CONTRIBUTING.md#dev-builds), "Dev builds".
- **Live tests use shared IDEs.** Read [live-test/AGENTS.md](live-test/AGENTS.md) before a live
  run, a bless, a change of a row or of a fixture file, an audit, or an agent batch.
- **Docs are pinned to the code.** After an edit of `README.md`, `docs/USAGE.md`,
  `docs/ARCHITECTURE.md` or the skill files, run the docs drift test
  ([CONTRIBUTING.md](docs/CONTRIBUTING.md), "Editing docs").

## Where things live

Each fact has one home: the file of its reader.

| Reader | File | Content |
|---|---|---|
| User of the plugin | [README.md](README.md), [docs/USAGE.md](docs/USAGE.md) | Install, configuration, tool reference |
| User of the plugin | [CHANGELOG.md](CHANGELOG.md), [docs/CHANGELOG-before-rebrand.md](docs/CHANGELOG-before-rebrand.md) | The changes of each release; the changelog of the older project |
| Agent that uses the tools | [SKILL.md](src/main/resources/skill/idesense/SKILL.md), [tools-reference.md](src/main/resources/skill/idesense/references/tools-reference.md) | Tool selection and return shapes; shipped with the plugin |
| Agent that works on this repository | this file, [live-test/AGENTS.md](live-test/AGENTS.md) | The rules that an agent needs in each session |
| Maintainer | [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Build, test, dev loop, dependencies, CI, issues, pull requests, release |
| Maintainer | [docs/PRINCIPLES.md](docs/PRINCIPLES.md) | Goal, scope, design principles |
| Maintainer | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Backing mechanisms, deviations from the IDE, platform contracts |
| Maintainer | [live-test/README.md](live-test/README.md), [live-test/CONVENTIONS.md](live-test/CONVENTIONS.md) | The live-test harness: commands, IDE operation, row and fixture conventions |
| Maintainer | [live-test/METHOD.md](live-test/METHOD.md) | The method of the four live-test instruments: the kinds of truth, the keys, the audit verdict, the agent batch, what a result can claim |
| Maintainer | [live-test/keygen/README.md](live-test/keygen/README.md), [live-test/audit/README.md](live-test/audit/README.md), [live-test/bench/README.md](live-test/bench/README.md) | The key makers, the audit and the agent benchmark: commands, file formats, setup, procedures |
| Another person who scores an agent | [live-test/bench/questions/README.md](live-test/bench/questions/README.md) | The questions and keys of the benchmark, and the score of an answer |
| Maintainer | the `GROUND-TRUTH.md` files in `live-test/fixtures/_snapshots/` and `live-test/real-products/_snapshots/`, `live-test/real-products/_setup/<product>/notes.md` | Results that look wrong but that the IDE also returns, parked rows, the setup facts of a product |

A new fact goes to the file of its reader. This file gets only a rule that an agent needs in
each session, as a short rule with a link. A fact about one machine or one
person (a path, a host name, an account) goes to no tracked file.
