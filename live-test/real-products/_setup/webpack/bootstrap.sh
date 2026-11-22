#!/usr/bin/env bash
# Prepare the webpack checkout for WebStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../webpack" && pwd)
for tool in node corepack; do
  if ! command -v "$tool" >/dev/null; then
    echo "webpack needs $tool on the PATH (Node.js 10.13 or later, with corepack)" >&2; exit 1
  fi
done
need=10.13.0  # engines.node in package.json
have=$(node --version | sed -n 's/^v\([0-9][0-9.]*\).*/\1/p')
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "webpack needs Node.js $need or later, found '$have'" >&2; exit 1
fi
# The field packageManager of package.json names yarn 1.22.22 with its hash. Corepack of Node.js
# reads that field, gets this yarn version into its own cache (COREPACK_HOME), checks the hash and
# runs it. This needs no global install and no `corepack enable`. yarn.lock is committed, and
# --frozen-lockfile refuses any change of it. --ignore-scripts runs no script of the product (it
# has `prepare`) and no install script of a package: the IDE reads the sources of the packages
# only. The .yarnrc of the product sets ignore-engines. yarn keeps each package in its cache
# (`yarn cache dir`) and copies it into node_modules/ of the checkout. The install runs only when
# the lockfile differs from the one of the last install. The committed node_modules/ folders
# below test/ and examples/ are test data of the product: the install does not touch them.
# YARN_DISABLE_SELF_UPDATE_CHECK keeps yarn from writing the time of its update check into the
# file ~/.yarnrc of the user.
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0 COREPACK_ENABLE_AUTO_PIN=0 YARN_DISABLE_SELF_UPDATE_CHECK=true
lock=$(sha256sum "$product/yarn.lock" | cut -d' ' -f1)
stamp="$product/node_modules/.bootstrap-lock.sha256"
if [ "$(cat "$stamp" 2>/dev/null)" != "$lock" ]; then
  (cd "$product" && corepack yarn install --frozen-lockfile --ignore-scripts --non-interactive \
    --no-progress)
  printf '%s\n' "$lock" > "$stamp"
fi
# WebStorm restores a project at its start only when the folder has IDE project files. The
# module file holds what WebStorm itself writes at the first open of this folder: one content
# root with no source folder, no test folder and no excluded folder. WebStorm adds node_modules/
# as a library root by itself at each open. The product ignores .idea in its .gitignore.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/webpack.iml" filepath="$PROJECT_DIR$/.idea/webpack.iml" />
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
if [ "$(cat "$idea/webpack.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/webpack.iml"
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "webpack: ready (yarn $(cd "$product" && corepack yarn --version))"
