#!/usr/bin/env python3
"""Read-only integrity verification of the four retained pre-RAPP/1 archives."""
import hashlib
import json
from pathlib import Path
import sys


def verify(catalog, family):
    failures = []
    for tool in catalog["tools"]:
        path = family / tool["repo"] / tool["id"] / "eggs" / (tool["id"] + ".egg")
        if not path.is_file() or path.is_symlink():
            failures.append(tool["id"] + ": missing or symlinked historical archive")
            continue
        data = path.read_bytes()
        if len(data) != tool["egg_bytes"] or hashlib.sha256(data).hexdigest() != tool["egg_sha256"]:
            failures.append(tool["id"] + ": historical archive differs from its catalog pin")
    return failures


def main():
    root = Path(__file__).resolve().parents[1]
    failures = verify(json.loads((root / "catalog/catalog.json").read_bytes()), root.parent)
    for message in failures:
        print(message, file=sys.stderr)
    if failures:
        return 1
    print("Verified four immutable historical archive pins; this is not current RAPP/1 conformance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
