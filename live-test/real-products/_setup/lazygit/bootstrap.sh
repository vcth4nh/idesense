#!/usr/bin/env bash
# Prepare the lazygit checkout for GoLand. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../lazygit" && pwd)
need=$(sed -n 's/^go //p' "$product/go.mod")
have=$(go env GOVERSION | sed 's/^go//')
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "lazygit needs Go $need or later, found $have" >&2; exit 1
fi
# The dependencies are committed in vendor/. GoLand resolves imports into vendor/ by default
# (vendor mode), so no module source is downloaded. This proves that vendor/modules.txt
# agrees with go.mod.
(cd "$product" && GOFLAGS= go list -mod=vendor -deps ./... > /dev/null)
# At each open GoLand reads the module graph with `go list -m -json -mod=mod all` on a copy of
# go.mod. This fills the module cache with the go.mod files of the graph (no module source),
# checked against go.sum, so that the open needs no network.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp "$product/go.mod" "$product/go.sum" "$tmp/"
(cd "$product" && GOFLAGS= go list -modfile="$tmp/go.mod" -m -json -mod=mod all > /dev/null)
# GoLand restores a project at its start only when the folder has IDE project files, and it
# gives a restored project no module. These are the files that GoLand 2026.3 wrote at a first
# open of this product. GoLand wrote no vendoring setting: vendor mode is its default.
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
      <module fileurl="file://$PROJECT_DIR$/.idea/lazygit.iml" filepath="$PROJECT_DIR$/.idea/lazygit.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/lazygit.iml" ]; then
  cat > "$idea/lazygit.iml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module type="WEB_MODULE" version="4">
  <component name="Go" enabled="true" />
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
echo "lazygit: ready"
