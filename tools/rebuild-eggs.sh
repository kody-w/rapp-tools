#!/usr/bin/env bash
# Rebuild every tool's egg from source and re-stamp the catalogue digests.
#
# WHY: the catalogue carried `egg_sha256` values that matched no egg in
# existence, and `rapptools hatch` had nothing to verify against. Two separate
# failures produced that: eggs were packed with mtime-stamped `zip` (so no
# digest could stay valid), and nothing recomputed the digest after a rebuild.
# packegg.py fixes the first; this script fixes the second, and both run
# together so the pair can never drift again.
#
#   rebuild-eggs.sh            rebuild, restamp
#   rebuild-eggs.sh --check    fail if any egg or digest is out of date
#
# --check is what CI and the dryrun suites call: it rebuilds into a temp tree
# and diffs, so a stale egg is a red test rather than a surprise at hatch time.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
FABLE="$(cd "$HERE/../.." && pwd -P)"
PACK="$HERE/packegg.py"
CATALOG="$HERE/../catalog/catalog.json"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

TOOLS="rapp-shot:rapp_shot rapp-voice:rapp_voice rapp-crispy:rapp_crispy rapp-rewind:rapp_rewind"
rc=0
declare -a REPORT=()

for pair in $TOOLS; do
  repo="${pair%%:*}"; pkg="${pair##*:}"
  root="$FABLE/$repo"
  [ -d "$root/$pkg" ] || { echo "skip $pkg — no $root/$pkg"; continue; }
  egg="$root/$pkg/eggs/$pkg.egg"
  ver=$(python3 -c "import json;print(json.load(open('$root/$pkg/manifest.json'))['version'])")

  # The singleton agent is the source of truth; the twin copy is generated.
  # They drifted before, which is how an egg shipped a claim its repo had
  # already corrected. --check must REPORT that drift, not silently repair it:
  # copying here made the read-only check write to the working tree and made
  # twin-only edits invisible, which is the one thing it exists to catch.
  if [ "$CHECK" = 1 ]; then
    if ! cmp -s "$root/$pkg/singleton/${pkg}_agent.py" \
                "$root/$pkg/twin/agents/${pkg}_agent.py"; then
      REPORT+=("DRIFT       $pkg — twin agent differs from the singleton"); rc=1
      continue
    fi
  else
    cp "$root/$pkg/singleton/${pkg}_agent.py" "$root/$pkg/twin/agents/${pkg}_agent.py"
  fi

  build=$(mktemp -d)
  mkdir -p "$build/state"
  cp -R "$root/$pkg/twin" "$build/twin"
  cp "$root/$pkg/manifest.json" "$build/"
  printf 'Intentionally empty. A hatched rapplication starts with no user state.\n' \
    > "$build/state/README.md"
  python3 - "$pkg" "$ver" "$build" <<'PY'
import json, sys
pkg, ver, build = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump({"schema": "rapp-egg/1.0", "id": pkg, "version": ver,
           "runtime": "twin", "publisher": "@kody-w",
           "contains": ["twin/soul.md", f"twin/agents/{pkg}_agent.py",
                        "manifest.json", "state/"],
           "state": "empty", "pii": "none",
           "note": ("Hatch cartridge only. No recordings, transcripts, indexes, "
                    "captures, credentials or personal paths.")},
          open(f"{build}/EGG.json", "w"), indent=2)
PY

  if [ "$CHECK" = 1 ]; then
    tmp=$(mktemp -d)/x.egg
    python3 "$PACK" "$build" "$tmp" >/dev/null
    new=$(shasum -a 256 "$tmp" | cut -d' ' -f1)
    have=$(shasum -a 256 "$egg" 2>/dev/null | cut -d' ' -f1 || echo none)
    want=$(python3 -c "
import json;c=json.load(open('$CATALOG'))
print(next((t.get('egg_sha256') or 'none') for t in c['tools'] if t['id']=='$pkg'))")
    wantb=$(python3 -c "
import json;c=json.load(open('$CATALOG'))
print(next((t.get('egg_bytes') or 0) for t in c['tools'] if t['id']=='$pkg'))")
    haveb=$(wc -c < "$egg" | tr -d ' ')
    if [ "$new" != "$have" ]; then
      REPORT+=("STALE-EGG   $pkg — on disk does not match source"); rc=1
    elif [ "$new" != "$want" ]; then
      REPORT+=("STALE-SHA   $pkg — catalogue digest does not match the egg"); rc=1
    elif [ "$wantb" != "$haveb" ]; then
      REPORT+=("STALE-BYTES $pkg — catalogue says $wantb bytes, egg is $haveb"); rc=1
    else
      REPORT+=("ok          $pkg $ver ${new:0:16}…")
    fi
  else
    python3 "$PACK" "$build" "$egg" | sed "s|^|  $pkg  |"
    sha=$(shasum -a 256 "$egg" | cut -d' ' -f1)
    bytes_=$(wc -c < "$egg" | tr -d ' ')
    python3 - "$CATALOG" "$pkg" "$sha" "$ver" "$bytes_" <<'PY'
import json, sys
path, pkg, sha, ver, nbytes = sys.argv[1:6]
c = json.load(open(path))
for t in c["tools"]:
    if t["id"] == pkg:
        t["egg_sha256"] = sha
        t["version"] = ver
        # published alongside the digest and never updated: every value was
        # wrong. A stale integrity-adjacent field is worse than no field.
        t["egg_bytes"] = int(nbytes)
json.dump(c, open(path, "w"), indent=2)
open(path, "a").write("\n")
PY
    REPORT+=("restamped   $pkg $ver ${sha:0:16}…")
  fi
  rm -rf "$build"
done

printf '%s\n' "${REPORT[@]}"
[ "$CHECK" = 1 ] && [ "$rc" != 0 ] && \
  echo "run tools/rebuild-eggs.sh to regenerate" >&2
exit $rc
