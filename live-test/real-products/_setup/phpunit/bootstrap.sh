#!/usr/bin/env bash
# Prepare the phpunit checkout for PhpStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../phpunit" && pwd)
if ! command -v php >/dev/null; then
  echo "phpunit needs php on the PATH for composer (any PHP 7.2.5 or later)" >&2; exit 1
fi
# composer: `composer` from the PATH, else the composer.phar of the mise tool github:composer/composer.
if command -v composer >/dev/null; then
  composer=(composer)
elif dir=$(mise where github:composer/composer 2>/dev/null) && [ -f "$dir/composer.phar" ]; then
  composer=(php "$dir/composer.phar")
else
  echo "phpunit needs composer 2 on the PATH (https://getcomposer.org/download/)" >&2; exit 1
fi
have=$("${composer[@]}" --version 2>/dev/null | sed -n 's/^Composer version \([0-9]*\)\..*/\1/p')
if [ "$have" != 2 ]; then
  echo "phpunit needs composer 2, found '$have' (${composer[*]})" >&2; exit 1
fi
# composer.lock is committed, and install never writes it. The product needs PHP 8.4.1 and six
# extensions; --ignore-platform-reqs skips the check of the PHP of this machine. PhpStorm needs
# no interpreter to index. The packages go to vendor/ in the checkout.
(cd "$product" && "${composer[@]}" install --ignore-platform-reqs --no-interaction --no-progress --quiet)
# PhpStorm restores a project at its start only when the folder has IDE project files. These
# files make the model that PhpStorm writes at the first open of the folder: one module with no
# source root and no test root (the autoload is classmap), and the package folders of the three
# composer roots excluded. At each open, composer sync of PhpStorm puts the same package folders
# on the PHP include path, so they are libraries. A restore does not exclude them by itself.
# composer sync also sets the language level from composer.json (8.4). At a first open, a check
# of the used features can raise it to 8.5 first (one test file uses the pipe operator), so
# php.xml fixes 8.4 and turns that check off.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/phpunit.iml" filepath="$PROJECT_DIR$/.idea/phpunit.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/phpunit.iml" ]; then
  python3 -I - "$product" > "$idea/phpunit.iml" <<'PY'
import json, os, sys
root = sys.argv[1]
excluded = []
for vendor in ("vendor/", "build/scripts/phar-set-timestamps/vendor/", "tools/.phpstan/vendor/"):
    with open(os.path.join(root, vendor, "composer/installed.json")) as f:
        packages = json.load(f)["packages"]
    excluded.append(vendor + "composer")
    excluded += [os.path.normpath(vendor + "composer/" + p["install-path"]) for p in packages]
print('<?xml version="1.0" encoding="UTF-8"?>')
print('<module type="WEB_MODULE" version="4">')
print('  <component name="NewModuleRootManager">')
print('    <content url="file://$MODULE_DIR$">')
for path in sorted(excluded):
    print('      <excludeFolder url="file://$MODULE_DIR$/%s" />' % path)
print('    </content>')
print('    <orderEntry type="inheritedJdk" />')
print('    <orderEntry type="sourceFolder" forTests="false" />')
print('  </component>')
print('</module>')
PY
fi
if [ ! -f "$idea/php.xml" ]; then
  cat > "$idea/php.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="PhpProjectSharedConfiguration" php_language_level="8.4">
    <option name="suggestChangeDefaultLanguageLevel" value="false" />
  </component>
</project>
XML
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "phpunit: ready"
