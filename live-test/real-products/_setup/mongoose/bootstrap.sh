#!/usr/bin/env bash
# Prepare the mongoose checkout for WebStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../mongoose" && pwd)
for tool in node npm; do
  if ! command -v "$tool" >/dev/null; then
    echo "mongoose needs $tool on the PATH (Node.js 20.19 or later)" >&2; exit 1
  fi
done
need=20.19.0  # engines.node in package.json
have=$(node --version | sed -n 's/^v\([0-9][0-9.]*\).*/\1/p')
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "mongoose needs Node.js $need or later, found '$have'" >&2; exit 1
fi
# Upstream has no lockfile: its .npmrc sets package-lock=false, and its .gitignore ignores
# package-lock.json. The package-lock.json next to this script pins the dependencies. When it is
# absent, the bootstrap makes it one time from package.json and keeps it here. The .npmrc of the
# product also sets min-release-age=2, so npm takes no version that is younger than two days.
kept="$here/package-lock.json"
if [ ! -f "$kept" ]; then
  (cd "$product" && npm install --package-lock-only --package-lock=true --ignore-scripts \
    --no-audit --no-fund --loglevel=error)
  cp "$product/package-lock.json" "$kept"
fi
# npm ci reads the lockfile only in the product folder. The product ignores package-lock.json,
# so the copy is no tracked file. --ignore-scripts runs no script of the product and no install
# script of a package: the IDE reads the sources of the packages only. The packages go to
# node_modules/ in the checkout. npm ci removes node_modules/ first, so it runs only when the
# lockfile differs from the one of the last install.
cmp -s "$kept" "$product/package-lock.json" || cp "$kept" "$product/package-lock.json"
lock=$(sha256sum "$kept" | cut -d' ' -f1)
stamp="$product/node_modules/.bootstrap-lock.sha256"
if [ "$(cat "$stamp" 2>/dev/null)" != "$lock" ]; then
  (cd "$product" && npm ci --package-lock=true --ignore-scripts --no-audit --no-fund \
    --loglevel=error)
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
      <module fileurl="file://$PROJECT_DIR$/.idea/mongoose.iml" filepath="$PROJECT_DIR$/.idea/mongoose.iml" />
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
if [ "$(cat "$idea/mongoose.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/mongoose.iml"
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "mongoose: ready"
