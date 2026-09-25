#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run every test suite in the release.

Each suite lives inside its own frozen bundle directory and resolves its
artifacts relative to that directory, so they cannot be collected by a single
``unittest discover`` pass.  This runner locates each suite, runs it in a child
process with the bundle as the working directory, and reports a summary.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def suites() -> list[tuple[str, Path, str]]:
    found = []
    for path in sorted(ROOT.rglob("test_*.py")):
        parts = set(path.parts)
        if ".git" in parts or "__pycache__" in parts:
            continue
        module = path.stem
        found.append((str(path.relative_to(ROOT)).replace("\\", "/"), path.parent, module))
    return found


def main() -> int:
    found = suites()
    if not found:
        print("no test suites found")
        return 1

    failures = []
    for label, workdir, module in found:
        print("=" * 72)
        print("running %s  (cwd: %s)" % (label, workdir.relative_to(ROOT)))
        print("=" * 72)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-v"],
            cwd=str(workdir),
        )
        if result.returncode != 0:
            failures.append(label)

    print()
    print("=" * 72)
    if failures:
        print("FAILED: %d suite(s)" % len(failures))
        for name in failures:
            print("  - %s" % name)
        return 1
    print("all %d suite(s) passed" % len(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
