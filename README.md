# IdeSense

![Build](https://github.com/vcth4nh/idesense/workflows/Build/badge.svg)

A JetBrains IDE plugin that exposes an **MCP (Model Context Protocol) server**, enabling AI coding assistants like Claude, Codex, Cursor, and Windsurf to leverage the IDE's powerful indexing and refactoring capabilities.

**Fully tested**: IntelliJ IDEA, PyCharm, WebStorm, GoLand, RustRover, Android Studio, PhpStorm
**May work** (untested): RubyMine, CLion, DataGrip

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/vcth4nh)

<!-- Plugin description -->
**IdeSense** is an MCP server for JetBrains IDEs (IntelliJ IDEA, PyCharm, WebStorm, GoLand, PhpStorm, RustRover, and more) that gives AI coding assistants the IDE's own indexing, navigation, and refactoring engines through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io).

### Features

**Multi-Language Support**
Advanced tools work across multiple languages based on available plugins:
- **Java & Kotlin** - IntelliJ IDEA, Android Studio
- **Python** - PyCharm (all editions), IntelliJ with Python plugin
- **JavaScript & TypeScript** - WebStorm, IntelliJ Ultimate, PhpStorm
- **Go** - GoLand, IntelliJ IDEA Ultimate with Go plugin
- **PHP** - PhpStorm, IntelliJ Ultimate with PHP plugin
- **Rust** - RustRover, IntelliJ IDEA Ultimate with Rust plugin, CLion
- **Markdown** - heading outlines in file structure for IDEs with the bundled Markdown plugin

**Universal Tools (All Supported JetBrains IDEs)**
- **Find References** - Locate all usages of any symbol across the project
- **Go to Definition** - Navigate to symbol declarations
- **Code Diagnostics** - Access errors, warnings, and quick fixes
- **Index Status** - Check if code intelligence is ready
- **Sync Files** - Force sync VFS/PSI cache after external file changes
- **Build Project** - Trigger IDE build with structured error/warning output (disabled by default)
- **Find Class** - Fast class/interface search by name (exact by default; opt into camelCase/substring matching with `fuzzySearch`)
- **Find File** - Fast file search by name using IDE's file index
- **Symbol Search** - Find code symbols by name with IntelliJ Go to Symbol matching (disabled by default)
- **Search Text** - Text search using IDE's pre-built word index
- **Read File** - Read file content by path or qualified name, including library sources (disabled by default)

**Extended Tools (Language-Aware)**
These tools activate based on installed language plugins:
- **Type Hierarchy** - Explore class inheritance chains
- **Call Hierarchy** - Trace method/function call relationships
- **Find Implementations** - Discover interface/abstract implementations
- **Find Super Methods** - Navigate method override hierarchies
- **File Structure** - View hierarchical file structure like IDE's Structure view, including Markdown heading outlines (disabled by default)

**Refactoring Tools**
- **Rename Refactoring** - Safe renaming with automatic related element renaming (getters/setters, overriding methods) - works across ALL languages, fully headless
- **Reformat Code** - Reformat using project code style with import optimization (disabled by default)
- **Safe Delete** - Remove code with usage checking (Java/Kotlin only)
- **Java to Kotlin Conversion** - Convert Java to Kotlin using IntelliJ's built-in converter (Java only)

### Why Use This Plugin?

Unlike simple text-based code analysis, this plugin gives AI assistants access to:
- **True semantic understanding** through the IDE's AST and index
- **Cross-project reference resolution** that works across files and modules
- **Multi-language support** - automatically detects and uses language-specific handlers
- **Safe refactoring operations** with automatic reference updates and undo support

Perfect for AI-assisted development workflows where accuracy and safety matter.
<!-- Plugin description end -->

## Documentation

- **[USAGE.md](docs/USAGE.md)** — full per-tool reference (parameters, examples, return shapes)
- **[CONTRIBUTING.md](docs/CONTRIBUTING.md)** — build, dev-loop, testing, PR checklist
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — design, backing-mechanism model, internals
- **[CHANGELOG.md](CHANGELOG.md)** — release notes and version history
- **[Agent skill](src/main/resources/skill/idesense/SKILL.md)** — runtime guidance for AI agents on tool selection and conventions
- **[Live-test harness](live-test/README.md)** — snapshot regression suite for verifying tool behavior against real IDEs

## Table of Contents

- [Available Tools](#available-tools)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Client Configuration](#client-configuration)
- [Multi-Project Support](#multi-project-support)
- [Tool Window](#tool-window)
- [Error Codes](#error-codes)
- [Community Integrations](#community-integrations)
- [Contributing](#contributing)

## Available Tools

The plugin provides **26 MCP tools** — 15 enabled by default, 11 opt-in (toggle any tool in <kbd>Settings</kbd> > <kbd>Tools</kbd> > <kbd>IdeSense</kbd>). The matrix below shows per-language support and test status; for parameters, examples, and return shapes, see **[USAGE.md](docs/USAGE.md)**.

**Legend:**
- **✅** supported & tested
- **⚠️** should work, not tested
- **⛔** not supported

**Navigation & search**

| Tool | Java | Kotlin | Python | JS | TS | Go | PHP | Rust |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `ide_find_usages` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_find_definition` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_find_class` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_find_symbol` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_find_file` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_search_text` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Hierarchy & structure**

| Tool | Java | Kotlin | Python | JS | TS | Go | PHP | Rust |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `ide_type_hierarchy` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_call_hierarchy` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_find_implementations` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_find_super_methods` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_file_structure` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Analysis**

| Tool | Java | Kotlin | Python | JS | TS | Go | PHP | Rust |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `ide_diagnostics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Refactoring**

| Tool | Java | Kotlin | Python | JS | TS | Go | PHP | Rust |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `ide_refactor_rename` | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| `ide_move_file` | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| `ide_reformat_code` | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| `ide_optimize_imports` | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| `ide_refactor_safe_delete` | ⚠️ | ⚠️ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| `ide_convert_java_to_kotlin` | ⚠️ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |

**Project** — language-agnostic (operate on the project/IDE, not language-specific code)

| Tool | Java | Kotlin | Python | JS | TS | Go | PHP | Rust |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `ide_index_status` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_install_plugin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_restart` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_sync_files` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_build_project` | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| `ide_read_file` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> **Notes:**
> - `ide_refactor_safe_delete` and `ide_convert_java_to_kotlin` require the Java plugin; refactoring tools are supported but not yet live-tested here (⚠️).
> - `ide_build_project` does a real build on JVM projects (Java/Kotlin, via JPS — ✅). It's build-system-driven (JPS/Gradle/Maven), so on non-JVM projects with no such build it returns trivial success without compiling — those stay ⚠️.
> - `ide_search_text` is backed by the IDE's word index, so language keywords (e.g. Kotlin `fun`) may not be matched even though identifiers and most words are.

## Requirements

- **JetBrains IDE** 2025.3 or later (any IDE based on IntelliJ Platform)
- **JVM** 21 or later
- **MCP Protocol** 2025-11-25 (primary Streamable HTTP, negotiated; 2025-03-26 / 2024-11-05 also supported)

### Supported IDEs

**Fully Tested:**
- IntelliJ IDEA (Community/Ultimate)
- Android Studio
- PyCharm (Community/Professional)
- WebStorm
- GoLand
- RustRover
- PhpStorm

**May Work (Untested):**
- RubyMine
- CLion
- DataGrip

> The plugin uses standard IntelliJ Platform APIs and should work on any IntelliJ-based IDE, but has only been tested on the IDEs listed above.

## Installation

> **Note:** IdeSense isn't on the JetBrains Marketplace yet — for now, use [Manual Installation](#manual-installation) below.

### Using the IDE built-in plugin system

<kbd>Settings/Preferences</kbd> > <kbd>Plugins</kbd> > <kbd>Marketplace</kbd> > <kbd>Search for "IdeSense"</kbd> > <kbd>Install</kbd>

### Using JetBrains Marketplace

Go to [JetBrains Marketplace](https://plugins.jetbrains.com/) and install it by clicking the <kbd>Install to ...</kbd> button.

### Manual Installation

Download the [latest release](https://github.com/vcth4nh/idesense/releases) and install it manually:
<kbd>Settings/Preferences</kbd> > <kbd>Plugins</kbd> > <kbd>⚙️</kbd> > <kbd>Install plugin from disk...</kbd>

## Quick Start

1. **Install the plugin** and restart your JetBrains IDE
2. **Open a project** - the MCP server starts automatically with IDE-specific defaults:
   - IntelliJ IDEA: `intellij-idesense` on port **29170**
   - PyCharm: `pycharm-idesense` on port **29172**
   - WebStorm: `webstorm-idesense` on port **29173**
   - Other IDEs: See [IDE-Specific Defaults](#ide-specific-defaults)
3. **Configure your AI assistant** using the "Install on Coding Agents" button (easiest) or manually
4. **Use the tool window** (bottom panel: "IdeSense") to copy configuration or monitor commands
5. **Change port** (optional): Click "Change port, disable tools" in the toolbar or go to <kbd>Settings</kbd> > <kbd>Tools</kbd> > <kbd>IdeSense</kbd>

### Using the "Install on Coding Agents" Button

The easiest way to configure your AI assistant:
1. Open the "IdeSense" tool window (bottom panel)
2. Click the prominent **"Install on Coding Agents"** button on the right side of the toolbar
3. A popup appears with two sections:
   - **Install Now** - For Claude Code CLI and Codex CLI: Runs the installation command automatically
   - **Copy Configuration** - For other clients: Copies the JSON config to your clipboard
4. For "Copy Configuration" clients, paste the config into the appropriate config file

## Client Configuration

### Claude Code (CLI)

Use the "Install on Coding Agents" button in the tool window, or run this command (adjust name and port for your IDE):

```bash
# IntelliJ IDEA
claude mcp add --transport http intellij-idesense http://127.0.0.1:29170/mcp/streamable-http --scope user

# PyCharm
claude mcp add --transport http pycharm-idesense http://127.0.0.1:29172/mcp/streamable-http --scope user

# WebStorm
claude mcp add --transport http webstorm-idesense http://127.0.0.1:29173/mcp/streamable-http --scope user
```

Options:
- `--scope user` - Adds globally for all projects
- `--scope project` - Adds to current project only

To remove: `claude mcp remove <server-name>` (e.g., `claude mcp remove intellij-idesense`)

### Codex CLI

Use the "Install on Coding Agents" button in the tool window, or run this command (adjust name and port for your IDE):

```bash
# IntelliJ IDEA
codex mcp add intellij-idesense --url http://127.0.0.1:29170/mcp/streamable-http

# PyCharm
codex mcp add pycharm-idesense --url http://127.0.0.1:29172/mcp/streamable-http

# WebStorm
codex mcp add webstorm-idesense --url http://127.0.0.1:29173/mcp/streamable-http
```

To remove: `codex mcp remove <server-name>` (e.g., `codex mcp remove intellij-idesense`)

### Cursor

Add to `.cursor/mcp.json` in your project root or `~/.cursor/mcp.json` globally (adjust name and port for your IDE):

```json
{
  "mcpServers": {
    "intellij-idesense": {
      "url": "http://127.0.0.1:29170/mcp/streamable-http"
    }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json` (adjust name and port for your IDE):

```json
{
  "mcpServers": {
    "intellij-idesense": {
      "serverUrl": "http://127.0.0.1:29170/mcp/streamable-http"
    }
  }
}
```

### VS Code (Generic MCP)

```json
{
  "mcp.servers": {
    "intellij-idesense": {
      "url": "http://127.0.0.1:29170/mcp/streamable-http"
    }
  }
}
```

> **Note**: Replace the server name and port with your IDE's defaults. See [IDE-Specific Defaults](#ide-specific-defaults) below.

### IDE-Specific Defaults

Each JetBrains IDE has a unique default port and server name to allow running multiple IDEs simultaneously without conflicts:

| IDE | Server Name | Default Port |
|-----|-------------|--------------|
| IntelliJ IDEA | `intellij-idesense` | 29170 |
| Android Studio | `android-studio-idesense` | 29171 |
| PyCharm | `pycharm-idesense` | 29172 |
| WebStorm | `webstorm-idesense` | 29173 |
| GoLand | `goland-idesense` | 29174 |
| PhpStorm | `phpstorm-idesense` | 29175 |
| RubyMine | `rubymine-idesense` | 29176 |
| CLion | `clion-idesense` | 29177 |
| RustRover | `rustrover-idesense` | 29178 |
| DataGrip | `datagrip-idesense` | 29179 |

> **Tip**: Use the "Install on Coding Agents" button in the tool window - it automatically uses the correct server name and port for your IDE.
>
> **Note**: The full IDE port list (including Aqua, DataSpell, and Rider) is documented in [ARCHITECTURE.md](docs/ARCHITECTURE.md#ide-specific-defaults). Rider has a port entry but is currently marked incompatible in the plugin manifest and is not supported.

## Multi-Project Support

When multiple projects are open in a single IDE window, you must specify which project to use with the `project_path` parameter:

```json
{
  "name": "ide_find_usages",
  "arguments": {
    "project_path": "/Users/dev/myproject",
    "file": "src/Main.kt",
    "line": 10,
    "column": 5
  }
}
```

If `project_path` is omitted:
- **Single project open**: That project is used automatically
- **Multiple projects open**: An error is returned with the list of available projects

### Workspace Projects

The plugin supports **workspace projects** where a single IDE window contains multiple sub-projects as modules with separate content roots. The `project_path` parameter accepts:

- The **workspace root** path
- A **sub-project path** (module content root)
- A **subdirectory** of any open project

When an error occurs, the response returns `available_projects`. By default this includes workspace sub-projects so AI agents can discover valid module content roots. If you want smaller error payloads, switch **Project list in error responses** to **Compact** in plugin settings to return only top-level project roots.

## Tool Window

The plugin adds an "IdeSense" tool window (bottom panel) that shows:

- **Server Status**: Running indicator with server URL and port
- **Project Name**: Currently active project
- **Command History**: Log of all MCP tool calls with:
  - Timestamp
  - Tool name
  - Status (Success/Error/Pending)
  - Parameters and results (expandable)
  - Execution duration

### Tool Window Actions

| Action | Description |
|--------|-------------|
| Refresh | Refresh server status and command history |
| Copy URL | Copy the MCP server URL to clipboard |
| Clear History | Clear the command history |
| Export History | Export history to JSON or CSV file |
| **Install on Coding Agents** | Install MCP server on AI assistants (prominent button on right) |

## Error Codes

### JSON-RPC Standard Errors

| Code | Name | Description |
|------|------|-------------|
| -32700 | Parse Error | Failed to parse JSON-RPC request |
| -32600 | Invalid Request | Invalid JSON-RPC request format |
| -32601 | Method Not Found | Unknown method name |
| -32602 | Invalid Params | Invalid or missing parameters |
| -32603 | Internal Error | Unexpected internal error |

### Tool Errors (resolved tool failures)

Pre-dispatch failures (parse error, unknown method, missing params) use JSON-RPC numeric error objects. Once a tool is dispatched and fails, it returns a **normal MCP result** with `isError: true` and a structured payload:

```json
{
  "error": "<snake_case_code>",
  "message": "<human-readable description>"
}
```

Common `error` codes:

| Code | When It Occurs |
|------|----------------|
| `index_not_ready` | IDE is in dumb mode (indexing in progress) |
| `file_not_found` | Specified file does not exist |
| `symbol_not_found` | No symbol found at the specified position |
| `refactoring_conflict` | Refactoring cannot be completed (e.g., name conflict) |
| `invalid_arguments` | Parameter validation failed (includes a `violations` array) |
| `tool_error` | Generic tool failure |
| `internal_error` | Unexpected server error |
| `no_project_open` / `project_not_found` / `multiple_projects_open` | Project resolution errors |

## Settings

Configure the plugin at <kbd>Settings</kbd> > <kbd>Tools</kbd> > <kbd>IdeSense</kbd>:

| Setting | Default | Description |
|---------|---------|-------------|
| Server Port | IDE-specific | MCP server port (range: 1024-65535, auto-restart on change). See [IDE-Specific Defaults](#ide-specific-defaults) |
| Server Host | `127.0.0.1` | Listening host. Change to `0.0.0.0` for remote/WSL access |
| Max History Size | 100 | Maximum number of commands to keep in history |
| Project List in Error Responses | Expanded | Controls `available_projects` detail for invalid/missing `project_path` errors. `Expanded` includes workspace sub-projects; `Compact` returns only top-level project roots |
| Sync External Changes | false | Sync external file changes before operations (**WARNING: significant performance impact**) |
| Disabled Tools | 11 tools | Per-tool enable/disable toggles. Some tools are disabled by default to keep the tool list focused |
| Response Format | `JSON` | Format for tool result text content block: `JSON` (default) mirrors the structured JSON; `TOON` converts it to a compact text-object notation for older clients |

## Community Integrations

- [opencode-jetbrains-index](https://github.com/ineersa/opencode-jetbrains-index) - a third-party integration for OpenCode that uses this plugin

> **Disclaimer**: This repository is not maintained by me. Please use its own issue tracker for integration-specific issues and support.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for build instructions, the dev loop, testing guidelines, and the PR checklist.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

IdeSense started as a fork of [jetbrains-index-mcp-plugin](https://github.com/hechtcarmel/jetbrains-index-mcp-plugin) by Carmel Hecht, and builds on the [IntelliJ Platform Plugin Template](https://github.com/JetBrains/intellij-platform-plugin-template).
