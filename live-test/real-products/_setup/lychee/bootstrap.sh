#!/usr/bin/env bash
# Prepare the lychee checkout for PhpStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../lychee" && pwd)
if ! command -v php >/dev/null; then
  echo "lychee needs php on the PATH for composer (any PHP 7.2.5 or later)" >&2; exit 1
fi
# composer: `composer` from the PATH, else the composer.phar of the mise tool github:composer/composer.
if command -v composer >/dev/null; then
  composer=(composer)
elif dir=$(mise where github:composer/composer 2>/dev/null) && [ -f "$dir/composer.phar" ]; then
  composer=(php "$dir/composer.phar")
else
  echo "lychee needs composer 2 on the PATH (https://getcomposer.org/download/)" >&2; exit 1
fi
have=$("${composer[@]}" --version 2>/dev/null | sed -n 's/^Composer version \([0-9]*\)\..*/\1/p')
if [ "$have" != 2 ]; then
  echo "lychee needs composer 2, found '$have' (${composer[*]})" >&2; exit 1
fi
for tool in node npm; do
  if ! command -v "$tool" >/dev/null; then
    echo "lychee needs $tool on the PATH (the product names no Node.js version)" >&2; exit 1
  fi
done
# composer.lock is committed, and install never writes it. Four packages come from the VCS
# repositories of composer.json; the lock pins each one to a commit. The product needs PHP 8.4
# and eleven extensions; --ignore-platform-reqs skips the check of the PHP of this machine.
# PhpStorm needs no interpreter to index. --no-scripts runs no script of the product (artisan),
# and --no-plugins loads no composer plugin. The packages go to vendor/ in the checkout.
(cd "$product" && "${composer[@]}" install --ignore-platform-reqs --no-scripts --no-plugins \
  --no-interaction --no-progress --quiet)
# package-lock.json is committed, and npm ci never writes it. --ignore-scripts runs no script
# of the product and no install script of a package: the IDE reads the sources of the packages
# only. The packages go to node_modules/ in the checkout. npm ci removes node_modules/ first,
# so it runs only when the lockfile differs from the one of the last install.
lock=$(sha256sum "$product/package-lock.json" | cut -d' ' -f1)
stamp="$product/node_modules/.bootstrap-lock.sha256"
if [ "$(cat "$stamp" 2>/dev/null)" != "$lock" ]; then
  (cd "$product" && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error)
  printf '%s\n' "$lock" > "$stamp"
fi
# PhpStorm restores a project at its start only when the folder has IDE project files. These
# files make the model that PhpStorm 2026.3 writes at the first open of the folder:
# - the source roots of the composer autoload: app as a source root, and the autoload-dev
#   folders database/factories, phpstan, scripts and tests as test roots (tests two times, one
#   time with no package prefix);
# - vendor/composer and the folder of each composer package excluded, except
#   vendor/jetbrains/phpstorm-stubs: PhpStorm removes that package from the include path and
#   does not exclude it. At each open, the composer sync of PhpStorm puts the other package
#   folders on the PHP include path, so they are libraries. A restore does not exclude them by
#   itself;
# - six folders of the Laravel framework excluded;
# - the language level 8.4 and the check of the used language features turned off. At the
#   first open that check sets 8.5; at a later open, with the check turned off, the composer
#   sync sets the level from composer.json ("php": "^8.4"), and PhpStorm uses 8.4.
# PhpStorm adds node_modules/ as a library root by itself at each open.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/lychee.iml" filepath="$PROJECT_DIR$/.idea/lychee.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/lychee.iml" ]; then
  python3 -I - "$product" > "$idea/lychee.iml" <<'PY'
import json, os, sys
root = sys.argv[1]
with open(os.path.join(root, "vendor/composer/installed.json")) as f:
    packages = json.load(f)["packages"]
excluded = {"vendor/composer", "bootstrap/cache", "storage/app", "storage/bootstrap",
            "storage/debugbar", "storage/framework", "storage/tmp"}
for p in packages:
    if p.get("install-path") is None:  # a metapackage has no folder
        continue
    path = os.path.normpath("vendor/composer/" + p["install-path"])
    if not path.startswith("vendor/composer/") and path != "vendor/jetbrains/phpstorm-stubs":
        excluded.add(path)
print('<?xml version="1.0" encoding="UTF-8"?>')
print('<module type="WEB_MODULE" version="4">')
print('  <component name="NewModuleRootManager">')
print('    <content url="file://$MODULE_DIR$">')
print('      <sourceFolder url="file://$MODULE_DIR$/app" isTestSource="false" packagePrefix="App\\" />')
print('      <sourceFolder url="file://$MODULE_DIR$/database/factories" isTestSource="true" packagePrefix="Database\\Factories\\" />')
print('      <sourceFolder url="file://$MODULE_DIR$/phpstan" isTestSource="true" packagePrefix="PHPStan\\" />')
print('      <sourceFolder url="file://$MODULE_DIR$/scripts" isTestSource="true" packagePrefix="Scripts\\" />')
print('      <sourceFolder url="file://$MODULE_DIR$/tests" isTestSource="true" />')
print('      <sourceFolder url="file://$MODULE_DIR$/tests" isTestSource="true" packagePrefix="Tests\\" />')
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
echo "lychee: ready"
