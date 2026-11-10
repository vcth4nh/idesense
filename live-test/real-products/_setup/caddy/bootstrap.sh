#!/usr/bin/env bash
# Prepare the caddy checkout for GoLand. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../caddy" && pwd)
need=1.26.0
have=$(go env GOVERSION | sed 's/^go//')
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "caddy needs Go $need or later, found $have" >&2; exit 1
fi
(cd "$product" && go mod download)
# GoLand restores a project at its start only when the folder has IDE project files, and it
# gives a restored project no module. These are the files that GoLand wrote for the Go fixture.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/workspace.xml" ]; then
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<project version="4">\n  <component name="GOROOT" url="file://%s" />\n</project>\n' \
    "$(go env GOROOT)" > "$idea/workspace.xml"
fi
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/caddy.iml" filepath="$PROJECT_DIR$/.idea/caddy.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/caddy.iml" ]; then
  cat > "$idea/caddy.iml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module type="WEB_MODULE" version="4">
  <component name="Go" enabled="true" />
  <component name="GoModuleSettings" enabled="true" />
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$" />
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "caddy: ready"
