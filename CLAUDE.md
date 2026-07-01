# IdeSense

An IntelliJ Platform plugin that exposes an MCP server so coding agents can use the IDE's
indexing, navigation, and refactoring engines. Works across JetBrains IDEs (IntelliJ IDEA,
PyCharm, WebStorm, GoLand, PhpStorm, RubyMine, CLion, RustRover, DataGrip, Android Studio).

## Agent rules

- **Mimic the IDE → Escalate.** Every tool should return what the IDE's own action/tool
  window shows for the same input; faithfully mirroring the IDE is the default. When
  correctness can only be judged against the running IDE, or when mirroring the IDE would
  withhold info that's genuinely more useful to the agent, **stop and ask the user** — don't
  decide silently. Full design principle + escalation rules: [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Never run platform tests yourself** (`*Test` extending `BasePlatformTestCase`) — CI runs
  them. Unit tests (`*UnitTest`) are fine.
- **Dev versioning gotcha:** during iteration use a monotonic `-dev.NN` suffix on
  `pluginVersion`; IntelliJ treats an equal version string as a no-op install, so reusing a
  version silently keeps old code. `-dev.NN` never lands on `main`. Details: [CONTRIBUTING.md](docs/CONTRIBUTING.md).

## Where things live
- **Using the tools (agents):** src/main/resources/skill/idesense/SKILL.md
- **User tool reference:** docs/USAGE.md
- **Contributing (build/test/PR/dev-loop):** docs/CONTRIBUTING.md
- **Architecture & design:** docs/ARCHITECTURE.md
