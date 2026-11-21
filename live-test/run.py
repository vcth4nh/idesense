#!/usr/bin/env python3
"""Entry command of the live tests. `./run.py [options]` runs the snapshot suites (see suite/cli.py).
`./run.py <package> <module> [args]` runs `python3 -m <package>.<module>` for audit, bench, keygen and common."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
PACKAGES = ("audit", "bench", "keygen", "common")

if len(sys.argv) > 2 and sys.argv[1] in PACKAGES:
    module = f"{sys.argv[1]}.{sys.argv[2]}"
    sys.argv = [module, *sys.argv[3:]]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
else:
    from suite.cli import main
    sys.exit(main())
