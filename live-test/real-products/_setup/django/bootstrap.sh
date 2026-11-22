#!/usr/bin/env bash
# Prepare the django checkout for PyCharm. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../django" && pwd)
if ! command -v uv >/dev/null; then
  echo "django needs uv on the PATH (https://docs.astral.sh/uv/)" >&2; exit 1
fi
# The environment is .venv in the checkout, with Python 3.12 (requires-python ">= 3.12"): uv
# takes an installed Python 3.12 or downloads one. uv writes .venv/.gitignore, so git ignores
# the environment.
venv="$product/.venv"
if [ ! -x "$venv/bin/python" ]; then
  uv venv --python 3.12 --quiet "$venv"
fi
# Upstream has no lockfile. The packages are those of the test setup of the Django docs
# (tests/requirements/py3.txt), without pylibmc and pywatchman: these two have no wheel and need
# a native build. The first run resolves them with the packages of the pin date and writes
# constraints.txt next to this script; the repository keeps that file. Each run installs
# exactly the packages of constraints.txt, from wheels only, so no package code runs.
lock="$here/constraints.txt"
if [ ! -f "$lock" ]; then
  grep -v -E '^(pylibmc|pywatchman)([^A-Za-z0-9_.-]|$)' "$product/tests/requirements/py3.txt" |
    uv pip compile - --python "$venv/bin/python" --only-binary :all: \
      --exclude-newer 2026-10-06T11:32:30Z \
      --custom-compile-command "live-test/real-products/_setup/django/bootstrap.sh" \
      --quiet -o "$lock"
fi
uv pip sync --python "$venv/bin/python" --only-binary :all: --quiet "$lock"
# PyCharm restores a project at its start only when the folder has IDE project files. At a
# first open PyCharm 2026.3 itself writes the module file .idea/Django.iml (the project name of
# pyproject.toml) with external.system.id, and at each open it rebuilds the module from
# pyproject.toml. The attribute makes the rebuild keep the roots of this file. The repository
# root is the source root (the package django), and tests is the test root: tests is no
# package, and the test runner of Django puts it on sys.path. PyCharm gives the module the uv
# environment in .venv when the module has no SDK.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/modules.xml" ]; then
  cat > "$idea/modules.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/Django.iml" filepath="$PROJECT_DIR$/.idea/Django.iml" />
    </modules>
  </component>
</project>
XML
fi
if [ ! -f "$idea/Django.iml" ]; then
  cat > "$idea/Django.iml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<module external.system.id="pyproject.toml" type="PYTHON_MODULE" version="4">
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$">
      <sourceFolder url="file://$MODULE_DIR$" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/tests" isTestSource="true" />
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
echo "django: ready"
