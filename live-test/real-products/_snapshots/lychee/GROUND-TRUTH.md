# Captured ground truth: lychee

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.

- **lychee: the `configs()` macro has no declaration.** The product adds the method `configs()`
  to `Request` with `Request::macro('configs', ...)` (`app/Providers/AppServiceProvider.php:151`).
  PhpStorm does not resolve a call of it. Go to Declaration (Ctrl+B) on `configs` at
  `app/View/Components/Webshop.php:35:48` does not move the caret (PhpStorm 2026.3, window
  observation). `def-configs-macro` gives the error "Could not resolve symbol definition". It
  is an expected-error row: it needs the two-step bless with
  `--bless-errors --tool ide_find_definition`.
- **lychee: the usages of `ConfigManager::getValueAsBool`.** `usage-getValueAsBool-page1` and
  `-page2` (`app/Repositories/ConfigManager.php:108:18`) have `totalCollected` 263: 262 code
  usages on 259 lines and 1 `DYNAMIC` text match in `docs/`. Find Usages of PhpStorm shows
  "259 usages": the window shows one entry for each line, and 3 lines have 2 usages. Both miss
  the 201 calls on the result of the `configs()` macro (for example
  `request()->configs()->getValueAsBool(...)`), because the macro has no declaration (see the
  item above). The usage in `resources/views/vueapp.blade.php` has a wrong path (#186); it is
  in the count.
- **lychee: anonymous classes.** `hier-sub-BaseApiRequest` has 198 subtypes, as the inlay
  "198 inheritors" of PhpStorm says. Two of them are anonymous classes in `tests/`, each with
  an empty `name` and the namespace with a trailing `\` as its `qualifiedName`. The Type
  Hierarchy window shows them with no name, only the file. The same as in phpunit.
- **lychee: the PHP outline shows an initializer.** `file-structure-ConfigManager.php` has the
  line `protected cache: string[] = [...] (line 25)`. The Structure window of PhpStorm shows
  `cache: string[] = [...]` too.
- **lychee: a `@property` field.** `def-size_variants-magic-property` resolves to a
  `@property` tag of the class doc comment of `app/Models/Photo.php` (line 90), with the kind
  FIELD and the `qualifiedName` `\App\Models\Photo::@$size_variants`. The name comes from the
  `QualifiedNameProvider` of PHP, the same source as the names in phpunit.
- **lychee: parked rows.** Each of these rows shows an open defect (see "Parked rows" in
  `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `explain-Album-name`, `usage-Album-bysymbol`, `hier-super-Album-byname` | #269 | the name `Album` (3 PHP classes, 2 TypeScript types) resolves to the TypeScript interface, with no candidates |
  | `hier-caller-getValueAsBool-d1` | #186 | the caller in the Blade template has the path `/vueapp.blade.php` |
  | `search-text-favourite-code` | #181 | `context: "code"` returns PHP string and comment matches |
  | `search-text-favourite`, `search-text-favourite-strings` | #144 | line 153 of `docs/specs/3-reference/frontend-architecture.md`, a line of a code fence with the info string `typescript`, has the label `CODE`. The Find tool window lists it below "Usage in string constants": Find in Files gives the 42 lines of the tool, and with "In String Literals" 33 lines, where `context: "strings"` gives 32 |
