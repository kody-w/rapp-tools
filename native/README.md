# Native macOS build infrastructure

This directory builds dependencies and release packages for four independently
installed applications. RAPP Tools is not an additional end-user app.

## Speech runtime

```sh
python3 native/packaging/build_whisper.py --arch arm64
python3 native/packaging/build_whisper.py --arch x86_64
```

The recipe verifies the upstream source archive before extraction, builds the
CPU backend with the macOS 14 deployment target, and refuses executables with
Homebrew or other non-system dynamic-library dependencies. Output lives in
`native/dist/runtime/<architecture>/` with licenses and a provenance manifest.
CMake and Xcode are build-time dependencies only. Nothing executes an upstream
installer or requires a package manager on a consumer's Mac.

The speech executable is a helper inside each speech application's signed
bundle. Build output alone is not a signed/notarized release. Final distribution
must verify nested signing, notarization, the stapled app/container, and hashes
of the final artifacts.

Model data is separate from executable code. The shared Swift package pins
approved base/small English models to an immutable repository revision and
verifies size and SHA-256 before activation. Apps must present the model's
identity, size, license and download location before starting a download.

## Signed native release

Commit the tested application and support package first. Configure the owner's
Apple developer account in Xcode; the release helper uses Xcode-managed
Developer ID signing and notarization rather than exporting credentials.

```sh
python3 native/packaging/release_app.py \
  --repo ../rapp-voice --product RAPPVoice --arch arm64 \
  --team-id YOUR_TEAM_ID --action release
```

Repeat for the other supported architecture and application. `--action archive`
is an explicit development-only operation, not a public release. The default
release path runs app tests, archives the native target, embeds verified
runtime helpers and original app artwork, uploads for managed notarization,
and retrieves the notarized application.

The output is a ZIP containing a signed, stapled, notarized `.app`. ZIP
containers cannot themselves be stapled: verification checks the enclosed
application, then hashes the final ZIP and verifies its extracted round trip.
End users unzip it in Finder and move the application to Applications; normal
installation does not require a terminal, Homebrew, Hammerspoon, or Python.

`release-result.json` records actual distribution checks and immutable source
commits. `distribution_verified` is not a substitute for application workflow,
privacy, hardware, and publication checks. Nothing in this helper changes a
live catalog or publishes a GitHub release.

After the native source commit has a successful public CI run, generate
store-bound evidence from the final ZIP:

```sh
python3 native/packaging/make_desktop_evidence.py \
  --result /path/to/release-result.json --repo kody-w/rapp-voice \
  --workflow-run https://github.com/kody-w/rapp-voice/actions/runs/RUN_ID
```

The emitter checks the workflow's actual repository, source commit, status,
and conclusion, then re-extracts and verifies the signed/stapled application.
It writes content-addressed `.zip.evidence.<sha256>.json` reports and an
artifact descriptor beside the ZIP, with actual command reports and final
byte/hash bindings. Corrections create new reports rather than overwriting
published evidence or native ZIPs. Local parent directories, including
macOS `/var`/`/private/var` aliases, are removed from reports; app-relative
identifiers and all verification results are preserved. Publishing the release
and submitting the catalog update remain explicit separate operations.

## Verification

```sh
swift test -j 2
python3 -m unittest discover -s native/verification -p 'test_*.py' -v
```

The `rapp-native-speech-smoke` executable exercises the same approved model
installer and bundled speech runtime as the apps. It accepts a synthetic WAV
and model path; it never opens the microphone. Set `RAPP_RUNTIME_BIN` explicitly
for a developer build. The app icon generator draws original geometry and
does not copy SF Symbols or third-party artwork into app icons.
