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

All four run entirely on-device. No account, no upload, no retention policy.

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
