# Captured ground truth: laravel-framework

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **laravel-framework: a macro has no declaration.** The test adds the method `everyXMinutes`
  to `Event` with `Event::macro('everyXMinutes', ...)` (`tests/Console/Scheduling/FrequencyTest.php:230`).
  Go to Declaration (Ctrl+B) on `everyXMinutes` at line 234, column 56 of the same file does
  not move the caret (PhpStorm 2026.3, window observation). `def-everyXMinutes-macro` gives
  the error "Could not resolve symbol definition". It is an expected-error row: it needs the
  two-step bless with `--bless-errors --tool ide_find_definition`. The same as lychee.
- **laravel-framework: a trait has no implementation.** `impls-Macroable-trait` is empty. Go to
  Implementation on the trait `Macroable` says "No implementations found". The inlay of
  PhpStorm on the trait says "used by 80".
- **laravel-framework: anonymous classes.** `impls-ShouldQueue` has 158 implementations, as
  Choose Implementation ("158 found") and the inlay "158 implementations" of PhpStorm. 8 of them
  are anonymous classes in `tests/`, each with an empty `name` and the namespace with a
  trailing `\` as its `qualifiedName`. The same as in phpunit and lychee.
- **laravel-framework: the `@method` tags of a facade.** `file-structure-Cache.php-ide-default-view`
  has one entry for each `@method` tag of the class doc comment of
  `src/Illuminate/Support/Facades/Cache.php`, with the default values of the parameters
  (`= null`, `= [...]`). The Structure window of PhpStorm shows the same entries. The row is a
  `shape` row, because the entries hold source text.
- **laravel-framework: callers in a bundled plugin and closures.** Call Hierarchy (callers) of
  `Arr::pull` (`src/Illuminate/Collections/Arr.php:941:28`) has 19 callers at depth 1. One of
  them is the file `.phpstorm.meta.php` in the jar of the Laravel Idea plugin that PhpStorm
  2026.3 bundles (`laravel-idea-13.4.1.261.jar`, kind `SYMBOL`). Three are closures, each with an
  empty `name` and the namespace with a trailing `\` as its `qualifiedName`. The Callers window
  of PhpStorm (scope "All") shows the same 19 entries: the meta file with its path in the
  PhpStorm installation, and each closure with no name. No row pins this result, because the
  path of the meta file changes with each update of the bundled plugin. The row
  `hier-caller-Arr.random-d2` has only callers in the product.
- **laravel-framework: the default view of the Structure window.** The four
  `file-structure-*-ide-default-view` rows give `show: ["constants", "includes",
  "private_members", "properties", "protected_members"]`. This is the default view of the
  Structure window of PhpStorm 2026.3: in its view options, "Anonymous Classes", "Inherited" and
  "Lambdas" are off, and "Show Constants", "Show Includes", "Show Private Members", "Show
  Properties" and "Show Protected Members" are on. The File Structure popup has the check boxes
  "Inherited members", "Anonymous Classes" and "Lambdas", all off. Since #341 the default `show`
  of the tool for PHP is the same list, so a call with no `show` gives the same outline. Before
  it, the default also had `lambdas`, and the outline had the `Lambda(...)` nodes that the
  window hides.
- **laravel-framework: the file rows equal Go to File.** `canary-find-file-Carbon.php`,
  `find-file-Repository.php` and `find-file-model.stub` give the same set of files as Go to File
  of PhpStorm 2026.3 (tab "Files", scope "Project Files"): 2, 28 and 5 files. The order of the
  files in the window differs, but an `exact` row sorts its lists, so the row does not pin the
  order.
- **laravel-framework: a YAML value has the label `STRING_LITERAL`.** Line 39 of
  `.github/workflows/tests.yml` and line 4 of `docker-compose.yml` (`image:
  amazon/dynamodb-local:2.0.0`) hold a plain scalar value of YAML. `search-text-dynamodb` and
  `search-text-dynamodb-strings` give them the label `STRING_LITERAL`, and `context: "strings"`
  returns them. PhpStorm PS-263.7307.215, in a project that holds copies of these files, with
  "Match case" and "Words": Find in Files lists them with "In String Literals" and not with
  "Except Comments and String Literals". The Find tool window has them below "Unclassified".
  For such a line the filter and the group of the IDE differ, and the label follows the
  filter (see "`ide_search_text`: one match for each line, and the context filter" in
  `docs/ARCHITECTURE.md`). The key lines `dynamodb:` (line 38 of the workflow file and line 3
  of the other file) have the label `CODE`.
- **laravel-framework: parked rows.** Each of these rows shows an open defect (see "Parked
  rows" in `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `usage-Arr.accessible`, `usage-Arr.accessible-production-scope`, `usage-Arr.accessible-test-scope`, `usage-Cache.remember-method-tag` | #307 | the column of a PHP method call is the start of the call expression (the receiver), not the method name that Find Usages goes to |
  | `search-text-dynamodb-code` | #181 | `context: "code"` returns PHP string and comment matches |
  | `find-file-Carbon.php-libraries-scope` | #271 | the tool gives 21 files; Go to File (scope "Project and Libraries") also gives the files that match through the directory path, for example the locale files below `vendor/nesbot/carbon/src/Carbon/Lang/` |
