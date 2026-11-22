#!/usr/bin/env bash
# Prepare the backstage checkout for WebStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../backstage" && pwd)
if ! command -v node >/dev/null; then
  echo "backstage needs node on the PATH (Node.js 22 or 24)" >&2; exit 1
fi
major=$(node --version | sed -n 's/^v\([0-9]*\)\..*/\1/p')
case "$major" in
  22|24) ;;  # engines.node in package.json: "22 || 24"
  *) echo "backstage needs Node.js 22 or 24, found '$(node --version)'" >&2; exit 1 ;;
esac
# The field packageManager of package.json names yarn@4.8.1, and .yarnrc.yml names the committed
# release .yarn/releases/yarn-4.8.1.cjs in yarnPath. Node.js runs that file directly: no download
# of yarn, no corepack, no global install. yarn.lock is committed, and --immutable refuses any
# change of it. No script may run: package.json has postinstall (husky) and prepare (husky), and
# a run of husky writes below .husky/ and sets core.hooksPath in the git configuration of the
# checkout. --mode=skip-build runs no build step, also not the postinstall of the root workspace;
# YARN_ENABLE_SCRIPTS=false turns the scripts of the packages off. The IDE reads the sources of the
# packages only. .yarnrc.yml sets nodeLinker node-modules and enableGlobalCache: yarn keeps each
# package in the cache of its global folder (~/.yarn/berry/cache) and copies it into node_modules/
# of the checkout. yarn links each workspace package (packages/*, plugins/*) into node_modules/
# with a symbolic link to its folder. YARN_ENABLE_TELEMETRY=0 sends no telemetry. The install runs
# only when the lockfile differs from the one of the last install.
export YARN_ENABLE_TELEMETRY=0 YARN_ENABLE_SCRIPTS=false YARN_ENABLE_PROGRESS_BARS=false
yarn=(node "$product/.yarn/releases/yarn-4.8.1.cjs")
lock=$(sha256sum "$product/yarn.lock" | cut -d' ' -f1)
stamp="$product/node_modules/.bootstrap-lock.sha256"
if [ "$(cat "$stamp" 2>/dev/null)" != "$lock" ]; then
  (cd "$product" && "${yarn[@]}" install --immutable --mode=skip-build)
  printf '%s\n' "$lock" > "$stamp"
fi
# WebStorm restores a project at its start only when the folder has IDE project files. The
# module file holds what WebStorm itself writes at the first open of this folder: one content
# root with no source folder, no test folder and no excluded folder. WebStorm adds node_modules/
# as a library root by itself at each open. The product ignores .idea/ in its .gitignore.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/backstage.iml" filepath="$PROJECT_DIR$/.idea/backstage.iml" />
    </modules>
  </component>
</project>
XML
fi
iml=$(cat <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module type="WEB_MODULE" version="4">
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$" />
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
)
if [ "$(cat "$idea/backstage.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/backstage.iml"
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
# The proof that husky did not run: no git hook setting and no hook folder.
if git -C "$product" config --get core.hooksPath >/dev/null || [ -e "$product/.husky/_" ]; then
  echo "a git hook setting or .husky/_ exists: a script of the product ran" >&2; exit 1
fi
echo "backstage: ready (yarn $(cd "$product" && "${yarn[@]}" --version))"
