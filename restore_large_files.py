#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore the release's oversized files after cloning.

Four artifacts exceed GitHub's 100 MB per-file limit and are therefore shipped
packed under `large_files/` rather than in place:

  * gzip  - the file compresses well (text), and is stored as `<name>.gz`
  * split - the file does not compress below the cap, and is stored as
            `<name>.part/partNN` byte ranges

Three of the four are verified by SHA-256 against values recorded in the
release's own manifests -- `sources.jsonl` by nine of them, `oof_predictions.jsonl`
by `manifest.json` and `scientific_completion.json` -- and `audit_analysis.py`
reads `oof_predictions.jsonl` directly.  Every restore here is therefore
byte-exact: the recorded digest is checked BEFORE the restored file is published,
so a failed restore never leaves a half-correct tree.

The archives live at the repository root precisely so that the sensitivity
auditor's directory inventory (audit_analysis.py:98, ALLOWED_DIRECTORIES) never
sees them: it only walks the bundle directory, and an undeclared directory there
would abort the audit.

USAGE
-----
    python restore_large_files.py                  # restore everything, verify
    python restore_large_files.py --check          # report, write nothing
    python restore_large_files.py --delete-archives  # also free the space
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK = 32 * 1024 * 1024


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        while blk := handle.read(BLOCK):
            h.update(blk)
    return h.hexdigest()


def restore_one(entry, delete_archives, check_only):
    label = entry["original_relative_path"]
    target = os.path.join(HERE, label.replace("/", os.sep))
    members = entry["members"]

    missing = [m["name"] for m in members
               if not os.path.exists(os.path.join(HERE, m["name"].replace("/", os.sep)))]
    if missing:
        print("  MISSING  %s\n           %s" % (label, ", ".join(missing)))
        return None

    if check_only:
        # For a split the member sizes are the original size; for gzip they are
        # the COMPRESSED size, so comparing them to original_size is meaningless.
        # Report presence plus the recorded digest, and let a real restore verify.
        if entry["method"] == "gzip":
            packed = sum(m["size"] for m in members)
            print("  OK       %-78s gzip  archive %.1f MB (restores to %.1f MB)"
                  % (label, packed / 1024 / 1024, entry["original_size"] / 1024 / 1024))
        else:
            total = sum(m["size"] for m in members)
            ok = total == entry["original_size"]
            print("  %s  %-78s split  %d/%d bytes"
                  % ("OK       " if ok else "MISMATCH", label, total, entry["original_size"]))
            return ok
        return True

    os.makedirs(os.path.dirname(target), exist_ok=True)
    temp = target + ".restoring"
    digest = hashlib.sha256()

    if entry["method"] == "gzip":
        opener = gzip.open
        mode = "wb"
        with opener(os.path.join(HERE, members[0]["name"].replace("/", os.sep)), "rb") as src, \
                open(temp, mode) as out:
            shutil.copyfileobj(src, out, BLOCK)
        # hash the product, not the stream, so the check is independent
        digest = hashlib.sha256()
        with open(temp, "rb") as handle:
            while blk := handle.read(BLOCK):
                digest.update(blk)
    else:
        with open(temp, "wb") as out:
            for member in members:
                with open(os.path.join(HERE, member["name"].replace("/", os.sep)), "rb") as src:
                    while blk := src.read(BLOCK):
                        out.write(blk)
                        digest.update(blk)

    if digest.hexdigest() != entry["original_sha256"]:
        os.remove(temp)
        print("  FAILED   %s\n           SHA-256 mismatch\n           got      %s\n           expected %s"
              % (label, digest.hexdigest(), entry["original_sha256"]))
        return None
    size = os.path.getsize(temp)
    if size != entry["original_size"]:
        os.remove(temp)
        print("  FAILED   %s  size %d != %d" % (label, size, entry["original_size"]))
        return None

    os.replace(temp, target)
    print("  OK       %-78s %s  %.1f MB, sha256 verified"
          % (label, entry["method"], size / 1024 / 1024))

    if delete_archives:
        for member in members:
            path = os.path.join(HERE, member["name"].replace("/", os.sep))
            os.remove(path)
            parent = os.path.dirname(path)
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="report whether the archives are present and complete")
    parser.add_argument("--delete-archives", action="store_true",
                        help="delete each archive once its file is verified")
    args = parser.parse_args()

    index_path = os.path.join(HERE, "large_files", "index.json")
    if not os.path.exists(index_path):
        raise SystemExit("large_files/index.json not found -- nothing to restore")
    with open(index_path, "rb") as handle:
        index = json.loads(handle.read().decode("utf-8"))

    verb = "checking" if args.check else "restoring"
    print("%s %d oversized file(s) from large_files/" % (verb, len(index["files"])))
    print()
    results = [restore_one(e, args.delete_archives, args.check) for e in index["files"]]

    print()
    if args.check:
        bad = [r for r in results if r is not True]
        print("%d/%d archives complete" % (len(results) - len(bad), len(results)))
        return 1 if bad else 0
    failed = [r for r in results if r is None]
    if failed:
        print("%d file(s) could not be restored" % len(failed))
        return 1
    print("all %d file(s) restored and verified against their recorded SHA-256" % len(results))
    if not args.delete_archives:
        print("re-run with --delete-archives to reclaim the space")
    return 0


if __name__ == "__main__":
    sys.exit(main())
