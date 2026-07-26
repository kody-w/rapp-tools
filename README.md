# RAPP Tools

One catalogue and one command for the local-first RAPP tools.

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

## Nothing is vendored

Catalogue entries point at each tool's own repository via
`raw.githubusercontent.com`. No egg, agent or UI is copied here, so each tool's
repo stays the source of truth and this catalogue cannot silently drift from it.
A test asserts that no artifact has been copied in, and another asserts every
catalogue URL still returns 200.

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

## Install

```bash
git clone https://github.com/kody-w/rapp-tools.git
cd rapp-tools && ./install.sh
rapptools hatch-all
```

Needs a RAPP brainstem at `~/.brainstem`. Each tool's own engines (ffmpeg,
whisper.cpp, the Vision shims) are that tool's dependency, listed in
`rapptools list -v` and checked by its own `doctor`.

## Adding a tool

Append an entry to `catalog/catalog.json` with `id`, `repo`, `port`, `agent`,
`actions`, `engines`, `needs` and the `raw.githubusercontent.com` URLs for its
egg, manifest and singleton. The suite will then assert the URLs resolve and the
port is unique.

## Tests

```bash
./tools/dryrun.sh
```

9 assertions: catalogue integrity, unique ports, every URL live, argument and
action validation, a real headless call against whatever is hatched, and that
nothing has been vendored.

MIT.
