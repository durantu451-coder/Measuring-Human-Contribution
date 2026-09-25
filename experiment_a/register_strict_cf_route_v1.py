# -*- coding: utf-8 -*-
"""Offline stage/promote utility for strict-CF model-scoped route bundles.

Staging performs no provider request.  Promotion accepts only an already-written,
accepted six-call quarantine smoke report and publishes one write-once pointer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from experiment_a.strict_cf_route_bundle import (
    build_candidate_bundle,
    promote_candidate,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    stage = sub.add_parser("stage")
    stage.add_argument("--model", required=True)
    stage.add_argument("--entrypoint", type=Path, required=True)
    stage.add_argument("--route-id", required=True)
    stage.add_argument("--client-id", required=True)
    stage.add_argument(
        "--coordination", choices=("none", "experiment_b_backend_c"), default="none"
    )
    stage.add_argument("--project-file", type=Path, action="append", default=[])
    stage.add_argument("--required-env", action="append", default=[])
    stage.add_argument("--optional-env", action="append", default=[])
    stage.add_argument("--external-package", action="append", default=[])
    stage.add_argument(
        "--external-dependency",
        action="append",
        default=[],
        metavar="ROLE=PATH",
    )

    promote = sub.add_parser("promote")
    promote.add_argument("--model", required=True)
    promote.add_argument("--bundle-sha256", required=True)
    promote.add_argument("--smoke-report", type=Path, required=True)
    return parser


def _external(values: Sequence[str]) -> list[dict[str, object]]:
    result = []
    for raw in values:
        if "=" not in raw:
            raise SystemExit(f"external dependency must be ROLE=PATH: {raw!r}")
        role, path = raw.split("=", 1)
        if not role.strip() or not path.strip():
            raise SystemExit(f"invalid external dependency: {raw!r}")
        result.append(
            {
                "role": role.strip(),
                "path": str(Path(path).expanduser()),
                "contains_credentials": False,
            }
        )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "stage":
        bundle, path = build_candidate_bundle(
            args.run_root,
            model=args.model,
            entrypoint=args.entrypoint,
            route_id=args.route_id,
            client_id=args.client_id,
            coordination=args.coordination,
            explicit_project_files=args.project_file,
            external_dependencies=_external(args.external_dependency),
            required_environment_names=args.required_env,
            optional_environment_names=args.optional_env,
            external_packages=args.external_package,
        )
        print(
            json.dumps(
                {
                    "state": "COMMITTED",
                    "model": args.model,
                    "bundle_sha256": bundle["bundle_sha256"],
                    "path": str(path),
                },
                sort_keys=True,
            )
        )
        return 0
    pointer = promote_candidate(
        args.run_root,
        model=args.model,
        bundle_sha256=args.bundle_sha256,
        smoke_report_path=args.smoke_report,
    )
    print(
        json.dumps(
            {
                "state": "FORMAL",
                "model": args.model,
                "formal_pointer_sha256": pointer["formal_pointer_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
