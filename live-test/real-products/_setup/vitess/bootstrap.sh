#!/usr/bin/env bash
# Prepare the vitess checkout for GoLand. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../vitess" && pwd)
# The Go SDK of the project is the version of go.mod. The go command gets that toolchain into
# the module cache (GOTOOLCHAIN) and checks it against the checksum database. No default Go
# of the host changes.
need=$(sed -n 's/^go //p' "$product/go.mod")
command -v go > /dev/null || { echo "vitess needs a go command on PATH" >&2; exit 1; }
goroot=$(cd "$product" && GOFLAGS= GOTOOLCHAIN="go$need" go env GOROOT)
go="$goroot/bin/go"
have=$(GOTOOLCHAIN=local "$go" env GOVERSION)
if [ "$have" != "go$need" ]; then
  echo "vitess needs Go $need, the toolchain gives $have" >&2; exit 1
fi
export GOTOOLCHAIN=local GOFLAGS=
# There are six go.mod files: the root module and five tool modules below tools/. At each open
# GoLand reads each module graph with `go list -m -json -mod=mod all` on a copy of go.mod, and
# it attaches each module of the graph that has a folder in the shared module cache. So the
# loop downloads each module of each graph: the libraries of the project then come from
# vitess only, not from what other checkouts downloaded, and the open needs no network.
# go.sum pins each version. The copy keeps go.mod and go.sum unchanged.
gomodcache=$("$go" env GOMODCACHE)
absent() { # the modules of the graph of the go.mod copy $2 (module folder $1) with no folder
  (cd "$1" && "$go" list -modfile="$2" -mod=mod -m \
    -f '{{if and (not .Main) (not .Dir)}}{{.Path}}@{{.Version}}{{end}}' all) | { grep . || true; }
}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
start=$(date +%s)
before=
while IFS= read -r mod; do
  dir=$(dirname "$mod")
  rel=${dir#"$product"}; rel=${rel#/}; rel=${rel:-.}
  copy="$tmp/$(echo "$rel" | tr '/.' '__')"
  mkdir -p "$copy"
  cp "$dir/go.mod" "$dir/go.sum" "$copy/"
  n=$(absent "$dir" "$copy/go.mod" | wc -l)
  [ "$n" -eq 0 ] && continue
  [ -n "$before" ] || before=$(du -sb "$gomodcache" | cut -f1)
  echo "$rel: $n modules of the graph have no folder in the module cache"
  (cd "$dir" && "$go" mod download -modfile="$copy/go.mod" all)
  n=$(absent "$dir" "$copy/go.mod" | wc -l)
  [ "$n" -eq 0 ] || { echo "$rel: $n modules still have no folder" >&2; exit 1; }
done < <(git -C "$product" ls-files --full-name -- 'go.mod' '*/go.mod' | sed "s|^|$product/|")
if [ -n "$before" ]; then
  after=$(du -sb "$gomodcache" | cut -f1)
  echo "module cache: +$((after - before)) bytes in $(($(date +%s) - start)) s"
fi
# GoLand restores a project at its start only when the folder has IDE project files, and it
# gives a restored project no module.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/workspace.xml" ]; then
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<project version="4">\n  <component name="GOROOT" url="file://%s" />\n</project>\n' \
    "$goroot" > "$idea/workspace.xml"
fi
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/vitess.iml" filepath="$PROJECT_DIR$/.idea/vitess.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/vitess.iml" ]; then
  cat > "$idea/vitess.iml" <<'XML'
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
echo "vitess: ready"
