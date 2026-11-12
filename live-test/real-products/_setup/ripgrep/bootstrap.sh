#!/usr/bin/env bash
# Prepare the ripgrep checkout for RustRover. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../ripgrep" && pwd)
for tool in cargo rustc; do
  if ! command -v "$tool" >/dev/null; then
    echo "ripgrep needs $tool on the PATH (rustup: https://rustup.rs)" >&2; exit 1
  fi
done
need=1.85.0  # rust-version in Cargo.toml
have=$(rustc --version | sed -n 's/^rustc \([0-9][0-9.]*\).*/\1/p')
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "ripgrep needs Rust $need or later, found '$have'" >&2; exit 1
fi
# RustRover resolves the standard library in the rust-src component of the toolchain.
if [ ! -f "$(rustc --print sysroot)/lib/rustlib/src/rust/library/core/src/lib.rs" ]; then
  echo "ripgrep needs the rust-src component: rustup component add rust-src" >&2; exit 1
fi
# Cargo.lock is committed, and --locked refuses any change of it. The crates go to the
# registry of CARGO_HOME, outside the checkout.
(cd "$product" && cargo fetch --locked --quiet)
# RustRover restores a project at its start only when the folder has IDE project files. The
# workspace file attaches the root Cargo.toml and names the toolchain, because a restored
# project does not look for them by itself. The product ignores /.idea in its .gitignore.
# The module file holds the source and test folders that RustRover itself writes for this pin
# (src and examples are sources, tests and benches are tests). The Cargo sync sets these roots
# at each open, but in a later open the IDE loads the module file after that sync and drops
# each root that the file does not have. The IDE in serverMode does not save the file.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/ripgrep.iml" filepath="$PROJECT_DIR$/.idea/ripgrep.iml" />
    </modules>
  </component>
</project>
XML
fi
iml=$(cat <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module type="EMPTY_MODULE" version="4">
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$">
      <sourceFolder url="file://$MODULE_DIR$/crates/cli/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/globset/benches" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/globset/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/grep/examples" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/grep/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ignore/examples" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ignore/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ignore/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/matcher/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/matcher/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/pcre2/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/printer/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/regex/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/searcher/examples" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/searcher/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/tests" isTestSource="true" />
      <excludeFolder url="file://$MODULE_DIR$/target" />
    </content>
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
)
if [ "$(cat "$idea/ripgrep.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/ripgrep.iml"
fi
if [ ! -f "$idea/workspace.xml" ]; then
  printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' '<project version="4">' \
    '  <component name="CargoProjects">' \
    '    <cargoProject FILE="$PROJECT_DIR$/Cargo.toml" />' \
    '  </component>' \
    '  <component name="RustProjectSettings">' \
    "    <option name=\"toolchainHomeDirectory\" value=\"$(dirname "$(command -v cargo)")\" />" \
    '  </component>' \
    '</project>' > "$idea/workspace.xml"
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "ripgrep: ready"
