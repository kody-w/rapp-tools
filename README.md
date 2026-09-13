# RAPP Tools

Discovery and build infrastructure for four independent local-first macOS apps.

## Native application downloads

| Application | Native release |
|---|---|
| RAPP Voice | [1.1.1 - Apple silicon and Intel](https://github.com/kody-w/rapp-voice/releases/tag/v1.1.1) |
| RAPP Crispy | [1.5.1 - Apple silicon and Intel](https://github.com/kody-w/rapp-crispy/releases/tag/v1.5.1) |
| RAPP Rewind | [1.2.1 - Apple silicon and Intel](https://github.com/kody-w/rapp-rewind/releases/tag/v1.2.1) |
| RAPP Shot | [1.3.1 - Apple silicon and Intel](https://github.com/kody-w/rapp-shot/releases/tag/v1.3.1) |

Requires macOS 14 or newer. Unzip the architecture-specific download in Finder
and move the app to Applications. Released apps are Developer ID-signed,
notarized and stapled; each release provides immutable verification reports.
No Brainstem, Homebrew, Hammerspoon, Python or terminal is required for normal
native use. First-run setup controls speech-model downloads and OS permissions;
optional cloud processing is disabled until explicit consent.

## Refresh an application and keep its source layout

[RAPP Workspace Refresh](skills/rapp-workspace-refresh/SKILL.md) audits and
modernizes an application repository through a reusable, portable skill. Its
operator inventories source and nested archives without running application
code, verifies the pinned current RAPP/1 reference, and prepares an additive
root skill entry plus a checksum-pinned bootstrap. Existing root skill content
and case-sensitive public URLs are preserved.

The skill is also published in the separate
[RAR Skills catalog](https://kody-w.github.io/RAR/skills.html), with an immutable
source revision and per-file hashes. It is not an agent-registry entry.

```sh
python3 rapp_workspace.py audit /path/to/application --allow-network
python3 rapp_workspace.py prepare /path/to/application --apply
python3 rapp_workspace.py bootstrap /path/to/application --apply \
  --owner example --world-id local-personal --allow-network
python3 rapp_workspace.py verify /path/to/application --allow-network
```

Use the actual owner/world rather than the example. Both `prepare` and
`bootstrap` are **plan-only without `--apply`**. A clone does not execute code:
after reviewing/trusting it, follow its root skill entry. First use needs
explicit public network access or verified offline operator/bundles; warm
bootstrap is offline-capable. Source stays in place; private state stays in
`.rapp/workspace`, `.rapp/cache`, and `.rapp/reports`, excluded from Git. Existing
workspace identities are reused or explicitly blocked for additive migration.
No global Brainstem, service, signing key, or publication is created.

The host performs the full semantic review, redesign and app-specific
regressions; the deterministic scan is not a claim to understand every source
file. Application readiness, workspace readiness, exact-integer artifact
diagnostics, authenticated RAPP/1 acceptance, and production conformance are
separate. Floating-point/full-JCS and missing authenticated owner evidence
remain explicit blockers. A successful scan or bootstrap is **not a RAPP/1
certificate**. `--allow-network` checks protected canonical freshness and never
silently adopts a new specification.

Tooling bundles under `workspace/artifacts/` are licensed, checksum-pinned
reference sources, not protocol eggs or application installers. Their source
commits and exact manifests are in `workspace/pins.json`. Reproduce the skill
with `tools/build_refresh_skill.py --converter /reviewed/rapp_skills.py`; the
converter verifies the skill and proves its code comes back unchanged, including
the complete host workflow.

The public [RAPP Store](https://kody-w.github.io/RAPP_Store/) is the app catalog.
RAPP Tools is shared infrastructure, **not a fifth application**. Native release
metadata lives in each catalog entry's `native_release`; the older top-level
versions, engine requirements and egg hashes describe the retained CLI/twin
compatibility path, not the native downloads.

## Native macOS build support

The root Swift package, `RAPPDesktopSupport`, is shared build-time source for
the four independent macOS applications. It provides bundled-helper discovery,
cancellable process execution, checksum-verified model installation, and local
whisper.cpp transcription. It is not a fifth application or a required
separate installation.

Run its tests with `swift test -j 2`. Native dependencies are pinned under
`native/dependencies/`. Speech models download only after the application
asks the user; the approved model files have immutable source revisions,
declared sizes, SHA-256 values, and license links. Captured audio is never
uploaded by this package.

Consumer apps resolve executables inside their signed application bundle.
`RAPP_RUNTIME_BIN` is an explicit development/test override, not a consumer
Homebrew or shell-PATH requirement. Native release availability must be
established from verified published artifacts, not inferred from a passing
Swift build or the historical cartridges below.

## Historical CLI and twin integration

Every tool here is a **hatchable rapplication**: it boots into its own brainstem
on its own port carrying only its own agent, and is driven **headlessly** over the
same `/chat` contract. Each ships a UI, but nothing requires one — an agent, a
script or a person all use the identical interface.

```bash
rapptools list                          # what exists
rapptools hatch-all                     # boot the fleet
rapptools call rapp_shot redact auto=true dry_run=true
rapptools ask rapp_rewind "what did I see about pricing yesterday?"
rapptools status
```

## The catalogue

| Tool | Port | What it does |
|---|---|---|
| [`rapp_voice`](https://github.com/kody-w/rapp-voice) | 7091 | Hold a key, speak, release — cleaned text at your cursor |
| [`rapp_crispy`](https://github.com/kody-w/rapp-crispy) | 7090 | Record, denoise, transcribe and summarise meetings |
| [`rapp_rewind`](https://github.com/kody-w/rapp-rewind) | 7092 | Searchable memory of everything on your screen |
| [`rapp_shot`](https://github.com/kody-w/rapp-shot) | 7093 | Screenshots that auto-redact credentials |

All four tools' **engines** run on-device. Read the privacy note below before you
assume that covers the twin path too — it does not.

## Two paths, two different privacy properties

Be precise about this, because the distinction is real and a user can be burned by it:

**The engines are on-device.** Capture, OCR, denoising, speech recognition,
annotation, redaction, indexing and search all run locally. Your screenshots,
recordings and transcripts are produced and stored on your own disk, and the CLIs
make no network call at all — a test asserts that.

**The twin's conversation layer is not.** Driving a rapplication over `/chat`
routes your prompt *and whatever the agent returns* through whichever LLM the host
brainstem is configured with. On a default install that is the GitHub Copilot API
(`Auth: GitHub Copilot API (via gh CLI)`). So asking a twin "what did I see about
the pricing deck?" sends the OCR'd text of your screen to that model.

If you need the strict guarantee, **use the CLI** (`shot`, `rewind`, `crispy`) —
that path is fully local. The twin exists to make the tools agent-drivable, and it
inherits the host brainstem's model, whatever that is. Point the brainstem at a
local model and the twin becomes local too.

## Application artifacts stay in their own repositories

Catalogue entries point at each tool's own repository via
`raw.githubusercontent.com`. No egg, agent or UI is copied here, so each tool's
repo stays the source of truth and this catalogue cannot silently drift from it.
The separate refresh skill and licensed protocol/workspace tooling bundles
are build/operator capabilities, not copies of those four applications.

What is centralised is **discovery and operation** — the part that was actually
scattered across four repos.

## Headless is the point

The reason these are rapplications rather than just CLIs: an agent can drive them
without a human, a terminal or a window.

```bash
# structured — an action plus validated key=value arguments
rapptools call rapp_crispy run seconds=600 name=standup

# or natural language into the same agent
rapptools ask rapp_shot "capture the screen and paint out anything that looks like a key"
```

Both paths reach the agent through the same `/chat` endpoint. There is no second,
privileged interface — which is why anything that can POST JSON can operate the
whole fleet:

```bash
curl -s localhost:7093/chat -H 'Content-Type: application/json' \
  -d '{"user_input":"RappShot {\"action\":\"doctor\"}"}'
```

Unknown actions are rejected **before** dispatch against the catalogue's declared
action list, so a typo fails locally rather than becoming an odd conversation.

## Cubbying and hatching from the private batcave

These follow the estate's existing cubby contract — the one
`rapp_pipeline_agent.py` already resolves against — rather than a new layout:

```
batcave   rapplications/<slug>/cubby-<slug>.egg   +  cubby.json (rapp-cubby/1.0)
cache     ~/.brainstem/eggs/cubby-<slug>.egg
hatched   ~/.brainstem/cubbies/<slug>/hatched
```

`rapptools hatch` resolves in that order — cached cubby egg, then the private
batcave over `gh`, then the public repo, then a local checkout — and tells you
which one it used:

```bash
rapptools hatch rapp_shot --source batcave
  rapp_shot hatched on :7093
    egg      kody-w/rapp-batcave:rapplications/rapp-shot/cubby-rapp-shot.egg
    cubby    ~/.brainstem/cubbies/rapp-shot/hatched
```

Verified end to end: with every hatched tree and cached egg deleted,
`rapptools hatch-all --source batcave` brings the whole fleet back from the
private batcave alone and each one answers real work.

## How hatching works

Per `rapp-application/1.0` §13: the egg is unzipped into an isolated twin root
under `~/.rappfleet/<id>/`, a brainstem boots there bound to the tool's port with
`SOUL_PATH` and `AGENTS_PATH` pointed at that root, and only that tool's agent
loads. The host brainstem's own agent namespace is never touched, so ten tools
do not crowd one tool list.

Each is also a uniform neighbour on the wire — the neighbourhood-protocol
twin-chat adapter reaches every one of them unchanged.

## Legacy CLI installation (not required for native apps)

```bash
git clone https://github.com/kody-w/rapp-tools.git
cd rapp-tools && ./install.sh
rapptools hatch-all
```

Needs a RAPP brainstem at `~/.brainstem`. Each tool's own engines (ffmpeg,
whisper.cpp, the Vision shims) are that tool's dependency, listed in
`rapptools list -v` and checked by its own `doctor`.

Legacy hatching still verifies the retained catalog archive digest, but does
not confer current RAPP/1 conformance. Missing digests refuse execution.
`hatch --force` and `stop` now operate only on a process launched by this CLI
whose PID/start identity still matches its private receipt. An existing
launchd job or an unrelated port owner is left untouched; manage it through its
actual owner first. Replacement stages and verifies archive contents, carries
local twin state, and retains the prior full installation as a named backup.
The host's own data directory remains governed by that host.

Historical archives are immutable. `tools/rebuild-eggs.sh --check` verifies
their original catalog hashes only; default rebuilding/overwriting is retired.
Native successors do not regenerate old protocol forms. `tools/dryrun.sh`
defaults to offline `--safe`; `--live-legacy` explicitly opts into the older
network/private-fleet checks and is not an application compliance gate.

## Adding a tool

Append an entry to `catalog/catalog.json` with `id`, `repo`, `port`, `agent`,
`actions`, `engines`, `needs` and the `raw.githubusercontent.com` URLs for its
egg, manifest and singleton. The suite will then assert the URLs resolve and the
port is unique.

## Tests

```bash
./tools/dryrun.sh --safe                # native catalog only: no services, capture, private repos
./tools/dryrun.sh
```

The unflagged command is the historical integration suite and may contact
configured services/private repositories; it is not needed for native app
installation. Its assertions cover catalogue integrity, unique ports, every URL live, argument and
action validation, a real headless call against whatever is hatched, and that
nothing has been vendored.

MIT.
