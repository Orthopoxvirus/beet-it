#!/usr/bin/env python3
"""CI guard: the alembic migration graph must have exactly one head and no
duplicate revision ids.

Locates the versions dir via the nearest ``alembic.ini`` (reading its
``script_location``), so this exact file is drop-in for any alembic repo
regardless of whether versions live under ``alembic/`` or ``migrations/``.

Catches the parallel-PR collision where two branches each add a migration on
the same parent: each branch alone is single-head, but once both land on
master ``alembic upgrade head`` breaks and the deploy crash-loops.

Pure stdlib — no DB, no alembic import.
"""
import collections
import configparser
import glob
import os
import re
import sys


def find_versions_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    while True:
        ini = os.path.join(d, "alembic.ini")
        if os.path.isfile(ini):
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(ini)
            loc = cfg.get("alembic", "script_location", fallback="alembic")
            versions = os.path.join(d, loc, "versions")
            if os.path.isdir(versions):
                return versions
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    for cand in glob.glob(os.path.join(here, "**", "versions"), recursive=True):
        if os.path.isdir(cand) and glob.glob(os.path.join(cand, "*.py")):
            return cand
    return None


def main():
    versions = find_versions_dir()
    if not versions:
        print("MIGRATION GRAPH CHECK: could not locate the alembic versions dir.")
        sys.exit(1)

    rev_files = collections.defaultdict(list)
    down_of = {}
    for path in sorted(glob.glob(os.path.join(versions, "*.py"))):
        src = open(path, encoding="utf-8").read()
        rm = re.search(r"^revision\s*[:=].*?['\"]([^'\"]+)['\"]", src, re.M)
        if not rm:
            continue
        rev = rm.group(1)
        rev_files[rev].append(os.path.basename(path))
        dm = re.search(r"^down_revision\s*[:=]\s*(.+)$", src, re.M)
        # down_revision may be a tuple (merge migration) — capture all ids.
        down_of[rev] = re.findall(r"['\"]([^'\"]+)['\"]", dm.group(1)) if dm else []

    if not down_of:
        print(f"MIGRATION GRAPH CHECK: no migrations found in {versions}.")
        sys.exit(1)

    errors = []
    dups = {r: fs for r, fs in rev_files.items() if len(fs) > 1}
    if dups:
        errors.append(f"duplicate revision ids: {dups}")
    referenced = {d for ds in down_of.values() for d in ds}
    heads = sorted(r for r in down_of if r not in referenced)
    if len(heads) != 1:
        errors.append(f"expected exactly 1 head, found {len(heads)}: {heads}")

    if errors:
        print("MIGRATION GRAPH CHECK FAILED:")
        for e in errors:
            print("  -", e)
        print(
            "\nFix: renumber the colliding migration and chain it after the "
            "other (set its down_revision to the current head)."
        )
        sys.exit(1)

    print(
        f"OK: single head {heads[0]}, {len(down_of)} revisions "
        f"in {os.path.relpath(versions)}, no duplicate ids."
    )


if __name__ == "__main__":
    main()
