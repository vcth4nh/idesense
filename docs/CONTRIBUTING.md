# Contributing

How to work on the IdeSense plugin: tech stack, build/run, dev loop, testing, and the PR checklist. For design and internals, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Doc ownership (where each topic lives)
| Topic | Owner |
|---|---|
| Build / run / dev-loop / testing / PR checklist | CONTRIBUTING.md |
| Design, backing-mechanism model, multi-language, hierarchy internals | ARCHITECTURE.md |
| Agent-only rules + pointers | CLAUDE.md |
| User-facing tool reference | USAGE.md |
| Agent return-shapes + tool selection | src/main/resources/skill/idesense/references/tools-reference.md |

## Technology Stack
- **Language**: Kotlin (JVM 21)
- **Build System**: Gradle 9.0 with Kotlin DSL
- **IDE Platform**: IntelliJ IDEA 2025.3+ (platformType = IC)
- **HTTP Server**: Ktor CIO 2.3.12 (embedded, configurable port)
- **Protocol**: Model Context Protocol (MCP) — 2025-11-25 (default), negotiated down to 2025-03-26 or 2024-11-05

## Development Guidelines

### Kotlin Standards
- Use Kotlin idioms (data classes, extension functions, coroutines where appropriate)
- Leverage null safety features
- Use `@RequiresBackgroundThread` / `@RequiresReadLock` annotations where needed

### IntelliJ Platform Best Practices
- Always check `DumbService.isDumb()` before accessing indexes
- Use `ReadAction` / `WriteAction` for PSI modifications
- Register extensions in `plugin.xml`, not programmatically
- Use `ApplicationManager.getApplication().invokeLater()` for UI updates
- Handle threading correctly (read actions on background threads, write actions on EDT)

### PSI-Document Synchronization

The IntelliJ Platform maintains separate Document (text) and PSI (parsed structure) layers.
When files are modified externally (e.g., by AI coding tools), PSI may not immediately reflect
the changes. This can cause search APIs to miss references in newly created files.

**Solution**: Call `ide_sync_files` after external file changes, or enable "Sync external file changes" in Settings.
`AbstractMcpTool.execute()` only refreshes the VFS/PSI automatically when **both** `requiresPsiSync` is true for that tool **and** `syncExternalChanges` is enabled in settings — the setting defaults to false, so automatic sync is off by default.

**User Setting**: "Sync external file changes before operations" (Settings → MCP Server)
- **Disabled** (default): Best performance, suitable for most use cases
- **Enabled**: **WARNING - SIGNIFICANT PERFORMANCE IMPACT.** Use only when rename/find-usages misses references in files just created externally. Each operation will take seconds instead of milliseconds on large repos.

**For tool developers**:
- Extend `AbstractMcpTool` and implement `doExecute()` (not `execute()`)
- PSI synchronization runs before `doExecute()` only when `requiresPsiSync` is true **and** `syncExternalChanges` is enabled in settings
- To opt-out (for tools that don't use PSI), override:
  ```kotlin
  override val requiresPsiSync: Boolean = false
  ```

### Code Style
- Follow Kotlin coding conventions
- Use meaningful variable names
- Keep functions small and focused
- Extract reusable logic to utility classes

### Tool Schema Guidelines

All tool input schemas MUST use `SchemaBuilder` (in `tools/schema/SchemaBuilder.kt`). This eliminates boilerplate and ensures consistency:

```kotlin
// ✓ Use SchemaBuilder for all tool schemas
override val inputSchema = SchemaBuilder.tool()
    .projectPath()
    .file()
    .lineAndColumn()
    .intProperty("maxResults", "Maximum results to return. Default: 100, max: 500.")
    .build()

// For enum parameters:
.enumProperty("matchMode", "How to match the query.", listOf("substring", "prefix", "exact"))

// For complex properties that don't fit the builder, use the escape hatch:
.property("target_type", buildJsonObject { /* custom schema */ })
```

## Building and Running

```bash
# Build the plugin
./gradlew build

# Run IDE with plugin installed
./gradlew runIde

# Run tests
./gradlew test

# Run plugin verification
./gradlew runPluginVerifier
```

### Run Configurations (in `.run/`)
- **Run Plugin** - Launch IDE with plugin for manual testing
- **Run Tests** - Execute unit tests
- **Run Verifications** - Run compatibility checks

### Local Plugin Dev Loop (autonomous iterate-and-verify)

The plugin is **not** dynamically reloadable (app-level Ktor service + listeners), so
every code change requires a build + reinstall + IDE restart. Once the
`ide_install_plugin` / `ide_restart` tools are loaded in the target IDEs (one-time
manual bootstrap — install + enable + restart), the full loop runs autonomously over
MCP with no manual steps:

```
edit → ./gradlew buildPlugin → ide_install_plugin → ide_restart
     → poll MCP until back → re-run live-test → compare
```

**Zip containment.** `ide_install_plugin` only accepts a zip that resolves inside the target
IDE's open project. When that IDE has this repo open, the default path (newest zip in
`build/distributions/`) just works. When it has a *different* project open (e.g. the
`live-test/<lang>` fixtures), copy the zip into that project root first and pass the
in-project path — see [live-test/README.md](../live-test/README.md).

**Dev versioning during iteration.** While iterating, set `pluginVersion` to a
monotonic dev suffix: `5.3.5-dev.01`, `5.3.5-dev.02`, … (increment every build that
will be installed). Rationale:

- IntelliJ plugin loading treats an equal version string as a **no-op** — reinstalling
  `5.3.7` over a running `5.3.7` silently keeps the old code (this bit us repeatedly).
  A distinct version every build guarantees install+restart actually loads the new bits.
- `serverInfo.version` (from the loaded `PluginDescriptor`, via the MCP `initialize`
  response) then unambiguously identifies *which iteration* is running — the
  authoritative check that a restart actually swapped code, not just staged it on disk.

**Real version bump happens once, at the end.** Only after the user confirms the work
is correct **and** the branch is merged, drop the `-dev.NN` suffix and set the real
SemVer version per the PR checklist below. Dev-suffixed versions never land on `main`.

**Escalation during the loop:** when verification needs the IDE or hits a
mimic-vs-useful tradeoff, stop and ask the user (see "Core Design Principle: Mimic the
IDE" in [ARCHITECTURE.md](ARCHITECTURE.md)).

## Plugin Configuration

Key files:
- `gradle.properties` - Plugin metadata (version, IDs, platform version)
- `plugin.xml` - Extension points and dependencies
- `build.gradle.kts` - Build configuration

### Adding Dependencies
1. Add to `gradle/libs.versions.toml` for version catalog
2. Reference in `build.gradle.kts` using `libs.xxx` syntax

### Adding Extension Points
Register in `plugin.xml`:
```xml
<extensions defaultExtensionNs="com.intellij">
    <your.extension implementation="com.your.ImplementationClass"/>
</extensions>
```

## Testing

### Test Architecture

Tests are split into two categories to optimize execution time:

1. **Unit Tests (`*UnitTest.kt`)** - Extend `junit.framework.TestCase`
   - Fast, no IntelliJ Platform initialization required
   - Use for: serialization, schema validation, data classes, registries, pure logic
   - Run with: `./gradlew test --tests "*UnitTest*"`

2. **Platform Tests (`*Test.kt`)** - Extend `BasePlatformTestCase`
   - Slower, requires full IntelliJ Platform with indexing
   - Use for: tests needing `project`, PSI operations, tool execution, resource reads
   - Run with: `./gradlew test --tests "*Test" --tests "!*UnitTest*"`

### Test File Conventions

| Test Class | Base Class | Purpose |
|------------|------------|---------|
| `McpPluginUnitTest` | `TestCase` | JSON-RPC serialization, error codes, registry |
| `McpPluginTest` | `BasePlatformTestCase` | Platform availability |
| `ToolsUnitTest` | `TestCase` | Tool schemas, registry, definitions |
| `ToolsTest` | `BasePlatformTestCase` | Tool execution with project |
| `JsonRpcHandlerUnitTest` | `TestCase` | JSON-RPC protocol, error handling |
| `JsonRpcHandlerTest` | `BasePlatformTestCase` | Tool calls requiring project |
| `CommandHistoryUnitTest` | `TestCase` | Data classes, filters |
| `CommandHistoryServiceTest` | `BasePlatformTestCase` | Service with project |

### When to Use Each Base Class

**Use `TestCase` (unit test) when:**
- Testing serialization/deserialization
- Validating schemas and definitions
- Testing data classes and their properties
- Testing registries without executing tools
- No `project` instance is needed

**Use `BasePlatformTestCase` (platform test) when:**
- Test needs `project` instance
- Test executes tools against a project
- Test uses project-level services (e.g., `CommandHistoryService`)
- Test needs PSI or index access

### Running Tests

```bash
# Run all tests (unit + platform) — this is what CI runs
./gradlew test

# Run only fast unit tests — recommended locally and required for AI agents (see CLAUDE.md)
./gradlew test --tests "*UnitTest*"

# Run only platform tests (requires IntelliJ Platform init; do NOT run these as an AI agent)
./gradlew test --tests "*Test" --tests "!*UnitTest*"

# Run specific test class
./gradlew test --tests "McpPluginUnitTest"
```

> **AI agents (Claude, Codex, etc.)**: run only `./gradlew test --tests "*UnitTest*"`. Never run platform tests (`*Test`) locally — CI handles those.

> **Editing docs?** `DocsDriftUnitTest` (a `*UnitTest`) pins the catalog docs to code-derived facts (tool names, params), but it reads the `.md` files via `File()` at runtime — they are **not** declared Gradle task inputs. So after a docs-only edit a plain `./gradlew test` reports `UP-TO-DATE`, and even `cleanTest` can return `FROM-CACHE` — a **stale pass**. Force a real re-run with `./gradlew --no-build-cache cleanTest test --tests "*DocsDriftUnitTest*"`. (`--rerun-tasks` also works but recompiles everything → add `-Pkotlin.daemon.jvmargs="-Xmx4g"`.)

> **Live-test harness**: For tool-behavior changes, also run the snapshot regression suite in `live-test/` against real running IDEs. See [live-test/README.md](../live-test/README.md) for instructions. The harness is not part of `./gradlew test` and requires running IDEs.

### Test Data
- Place test fixtures in `src/test/testData/`
- Test both smart mode and dumb mode scenarios for platform tests

## Troubleshooting

### Common Issues
1. **IndexNotReadyException** - Accessing indexes in dumb mode
   - Solution: Use `DumbService.getInstance(project).runWhenSmart { ... }`

2. **WriteAction required** - Modifying PSI without write lock
   - Solution: Wrap in `WriteCommandAction.runWriteCommandAction(project) { ... }`

3. **Must be called from EDT** - UI operations on background thread
   - Solution: Use `ApplicationManager.getApplication().invokeLater { ... }`

4. **Search misses newly created files** - PSI not synchronized with document
   - Cause: External tools modified files but PSI tree hasn't been updated
   - Solution: Enable "Sync external file changes" in Settings → MCP Server (WARNING: significant performance impact)
   - For custom code: `PsiDocumentManager.getInstance(project).commitAllDocuments()`

## Contributing / PR Checklist

Every PR **must** include:

1. **Version bump** — Update `pluginVersion` in `gradle.properties` following [SemVer](https://semver.org):
   - **Patch** (3.x.**Y**): Bug fixes, internal refactoring with no behavior change
   - **Minor** (3.**Y**.0): New features, new tools, protocol improvements
   - **Major** (**Y**.0.0): Breaking changes to tool schemas, transport, or client configuration
   - This is the **final** version. During iteration the version carries a `-dev.NN`
     suffix (see "Local Plugin Dev Loop"); strip it and set the real SemVer value only
     once the user confirms and the branch is ready to merge. `-dev.NN` never lands on `main`.
2. **CHANGELOG.md update** — Add an entry under `## [Unreleased]` following [Keep a Changelog](https://keepachangelog.com) format. Use sections: `Added`, `Changed`, `Fixed`, `Removed`, `Breaking`
3. Follow existing code patterns and use `SchemaBuilder` for new tool schemas
4. Add tests for new functionality
5. Update the docs ([ARCHITECTURE.md](ARCHITECTURE.md) for design/structure, this file for process) for any structural or architectural changes
6. Run `./gradlew test --tests "*UnitTest*"` to verify unit tests pass. Do NOT run platform tests yourself (CI runs `./gradlew test` which includes them). For tool-behavior changes, also run the live-test harness — see [live-test/README.md](../live-test/README.md).

---

**Template Source**: [JetBrains IntelliJ Platform Plugin Template](https://github.com/JetBrains/intellij-platform-plugin-template)
