# Goal, scope and design principles

This file defines what IdeSense is for, what it does not do, and which rules decide the result
of a tool. It is for each maintainer, human or agent. A change of this file needs the word of
the owner of the repository.

[ARCHITECTURE.md](ARCHITECTURE.md) describes how the code follows these rules. The process is
in [CONTRIBUTING.md](CONTRIBUTING.md), and the rules of conduct for an agent are in
[AGENTS.md](../AGENTS.md).

## Goal

IdeSense gives a coding agent the code-analysis engines of a JetBrains IDE: the index,
navigation, cross-references and diagnostics. The agent calls them as the tools of an MCP
server. No person operates the IDE.

Two properties of the caller are the reason for the principles below:

- The caller wants the answer that a developer gets from the IDE. That answer comes from the
  syntax tree and the index of the project, which a text search does not have.
- The caller has no IDE window and no person to ask. It reads only the result of the tool.

## Scope

The mission is code analysis without a person at the IDE. The IDE does not edit, build or run
code for the agent.

- **In scope.** A tool that only reads is in scope. It answers from the index and the analysis
  of the IDE: search, navigation, hierarchies, file structure and diagnostics.
  `ide_diagnostics` also reports the last build and the open test runs, but it starts no
  build and no test. `ide_sync_files` changes no code. It makes the IDE read the changes that
  the agent made on the disk.
- **Kept on purpose.** Two refactorings that need the index stay: `ide_refactor_rename` and
  `ide_move_file`. They are off by default.
- **Plugin development loop.** `ide_install_plugin` and `ide_restart` install a build of a
  plugin in the IDE and load it. They are off by default.
- **Out of scope.** Three kinds of action are out of scope: editor interaction (open a file,
  read the active file), each other change of code (format, optimize imports, safe delete,
  convert a file), and the start of a build or of a run. Version 2.0.0 removed the seven
  tools of these kinds (see the entry of that version in [CHANGELOG.md](../CHANGELOG.md)).

A new tool that does more than read needs the word of the owner of the repository.

## Design principles

The principles decide what a tool returns and what it says. Principle 1 is the default method,
and principle 2 is how the code gets there. Principles 3 to 5 apply where the IDE relies on a
person or on a window, which the caller does not have.

Two terms need a definition. A row is one entry of a result list, for example one usage. The
fields `notes` and `warnings` of a result hold text for the calling agent. A result with pages
has them on its first page.

### 1. Mimic the IDE

This is the default method. Each tool returns what the action or the tool window of the IDE
shows for the same input. The table "Tool → backing mechanism" in
[ARCHITECTURE.md](ARCHITECTURE.md#tool--backing-mechanism) gives the mechanism behind each
tool and, where one exists, the IDE action that the tool follows.

- **Options.** To mimic the IDE includes, among other things, the options of the IDE. Where
  the IDE gives its user a choice, the tool gives the calling agent enough options to make
  that choice. Examples are a search scope, a filter, and an additional option that the IDE
  has for one language. Today the parameter `scope` selects one of the search scopes of the
  IDE, for example in `ide_find_usages`. The parameters `show` and `sort` of
  `ide_file_structure` select the filters and the sort order that the Structure view has for
  the language of the file. Issue #219 holds an open decision of the owner. The question is
  whether an option that changes the result set gets a default value or is a required
  parameter.
- **IDE versions.** When the behavior of the IDE changes with a new version, the tool follows
  the IDE. The code does not keep the old result.
- **Composed results.** `ide_explain_symbol` composes the results of several IDE actions in
  one answer. Each part follows the action that it comes from.
- **Deviations.** "Mimic the IDE" is the default, not an absolute. A tool can differ from the
  IDE on purpose when the result of the IDE would withhold information that is more useful to
  the calling agent. Each deviation needs the sign-off of the owner of the repository and an
  entry in "Where a tool differs from the IDE on purpose" in
  [ARCHITECTURE.md](ARCHITECTURE.md#where-a-tool-differs-from-the-ide-on-purpose). Principles
  3 and 4 are rules of the owner for two classes of such decisions.

### 2. Delegate to the platform

A tool calls the extension points and the presentation APIs that the IDE action uses. It does
not derive the behavior again for each language, so one implementation gives the result of
the IDE in each language. Code for one language is the last resort, where the platform has no
API for all languages. The result field `kind` of an element (for example `CLASS`, `STRUCT` or
`TRAIT`) is the main case, because the platform has no `PsiElement.getKind()`.

### 3. Marked false positives

A marked false positive is better than a false negative. In some cases the IDE relies on its
user. It asks a question before a search ("search the base method too?"), or it hides a class
of results by default (dynamic usages). A tool has no user to ask. In such a case the tool
takes the wider result and marks each row that is not a sure match. A sure match refers to
the symbol of the query itself. The response says what the tool added, in terms of the code.
A tool never leaves out such a row silently, and it never returns such a row without a mark.

`ide_find_usages` is the first tool that applies this rule (issues #171 and #196). Its marks
are `BASE`, `OVERRIDE` and `DYNAMIC`. [USAGE.md](USAGE.md#ide_find_usages) defines them, and
"Find Usages" in [ARCHITECTURE.md](ARCHITECTURE.md#find-usages) gives the mechanism.

### 4. No silent drop

When a tool leaves out rows that the search of the IDE returned, the response says so. The
first page of the result has a `notes` entry with the kind of the rows, their count and the
reason, in terms of the code. The kinds of rows that a tool leaves out today are in "Find
Usages" in [ARCHITECTURE.md](ARCHITECTURE.md#find-usages).

### 5. Text for the calling agent

A `notes` entry, a `warnings` entry and an error message speak in terms of the code: the
symbol, its position, the effect on the result. They name no dialog, question, button or
window of the IDE, because the calling agent has no IDE window. The reason for IDE parity goes
into `docs/USAGE.md`, the changelog, the GitHub issue and the code comments.

For example, `BaseDeclarationsNote.build` writes this note for a symbol with one base
declaration:

```text
'<symbol>' overrides or implements <base> (<path>:<line>:<column>). The result also holds the usages of this base declaration, because a call through it can run '<symbol>'. <n> of the <m> usages have match BASE.
```

A text such as "the tool answers Yes to the question of the IDE" names a question that the
agent never sees.
