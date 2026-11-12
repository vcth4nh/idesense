#!/usr/bin/env bash
# Prepare the beets checkout for PyCharm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../beets" && pwd)
if ! command -v uv >/dev/null; then
  echo "beets needs uv on the PATH (https://docs.astral.sh/uv/)" >&2; exit 1
fi
# uv.lock is committed. --locked stops when the lock is not up to date and never writes it.
# The lock has markers for the Python version (numpy), so the version is fixed: uv takes an
# installed Python 3.12 or downloads one. The environment is .venv in the checkout, with the
# default group dev (docs, lint, test, typing) and no extras.
(cd "$product" && uv sync --locked --python 3.12 --quiet)
# PyCharm restores a project at its start only when the folder has IDE project files. At each
# open PyCharm rebuilds the module from pyproject.toml, and it gives a module with no SDK the
# uv environment in .venv. The repository root is the source root (beets and the namespace
# package beetsplug), and test is the test root. The module file has external.system.id: then
# PyCharm counts the module as its own and keeps its roots. Without it, the rebuild writes the
# roots again with no isTestSource, and at the next start test is a plain source root.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/beets.iml" filepath="$PROJECT_DIR$/.idea/beets.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/beets.iml" ]; then
  cat > "$idea/beets.iml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module external.system.id="pyproject.toml" type="PYTHON_MODULE" version="4">
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$">
      <sourceFolder url="file://$MODULE_DIR$" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/test" isTestSource="true" />
      <excludeFolder url="file://$MODULE_DIR$/.venv" />
    </content>
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
XML
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "beets: ready"
