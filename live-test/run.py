#!/usr/bin/env python3
"""Entry command of the live tests. `./run.py [options]` runs the snapshot suites (see suite/cli.py).
`./run.py <package> <module> [args]` runs `python3 -m <package>.<module>` for audit, bench, keygen and common. With
no module of the package (no second argument, `-h`, or a name that is no module of the package), it prints one usage
line with the modules of the package and exits 2."""
import importlib.util
import pkgutil
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
PACKAGES = ("audit", "bench", "keygen", "common")


def _is_module(package: str, name: str) -> bool:
    """True when `<package>.<name>` is a module of the package, not a package."""
    try:
        spec = importlib.util.find_spec(f"{package}.{name}")
    except (ImportError, ValueError):
        return False
    return spec is not None and spec.submodule_search_locations is None


if len(sys.argv) > 1 and sys.argv[1] in PACKAGES:
    package = sys.argv[1]
    if len(sys.argv) < 3 or not _is_module(package, sys.argv[2]):
        folder = Path(__file__).resolve().parent / package
        modules = sorted(m.name for m in pkgutil.iter_modules([str(folder)]) if not m.ispkg)
        print(f"usage: ./run.py {package} <module> [args]; the modules of {package}: {', '.join(modules)}",
              file=sys.stderr)
        sys.exit(2)
    module = f"{package}.{sys.argv[2]}"
    sys.argv = [module, *sys.argv[3:]]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
else:
    from suite.cli import main
    sys.exit(main())
