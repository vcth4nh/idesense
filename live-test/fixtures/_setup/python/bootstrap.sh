#!/usr/bin/env bash
# Prepare the Python fixture for PyCharm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fixture=$(cd "$here/../../python" && pwd)
if ! command -v uv >/dev/null; then
  echo "the Python fixture needs uv on the PATH (https://docs.astral.sh/uv/)" >&2; exit 1
fi
# The environment is .venv in the fixture. The fixture has no dependencies. git ignores .venv
# and uv.lock. At the first open PyCharm makes a uv interpreter from .venv, and writes its name
# (a path of this machine) to misc.xml and to the module file. For this reason git tracks only
# modules.xml, and this script writes the module file.
(cd "$fixture" && uv sync --quiet)
# modules.xml names the module that PyCharm makes from pyproject.toml. src is the source root,
# and test is the test root: the hierarchy scopes production and test need it. The module file
# has external.system.id: then the rebuild from pyproject.toml at each open keeps the roots.
# Without it, the rebuild writes the roots again with no isTestSource (see
# real-products/_setup/beets/notes.md). An existing module file stays as it is.
iml="$fixture/.idea/live-test-python.iml"
if [ ! -f "$iml" ]; then
  cat > "$iml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module external.system.id="pyproject.toml" type="PYTHON_MODULE" version="4">
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$">
      <sourceFolder url="file://$MODULE_DIR$/src" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/test" isTestSource="true" />
      <excludeFolder url="file://$MODULE_DIR$/.venv" />
    </content>
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
fi
echo "python fixture: ready"
