#!/usr/bin/env bash
# Prepare the uptime-kuma checkout for WebStorm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../uptime-kuma" && pwd)
for tool in node npm; do
  if ! command -v "$tool" >/dev/null; then
    echo "uptime-kuma needs $tool on the PATH (Node.js 20.4 or later)" >&2; exit 1
  fi
done
need=20.4.0  # engines.node in package.json
have=$(node --version | sed -n 's/^v\([0-9][0-9.]*\).*/\1/p')
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "uptime-kuma needs Node.js $need or later, found '$have'" >&2; exit 1
fi
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
      <module fileurl="file://$PROJECT_DIR$/.idea/uptime-kuma.iml" filepath="$PROJECT_DIR$/.idea/uptime-kuma.iml" />
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
if [ "$(cat "$idea/uptime-kuma.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/uptime-kuma.iml"
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "uptime-kuma: ready"
