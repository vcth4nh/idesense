#!/usr/bin/env bash
# Prepare the ruff checkout for RustRover. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../ruff" && pwd)
for tool in rustup cargo rustc; do
  if ! command -v "$tool" >/dev/null; then
    echo "ruff needs $tool on the PATH (rustup: https://rustup.rs)" >&2; exit 1
  fi
done
cd "$product"
# rust-toolchain.toml of the product names the toolchain. RUSTUP_TOOLCHAIN overrides that file,
# so the calls of this script run without it. `rustup toolchain install` with no name installs
# the toolchain of the file; it changes no default toolchain.
unset RUSTUP_TOOLCHAIN
rustup toolchain install --no-self-update >/dev/null
# RustRover resolves the standard library in the rust-src component of the toolchain.
rustup component add rust-src >/dev/null
if [ ! -f "$(rustc --print sysroot)/lib/rustlib/src/rust/library/core/src/lib.rs" ]; then
  echo "ruff needs the rust-src component of $(rustup show active-toolchain)" >&2; exit 1
fi
# Cargo.lock is committed, and --locked refuses any change of it. The crates go to the
# registry of CARGO_HOME, outside the checkout. The Python and JavaScript packages are not
# installed: no row resolves into them.
cargo fetch --locked --quiet
# RustRover restores a project at its start only when the folder has IDE project files. The
# workspace file attaches the root Cargo.toml and names the toolchain, because a restored
# project does not look for them by itself. The product ignores .idea in its .gitignore.
# The module file holds the source and test folders that RustRover itself writes for this pin
# (src and examples are sources, tests and benches are tests). In a later open the IDE applies
# the module file after the Cargo sync and drops each root that the file does not have.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/ruff.iml" filepath="$PROJECT_DIR$/.idea/ruff.iml" />
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
      <sourceFolder url="file://$MODULE_DIR$/crates/mdtest/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_annotate_snippets/examples" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_annotate_snippets/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_annotate_snippets/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_benchmark/benches" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_benchmark/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_cache/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_cache/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_db/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_dev/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_diagnostics/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_formatter/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_graph/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_index/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_linter/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_macros/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_markdown/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_mdtest/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_mdtest/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_memory_usage/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_notebook/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_options_metadata/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_ast/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_ast_integration_tests/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_ast_integration_tests/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_codegen/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_formatter/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_formatter/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_importer/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_index/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_literal/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_parser/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_parser/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_semantic/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_stdlib/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_trivia/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_trivia_integration_tests/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_python_trivia_integration_tests/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_ranged_value/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_server/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_server/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_source_file/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_text_size/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_text_size/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_wasm/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_wasm/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ruff_workspace/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_combine/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_completion_bench/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_completion_eval/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_ide/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_module_resolver/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_project/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_python_core/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_python_semantic/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_python_semantic/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_server/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_server/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_site_packages/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_static/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_test/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_vendored/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_wasm/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/ty_wasm/tests" isTestSource="true" />
      <excludeFolder url="file://$MODULE_DIR$/target" />
    </content>
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
)
if [ "$(cat "$idea/ruff.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/ruff.iml"
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
echo "ruff: ready ($(rustup show active-toolchain | cut -d' ' -f1))"
