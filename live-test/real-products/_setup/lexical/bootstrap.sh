#!/usr/bin/env bash
# Prepare the lexical checkout for WebStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../lexical" && pwd)
for tool in node corepack; do
  if ! command -v "$tool" >/dev/null; then
    echo "lexical needs $tool on the PATH (Node.js 20.19 or later, with corepack)" >&2; exit 1
  fi
done
need=20.19.0  # engines.node in package.json
have=$(node --version | sed -n 's/^v\([0-9][0-9.]*\).*/\1/p')
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "lexical needs Node.js $need or later, found '$have'" >&2; exit 1
fi
# The product is a pnpm workspace: pnpm-workspace.yaml names packages/* and dev-examples/*, and
# the field packageManager of package.json names the pnpm version. Corepack of Node.js reads that
# field, gets this pnpm version into its own cache (COREPACK_HOME), and runs it. This needs no
# global install and no `corepack enable`. pnpm-lock.yaml is committed, and --frozen-lockfile
# refuses any change of it. --ignore-scripts runs no script of the product and no install script
# of a package: the IDE reads the sources of the packages only. pnpm puts each package into the
# store of the user (`pnpm store path`) and links it into node_modules/.pnpm/ of the checkout.
# The install runs only when the lockfile differs from the one of the last install.
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0 COREPACK_ENABLE_AUTO_PIN=0
lock=$(sha256sum "$product/pnpm-lock.yaml" | cut -d' ' -f1)
stamp="$product/node_modules/.bootstrap-lock.sha256"
if [ "$(cat "$stamp" 2>/dev/null)" != "$lock" ]; then
  (cd "$product" && corepack pnpm install --frozen-lockfile --ignore-scripts \
    --config.confirm-modules-purge=false --reporter=append-only)
  printf '%s\n' "$lock" > "$stamp"
fi
# WebStorm restores a project at its start only when the folder has IDE project files. The
# module file holds what WebStorm itself writes at the first open of this folder: one content
# root with no source folder, no test folder and no excluded folder. WebStorm adds node_modules/
# as a library root by itself at each open. The product ignores /.idea in its .gitignore.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/lexical.iml" filepath="$PROJECT_DIR$/.idea/lexical.iml" />
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
if [ "$(cat "$idea/lexical.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/lexical.iml"
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "lexical: ready (pnpm $(cd "$product" && corepack pnpm --version))"
