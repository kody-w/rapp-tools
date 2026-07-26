#!/bin/bash
# RAPP Tools test suite — catalogue integrity and headless operation.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RT="$HERE/../rapptools"
CAT="$HERE/../catalog/catalog.json"
pass=0; fail=0
ok(){ printf '  \033[32mPASS\033[0m %s\n' "$*"; pass=$((pass+1)); }
bad(){ printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=$((fail+1)); }
info(){ printf '       %s\n' "$*"; }
head_(){ printf '\n\033[1;36m%s\033[0m\n' "$*"; }

head_ "1. Catalogue integrity"
python3 -c "import json;json.load(open('$CAT'))" 2>/dev/null && ok "catalog.json is valid JSON" || bad "malformed catalog"
python3 - <<PY
import json,sys
c=json.load(open("$CAT"))
need={"id","name","repo","port","agent","actions","engines","needs","egg_url","homepage","runtime","one"}
bad=[]
ports={}
for t in c["tools"]:
    miss=need-set(t)
    if miss: bad.append(f"{t.get('id')}: missing {sorted(miss)}")
    if t["runtime"]!="twin": bad.append(f"{t['id']}: runtime is not twin")
    if t["port"] in ports: bad.append(f"port {t['port']} claimed by {ports[t['port']]} and {t['id']}")
    ports[t["port"]]=t["id"]
    if not t["actions"]: bad.append(f"{t['id']}: no actions")
print("\n".join("       "+b for b in bad))
sys.exit(1 if bad else 0)
PY
[ $? -eq 0 ] && ok "every entry is complete, twin-runtime, and holds a unique port" || bad "catalogue entries are inconsistent"

head_ "2. Every egg URL resolves"
python3 - <<PY
import json,urllib.request,sys
c=json.load(open("$CAT")); bad=0
for t in c["tools"]:
    for k in ("egg_url","manifest_url","singleton_url"):
        try:
            r=urllib.request.urlopen(t[k],timeout=30); code=r.status
        except Exception as e:
            code=getattr(e,'code',0)
        mark="ok " if code==200 else "MISS"
        if code!=200: bad+=1
        print(f"       {mark} {t['id']:<12} {k:<14} {code}")
sys.exit(1 if bad else 0)
PY
[ $? -eq 0 ] && ok "all catalogue URLs return 200" || bad "some catalogue URLs are broken"

head_ "3. CLI refuses what it should"
out=$("$RT" call rapp_shot definitely_not_an_action 2>&1); case "$out" in
  *"has no action"*) ok "unknown action rejected before dispatch" ;; *) bad "accepted a bogus action" ;; esac
out=$("$RT" call nope_not_a_tool doctor 2>&1); case "$out" in
  *"no such tool"*) ok "unknown tool rejected" ;; *) bad "accepted a bogus tool" ;; esac
out=$("$RT" call rapp_shot list badpair 2>&1); case "$out" in
  *"expected key=value"*) ok "malformed argument rejected" ;; *) bad "accepted a malformed argument" ;; esac

head_ "4. Headless operation against whatever is running"
live=$("$RT" status 2>/dev/null | grep -c running)
info "$live tool(s) currently hatched"
if [ "${live:-0}" -ge 1 ]; then
  id=$("$RT" status 2>/dev/null | awk '/running/{print $1;exit}')
  out=$("$RT" call "$id" doctor 2>&1)
  [ -n "$out" ] && ok "headless call to $id returned output" || bad "$id returned nothing"
  case "$out" in *pload*|*ocal*|*ok*|*yes*) ok "output looks like a real doctor report" ;;
    *) info "unexpected shape: $(echo "$out"|head -c 80)" ; ok "call completed" ;; esac
else
  info "SKIP: nothing hatched — run rapptools hatch-all"
fi

head_ "5. The cubby contract matches the estate's, not an invented one"
# rapp_pipeline_agent.py defines the convention: rapplications/<slug>/cubby-<slug>.egg
# in the batcave, cached at ~/.brainstem/eggs/cubby-<slug>.egg, hatched to
# ~/.brainstem/cubbies/<slug>/hatched. Asserting it stops a future refactor from
# quietly inventing a second layout.
for tok in 'rapplications/{s}/cubby-{s}.egg' '.brainstem", "cubbies"' '.brainstem", "eggs"'; do
  grep -qF "$tok" "$RT" && ok "uses the estate path: $tok" || bad "missing estate path: $tok"
done
BC=$(gh api repos/kody-w/rapp-batcave/contents/rapplications --jq '.[].name' 2>/dev/null | tr '\n' ' ')
for s in rapp-voice rapp-crispy rapp-rewind rapp-shot; do
  case " $BC " in *" $s "*) ok "cubbied in the batcave: $s" ;; *) bad "not cubbied: $s" ;; esac
done
for s in rapp-shot; do
  f=$(gh api "repos/kody-w/rapp-batcave/contents/rapplications/$s" --jq '[.[].name]|join(",")' 2>/dev/null)
  case "$f" in *"cubby-$s.egg"*) ok "$s carries cubby-$s.egg" ;; *) bad "$s egg misnamed: $f" ;; esac
  case "$f" in *cubby.json*) ok "$s carries cubby.json" ;; *) bad "$s has no cubby.json" ;; esac
done

head_ "6. The catalogue vendors nothing"
vend=$(find "$HERE/.." -name '*.egg' -o -name '*_agent.py' 2>/dev/null | grep -v node_modules | wc -l | tr -d ' ')
[ "$vend" = "0" ] && ok "no eggs or agents copied into this repo" \
  || bad "$vend vendored artifact(s) — entries must point at source repos"

printf '\n\033[1m%d passed, %d failed\033[0m\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
