#!/usr/bin/env bash
# Prepare the laravel-framework checkout for PhpStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../laravel-framework" && pwd)
if ! command -v php >/dev/null; then
  echo "laravel-framework needs php on the PATH for composer (any PHP 7.2.5 or later)" >&2; exit 1
fi
# composer: `composer` from the PATH, else the composer.phar of the mise tool github:composer/composer.
if command -v composer >/dev/null; then
  composer=(composer)
elif dir=$(mise where github:composer/composer 2>/dev/null) && [ -f "$dir/composer.phar" ]; then
  composer=(php "$dir/composer.phar")
else
  echo "laravel-framework needs composer 2 on the PATH (https://getcomposer.org/download/)" >&2; exit 1
fi
have=$("${composer[@]}" --version 2>/dev/null | sed -n 's/^Composer version \([0-9]*\)\..*/\1/p')
if [ "$have" != 2 ]; then
  echo "laravel-framework needs composer 2, found '$have' (${composer[*]})" >&2; exit 1
fi
# The version of the root package is the pin. Packages that require laravel/framework (for
# example orchestra/testbench-core) resolve against it.
export COMPOSER_ROOT_VERSION=13.25.0
# The product needs PHP 8.3 and seven extensions; --ignore-platform-reqs skips the check of the
# PHP of this machine. PhpStorm needs no interpreter to index. --no-scripts runs no script of the
# product, and --no-plugins loads no composer plugin.
flags=(--ignore-platform-reqs --no-scripts --no-plugins --no-interaction --no-progress)
# Upstream has no lockfile: its .gitignore ignores composer.lock. The composer.lock next to this
# script pins the dependencies. When it is absent, the bootstrap makes it one time from
# composer.json and keeps it here. Composer has no option for a date limit, so the bootstrap
# checks the release time of each locked package: a package released at or after $before gets
# the constraint "lower than the locked version", and composer resolves again.
kept="$here/composer.lock"
before=2026-11-20T00:00:00+00:00
if [ ! -f "$kept" ]; then
  with=$(mktemp)
  trap 'rm -f "$with"' EXIT
  while :; do
    mapfile -t args < <(sed 's/^/--with=/' "$with")
    rm -f "$product/composer.lock"
    (cd "$product" && "${composer[@]}" update --no-install --no-audit --quiet "${flags[@]}" \
      ${args[@]+"${args[@]}"})
    rc=0
    python3 -I - "$product/composer.lock" "$before" "$with" <<'PY' || rc=$?
import json, sys
from datetime import datetime
lock, before, path = sys.argv[1], datetime.fromisoformat(sys.argv[2]), sys.argv[3]
with open(lock) as f:
    data = json.load(f)
young = {p["name"]: "<" + p["version"] for p in data["packages"] + data["packages-dev"]
         if datetime.fromisoformat(p["time"]) >= before}
with open(path) as f:
    constraints = dict(line.strip().split(":", 1) for line in f if line.strip())
constraints.update(young)
with open(path, "w") as f:
    f.writelines("%s:%s\n" % item for item in sorted(constraints.items()))
sys.exit(3 if young else 0)
PY
    case $rc in 0) break ;; 3) continue ;; *) exit 1 ;; esac
  done
  cp "$product/composer.lock" "$kept"
fi
# composer install reads the lockfile only in the product folder. The product ignores
# composer.lock, so the copy is no tracked file. install never writes the lockfile. The packages
# go to vendor/ in the checkout.
cmp -s "$kept" "$product/composer.lock" || cp "$kept" "$product/composer.lock"
(cd "$product" && "${composer[@]}" install --quiet "${flags[@]}")
# PhpStorm restores a project at its start only when the folder has IDE project files. These
# files make the model that PhpStorm 2026.3 writes at the first open of the folder:
# - a source root for each PSR-4 entry of each composer.json of the product (the root, the 37
#   components below src/Illuminate and the two fixtures below tests/Foundation/fixtures), with
#   its namespace as the package prefix. autoload-dev entries are test roots. An entry with an
#   empty folder keeps the trailing slash of its URL, and each other entry loses it;
# - vendor/composer and the folder of each composer package excluded. At each open, the
#   composer sync of PhpStorm puts the package folders on the PHP include path, so they are
#   libraries. A restore does not exclude them by itself;
# - the language level 8.3, which the composer sync sets from composer.json ("php": "^8.3").
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/laravel-framework.iml" filepath="$PROJECT_DIR$/.idea/laravel-framework.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/laravel-framework.iml" ]; then
  python3 -I - "$product" > "$idea/laravel-framework.iml" <<'PY'
import json, os, sys
root = sys.argv[1]
folders = set()
for top, dirs, files in os.walk(root):
    dirs[:] = sorted(d for d in dirs if top != root or d not in (".git", ".idea", "vendor"))
    if "composer.json" not in files:
        continue
    base = os.path.relpath(top, root)
    with open(os.path.join(top, "composer.json")) as f:
        data = json.load(f)
    for section, test in (("autoload", "false"), ("autoload-dev", "true")):
        for prefix, paths in data.get(section, {}).get("psr-4", {}).items():
            for path in paths if isinstance(paths, list) else [paths]:
                url = path if base == "." else base + "/" + path
                folders.add((url.rstrip("/") if path else url, test, prefix))
with open(os.path.join(root, "vendor/composer/installed.json")) as f:
    packages = json.load(f)["packages"]
excluded = {"vendor/composer"}
for p in packages:
    if p.get("install-path") is None:  # a metapackage has no folder
        continue
    path = os.path.normpath("vendor/composer/" + p["install-path"])
    if not path.startswith("vendor/composer/"):
        excluded.add(path)
print('<?xml version="1.0" encoding="UTF-8"?>')
print('<module type="WEB_MODULE" version="4">')
print('  <component name="NewModuleRootManager">')
print('    <content url="file://$MODULE_DIR$">')
for url, test, prefix in sorted(folders):
    print('      <sourceFolder url="file://$MODULE_DIR$/%s" isTestSource="%s" packagePrefix="%s" />'
          % (url, test, prefix))
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
  <component name="PhpProjectSharedConfiguration" php_language_level="8.3" />
</project>
XML
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "laravel-framework: ready"
