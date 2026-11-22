#!/usr/bin/env bash
# Prepare the rolldown checkout for RustRover. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../rolldown" && pwd)
for tool in rustup cargo rustc; do
  if ! command -v "$tool" >/dev/null; then
    echo "rolldown needs $tool on the PATH (rustup: https://rustup.rs)" >&2; exit 1
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
  echo "rolldown needs the rust-src component of $(rustup show active-toolchain)" >&2; exit 1
fi
# Cargo.lock is committed, and --locked refuses any change of it. The crates go to the
# registry of CARGO_HOME, outside the checkout. The JavaScript packages are not installed: no
# row resolves into node_modules.
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
      <module fileurl="file://$PROJECT_DIR$/.idea/rolldown.iml" filepath="$PROJECT_DIR$/.idea/rolldown.iml" />
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
      <sourceFolder url="file://$MODULE_DIR$/crates/bench/benches" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/bench/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown/examples" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_binding/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_common/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_dev/examples" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_dev/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_dev_common/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_devtools/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_devtools_action/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_ecmascript/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_ecmascript_utils/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_error/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_fs/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_fs_watcher/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_asset_module/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_bundle_analyzer/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_chunk_import_map/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_copy_module/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_data_url/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_esm_external_require/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_hmr/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_isolated_declaration/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_isolated_declaration/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_lazy_compilation/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_oxc_runtime/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_replace/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_replace/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_utils/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_alias/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_build_import_analysis/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_dynamic_import_vars/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_import_glob/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_json/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_load_fallback/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_manifest/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_module_preload_polyfill/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_react_refresh_wrapper/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_reporter/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_resolve/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_transform/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_plugin_vite_web_worker_post/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_resolver/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_sourcemap/benches" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_sourcemap/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_std_utils/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_testing/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_testing/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_testing_config/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_tracing/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_tracing/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_utils/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_watcher/examples" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_watcher/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/rolldown_workspace/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/string_wizard/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/crates/string_wizard/tests" isTestSource="true" />
      <sourceFolder url="file://$MODULE_DIR$/tasks/generator/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/tasks/ls_lint/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/tasks/track_memory_allocations/src" isTestSource="false" />
      <excludeFolder url="file://$MODULE_DIR$/target" />
    </content>
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
)
if [ "$(cat "$idea/rolldown.iml" 2>/dev/null)" != "$iml" ]; then
  printf '%s\n' "$iml" > "$idea/rolldown.iml"
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
echo "rolldown: ready ($(rustup show active-toolchain | cut -d' ' -f1))"
