# -*- coding: utf-8 -*-
"""Compatibility entry point for the strict baseline analysis CLI.

All validation, joining, statistics, bootstrap policy, and output serialization
live in :mod:`experiment_baseline.analysis_core` and
:mod:`experiment_baseline.analyze_phi_ext`.  Legacy ``--phi`` inputs remain
available only as explicitly non-publication output through that CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from experiment_baseline.analyze_phi_ext import main


if __name__ == "__main__":
    raise SystemExit(main())
