# IdeSense

![Build](https://github.com/vcth4nh/idesense/workflows/Build/badge.svg)

A JetBrains IDE plugin that exposes an **MCP (Model Context Protocol) server**, giving AI coding assistants like Claude, Codex, Cursor, and Windsurf the IDE's code-analysis engines — indexing, navigation, and diagnostics — with no human interaction with the IDE required.

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/vcth4nh)

<!-- Plugin description -->
**IdeSense** is an MCP server for JetBrains IDEs (IntelliJ IDEA, PyCharm, WebStorm, GoLand, PhpStorm, RustRover, and more) that gives AI coding assistants the IDE's own code-analysis engines — indexing, navigation, cross-references, diagnostics — through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io), with no human-in-the-IDE interaction required. A minimal set of index-backed refactorings (rename, move file) is retained.

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
- **Explain Symbol** - Declaration, signature, documentation, supers, implementations and a usage summary in one call
- **Index Status** - Check if code intelligence is ready
- **Sync Files** - Make the IDE pick up files that were created, modified, or deleted outside it (e.g., by coding agents)
- **Find Class** - Fast class/interface search by name (exact by default; opt into camelCase/substring matching with `fuzzySearch`)
- **Find File** - Fast file search by name using IDE's file index
- **Symbol Search** - Find code symbols by name with IntelliJ Go to Symbol matching
- **Search Text** - Text search using IDE's pre-built word index
- **Read File** - Read file content by path or qualified name, including library sources (disabled by default)

**Extended Tools (Language-Aware)**
These tools give results for each language whose plugin is installed. Find Super Methods is listed only when the IDE has a plugin for one of its languages.
- **Type Hierarchy** - Explore class inheritance chains
- **Call Hierarchy** - Trace method/function call relationships
- **Find Implementations** - Discover interface/abstract implementations
- **Find Super Methods** - Navigate method override hierarchies
- **File Structure** - View hierarchical file structure like IDE's Structure view, including Markdown heading outlines

**Refactoring Tools**
- **Rename Refactoring** - Safe renaming with automatic related element renaming (getters/setters, overriding methods) - works across ALL languages, headless with the default strategies (disabled by default)
- **Move File** - Move a file to a new directory; the IDE also updates references, imports, and the package/namespace when its language plugin supports that for the file type (disabled by default)

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

- [Documentation](#documentation)
- [Available Tools](#available-tools)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Client Configuration](#client-configuration)
- [Multi-Project Support](#multi-project-support)
- [Tool Window](#tool-window)
- [Error Codes](#error-codes)
- [Settings](#settings)
- [Community Integrations](#community-integrations)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Available Tools

The plugin provides **20 MCP tools** — 15 enabled by default, 5 opt-in (toggle any tool in <kbd>Settings</kbd> > <kbd>Tools</kbd> > <kbd>IdeSense</kbd>). The matrix below shows per-language support and test status; for parameters, examples, and return shapes, see **[USAGE.md](docs/USAGE.md)**.

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
| `ide_explain_symbol` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Refactoring**

| Tool | Java | Kotlin | Python | JS | TS | Go | PHP | Rust |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `ide_refactor_rename` | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| `ide_move_file` | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |

**Project** — language-agnostic (operate on the project/IDE, not language-specific code)

| Tool | Java | Kotlin | Python | JS | TS | Go | PHP | Rust |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `ide_index_status` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_install_plugin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_restart` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_sync_files` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `ide_read_file` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> **Notes:**
> - Refactoring tools (`ide_refactor_rename`, `ide_move_file`) are supported but not yet live-tested here (⚠️).
> - `ide_search_text` is backed by the IDE's word index, so language keywords (e.g. Kotlin `fun`) may not be matched even though identifiers and most words are.

## Requirements

- **JetBrains IDE** 2025.3 or later (any IDE based on IntelliJ Platform)
- **JVM** 21 or later
- **MCP Protocol** 2025-11-25 (primary Streamable HTTP, negotiated; 2025-03-26 / 2024-11-05 also supported). Legacy SSE clients (2024-11-05) use `http://127.0.0.1:<port>/mcp/sse`.

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

IdeSense isn't on the JetBrains Marketplace yet. Install it from a release:

1. Download the plugin ZIP of the [latest release](https://github.com/vcth4nh/idesense/releases).
2. In the IDE, go to <kbd>Settings/Preferences</kbd> > <kbd>Plugins</kbd> > <kbd>⚙️</kbd> > <kbd>Install plugin from disk...</kbd> and select the ZIP.
3. Restart the IDE.

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
3. A popup appears with three sections:
   - **Install Now** - For Claude Code CLI and Codex CLI: Runs the installation command automatically
   - **Copy Configuration** - For Claude Code, Codex CLI, Gemini CLI and Cursor: Copies the command or config of that client to your clipboard
   - **Generic MCP Config** - For other clients: Copies a Streamable HTTP config or a Legacy SSE config to your clipboard
4. For "Copy Configuration" and "Generic MCP Config", paste the config into the appropriate config file

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
| Aqua | `aqua-idesense` | 29180 |
| DataSpell | `dataspell-idesense` | 29181 |
| Other IntelliJ-based IDE | `jetbrains-idesense` | 29199 |

> **Tip**: Use the "Install on Coding Agents" button in the tool window - it automatically uses the correct server name and port for your IDE.
>
> **Note**: Rider is not supported. The plugin manifest marks it incompatible.

## Multi-Project Support

When more than one project is open in the IDE, you must specify which project to use with the `project_path` parameter:

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

A `project_not_found` or `multiple_projects_open` error returns `available_projects`. By default this includes workspace sub-projects so AI agents can discover valid module content roots. If you want smaller error payloads, switch **Project list in error responses** to **Compact** in plugin settings to return only top-level project roots.

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
| Get Companion Skill | Install the companion skill into `.claude/skills/` in the project root, or save it as a `.skill` or `.zip` file |
| **Install on Coding Agents** | Install MCP server on AI assistants (prominent button on right) |

## Error Codes

The JSON-RPC error codes and the tool error codes are listed in [Error Handling](docs/USAGE.md#error-handling) in USAGE.md.

## Settings

Configure the plugin at <kbd>Settings</kbd> > <kbd>Tools</kbd> > <kbd>IdeSense</kbd>:

| Setting | Default | Description |
|---------|---------|-------------|
| Server Port | IDE-specific | MCP server port (range: 1024-65535, auto-restart on change). See [IDE-Specific Defaults](#ide-specific-defaults) |
| Server Host | `127.0.0.1` | Listening host. A non-loopback host (e.g. `0.0.0.0` for remote/WSL access) also requires **Allow non-loopback bind** — see below |
| Allow non-loopback bind | false | Acknowledges that binding a non-loopback host exposes every enabled tool — including full read access to your projects — to any machine that can reach the port, with **no authentication**. Without it, a non-loopback host falls back to `127.0.0.1` and the server keeps running |
| Max History Size | 100 | Maximum number of commands to keep in history |
| Project List in Error Responses | Expanded | Controls `available_projects` detail for invalid/missing `project_path` errors. `Expanded` includes workspace sub-projects; `Compact` returns only top-level project roots |
| Sync External Changes | false | Sync external file changes before operations (**WARNING: significant performance impact**) |
| Disabled Tools | 5 tools | Per-tool enable/disable toggles. Tools that modify code or the IDE — plus `ide_read_file` — are disabled by default |
| Response Format | `JSON` | Format for tool result text content block: `JSON` (default) mirrors the structured JSON; `TOON` writes the text block in Token-Oriented Object Notation. `structuredContent` stays JSON in both formats |

## Community Integrations

- [opencode-jetbrains-index](https://github.com/ineersa/opencode-jetbrains-index) - a third-party integration for OpenCode that uses this plugin

> **Disclaimer**: This repository is not maintained by me. Please use its own issue tracker for integration-specific issues and support.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for build instructions, the dev loop, testing guidelines, and the PR checklist.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

IdeSense started as a fork of [jetbrains-index-mcp-plugin](https://github.com/hechtcarmel/jetbrains-index-mcp-plugin) by Carmel Hecht, and builds on the [IntelliJ Platform Plugin Template](https://github.com/JetBrains/intellij-platform-plugin-template).
