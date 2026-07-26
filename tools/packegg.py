#!/usr/bin/env python3
"""Deterministic egg packer — same contents in, byte-identical egg out.

WHY THIS EXISTS.

Eggs were packed with `zip`, which stamps every entry with its file mtime. Two
packs of identical content therefore produced different bytes and different
sha256s. Three things broke as a consequence:

  * the catalogue's `egg_sha256` matched nothing, so `rapptools hatch` had no
    integrity check to perform even after one was added;
  * every repack left the repo dirty with a "changed" egg whose contents were
    the same, which trains you to `git add` a binary you did not inspect;
  * nobody could reproduce a published egg to check it against the digest.

Fixing the digest without fixing reproducibility would have been theatre. So:
entries sorted by name, a fixed timestamp, fixed permissions, no extra fields.

    packegg.py <source-dir> <out.egg>          pack
    packegg.py --check <out.egg>               repack in memory, confirm stable

The timestamp is the DOS epoch floor (1980-01-01); zip cannot store anything
earlier, and a constant is the point.
"""

import hashlib
import os
import sys
import zipfile

FIXED = (1980, 1, 1, 0, 0, 0)


def entries(src):
    out = []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for f in sorted(files):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src)
            if rel.startswith(".git") or f == ".DS_Store":
                continue
            out.append((rel.replace(os.sep, "/"), full))
    return sorted(out)


def pack_bytes(src):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, full in entries(src):
            zi = zipfile.ZipInfo(rel, date_time=FIXED)
            # 0644 for data, 0755 for anything executable on disk
            mode = 0o755 if os.access(full, os.X_OK) else 0o644
            zi.external_attr = (mode & 0xFFFF) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3  # unix, constant across machines
            with open(full, "rb") as fh:
                z.writestr(zi, fh.read())
    return buf.getvalue()


def main(argv):
    if len(argv) == 3 and argv[1] == "--check":
        # unpack to a temp tree, repack, and confirm the bytes come back equal
        import shutil, tempfile
        egg = argv[2]
        d = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(egg) as z:
                z.extractall(d)
            again = pack_bytes(d)
            have = open(egg, "rb").read()
            if again == have:
                print(f"reproducible  {hashlib.sha256(have).hexdigest()}  {egg}")
                return 0
            print(f"NOT reproducible: {egg}\n"
                  f"  on disk  {hashlib.sha256(have).hexdigest()}\n"
                  f"  repacked {hashlib.sha256(again).hexdigest()}", file=sys.stderr)
            return 1
        finally:
            shutil.rmtree(d, ignore_errors=True)

    if len(argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    src, out = argv[1], argv[2]
    if not os.path.isdir(src):
        print(f"not a directory: {src}", file=sys.stderr)
        return 2
    blob = pack_bytes(src)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # only rewrite when the bytes differ, so an unchanged egg stays unchanged in git
    if os.path.exists(out) and open(out, "rb").read() == blob:
        print(f"unchanged     {hashlib.sha256(blob).hexdigest()}  {out}")
        return 0
    with open(out, "wb") as fh:
        fh.write(blob)
    print(f"packed        {hashlib.sha256(blob).hexdigest()}  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
