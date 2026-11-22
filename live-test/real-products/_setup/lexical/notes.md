# lexical

- Repository: https://github.com/meta/lexical
- Pin: tag `v0.50.0`, commit `02cb51fe9e7390ee83542899c4c00c58c68c9c09`, committed 2026-09-02.
- License: MIT (`LICENSE`)
- IDE: WebStorm (port 29173), fixture languages JavaScript and TypeScript
- Node.js: `engines.node` is `>=20.19.0` in `package.json`. The field `packageManager` names
  `pnpm@11.24.0`. The bootstrap ran with Node.js 24.16.0 and pnpm 11.24.0 through corepack.
- The checkout has 2,300 tracked files: 1,139 TypeScript files, 229 JavaScript files and 140
  Markdown files.
- Languages: TypeScript and TSX (React), and Flow stubs. `packages/` holds 38 packages. Each
  package has a `flow/` folder with Flow declarations of its API: 102 `.js.flow` files in the
  checkout. WebStorm gives these files the language "Flow JS", not "JavaScript".
- The root `tsconfig.json` has 174 entries in `paths`. They map each package name (`lexical`,
  `@lexical/react/LexicalComposerContext` and the others) to the sources in `packages/`.
- `pnpm-workspace.yaml` names `packages/*` and `dev-examples/*` (5 folders). It excludes
  `examples/**` and `scripts/__tests__/integration/fixtures/**`. It sets `engineStrict: true`
  and `minimumReleaseAge: 10080`.
- `examples/` holds 21 example applications (430 files). Each has its own `package.json`,
  and `examples/node-replacement` has its own `pnpm-workspace.yaml`. The install gives them no
  `node_modules/`, and their `tsconfig.json` files have no `paths`. So an import of `lexical`
  in `examples/` has no package to resolve to.
- TypeScript declaration merging gives two declarations for some names: `DecoratorNode`
  (an interface at line 23 and a class at line 30 of `LexicalDecoratorNode.ts`),
  `ElementNode` (114 and 121) and `TextNode` (304 and 328). The Flow stubs declare most API
  names one more time (for example `ParagraphNode` in `packages/lexical/flow/Lexical.js.flow`).
  So a symbol name often has two or more declarations (#269).

## Setup

Run `bootstrap.sh`. It needs `node` 20.19 or later with `corepack` on the `PATH`. It needs no
global install of pnpm and no `corepack enable`.

- `pnpm-lock.yaml` is committed (lockfile version 9.0, 2,709 entries, 44 importers).
  `--frozen-lockfile` refuses each change of it.
- `--ignore-scripts` runs no script of the product and no install script of a package.
- pnpm puts each package into the store of the user and links it into `node_modules/.pnpm/`
  of the checkout with hardlinks. The install writes these folders outside the checkout:

  | Folder | Size | Content |
  |---|---|---|
  | `~/.local/share/pnpm/store/v11` | 1.7 GB | the store of the packages |
  | `~/.cache/pnpm` | 617 MB | the metadata cache and `lockfile-verified.jsonl` |
  | `~/.cache/node/corepack/v1/pnpm/11.24.0` | 21 MB | pnpm itself (corepack) |
  | `~/.local/state/pnpm/pnpm-state.json` | 56 bytes | the time of the last update check of pnpm |

- The checkout has 28 MB, and 1.7 GB with `node_modules/` (2,571 packages). The new data of
  the first install was about 2.45 GB.
- pnpm checks the release age of each lockfile entry (`minimumReleaseAge`): "Lockfile passes
  supply-chain policies (2709 entries in 21.8s)". This check needs the network.
- WebStorm restores a project at its start only when the folder has IDE project files. The
  module file holds what WebStorm itself writes at the first open of this folder: one content
  root with no source folder, no test folder and no excluded folder. Evidence: on 2026-11-22 a
  WebStorm 2026.3 (WS-263.7307.202) with a window opened a copy of the pin with no `.idea`
  folder. Its module file and `modules.xml` were equal to the files of the bootstrap, except
  the module name (the folder name) and the final newline. WebStorm adds `node_modules/` as a
  library root by itself at each open.
- So the project has no source root and no test root. `ide_find_usages` and `ide_find_file`
  with `project_production_files` or `project_test_files` give `scope_matches_no_files`.
  `ide_type_hierarchy` with these scopes gives the full result (43 subtypes of
  `DecoratorNode`, the same as with no scope). `ide_call_hierarchy` with
  `project_production_files` gives 0 calls.
- Times: the first bootstrap run took 23.8 s (22.7 s of it is the pnpm install). A second
  run took 0.65 s and changed no file.

## Import

Fleet WebStorm 2026.3 (WS-263.7307.202), plugin 2.1.1-dev.31, 2026-11-22.

| Value | Measured |
|---|---|
| Switch time, first open | 11 s; ready 0 s |
| `node_modules` library root added | 15.7 s after the IDE start (`NodeModulesDirectoryManager - Contributed`, 38,107 files); it grew to 43,188 files at 45.4 s |
| First index build | "Unindexed files update took 25142ms" (On project open); dumb mode ended 46.5 s after the IDE start |
| Resident memory after the first open | 3.60 GiB; 3.15 GiB after a full collection |
| Used heap after a full collection | 364 MB (`jcmd GC.run`, `GC.heap_info`; limit 2,048 MB) |
| Resident memory at the end of the onboarding | 4.18 GiB, 2 h after the first open, in the same IDE session: after all runs of the rows, the bless and the fixture runs of JavaScript and TypeScript |
| One run of all rows | 3 s to 10 s |

The harness reports "ready 0s" before the library root and the dumb pass of the index build
come. Wait for the quiet state before the first row.

## Library files in the expected rows

The dependency files of the rows are in `node_modules/.pnpm/` of the checkout. The folder
names of the rows are `<name>@<version>` with no suffix. Some other folders there have a
suffix after `_` with a hash (for example `@docsearch+react@4.3.2_…`); no row uses such a
folder. Evidence: a second clean install of the same lockfile into a copy gave the same 2,573
folder names below `node_modules/.pnpm/`.

| Row | File | Lock entry |
|---|---|---|
| `canary-def-Doc-into-dependency` | `node_modules/.pnpm/yjs@13.6.31/node_modules/yjs/dist/src/utils/Doc.d.ts` | `yjs@13.6.31` (the only version of yjs in the lockfile) |
| `def-lazy-into-types-react` | `node_modules/.pnpm/@types+react@19.2.14/node_modules/@types/react/index.d.ts` | `'@types/react@19.2.14'`; the lockfile has 4 versions, and the root importer `.` pins 19.2.14 |
| `find-class-Doc-libraries-scope` | the `Doc` declarations of `prettier@3.8.1`, `yjs@13.6.31`, `zod@4.4.2` and `zod@4.4.3` | `prettier@3.8.1` (an `overrides` entry), `yjs@13.6.31`, `zod@4.4.2`, `zod@4.4.3` |

## Call hierarchy times

The call hierarchy of `$createImageNode` (`ImageNode.tsx:320`) at depth 2 took 24.0 s at its
first call (fleet, 17:13:57) and gave 200 nodes with `truncated: true`. At depth 1 it took
0.07 s (11 callers). The depth 2 row uses `$isCaptionEditorEmpty` (`ImageNode.tsx:102`)
instead: 2.27 s at its first call, 15 nodes.
