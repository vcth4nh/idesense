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
mkdir -p "$product/.idea"
if [ ! -f "$product/.idea/workspace.xml" ]; then
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<project version="4">\n  <component name="GOROOT" url="file://%s" />\n</project>\n' \
    "$(go env GOROOT)" > "$product/.idea/workspace.xml"
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "caddy: ready"
