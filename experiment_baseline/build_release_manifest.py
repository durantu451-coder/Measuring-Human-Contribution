# -*- coding: utf-8 -*-
"""Create a compact SHA-256 inventory for the activated baseline-v2 release."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from experiment_b.storage import atomic_replace_json, canonical_row_sha256, file_sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--active-pointer", type=Path, required=True)
    parser.add_argument("--prepare-manifest", type=Path, required=True)
    parser.add_argument("--parity-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    paths = [args.active_pointer, args.prepare_manifest, args.parity_report]
    paths.extend(
        path
        for subtree in (args.run_root / "final", args.run_root / "timing")
        for path in subtree.rglob("*")
        if path.is_file()
    )
    unique = sorted({path.resolve() for path in paths}, key=lambda path: path.as_posix())
    files = [
        {
            "path": (
                path.relative_to(args.run_root.parent.parent).as_posix()
                if path.is_relative_to(args.run_root.parent.parent)
                else path.as_posix()
            ),
            "size": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in unique
    ]
    value = {
        "schema": "baseline_v2_release_manifest",
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_root": str(args.run_root.resolve()),
        "file_count": len(files),
        "files": files,
    }
    value["file_inventory_sha256"] = canonical_row_sha256(files)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_json(args.out, value)
    print(
        f"wrote {len(files)} files, inventory={value['file_inventory_sha256']} "
        f"-> {args.out}"
    )


if __name__ == "__main__":
    main()
