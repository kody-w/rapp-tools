#!/usr/bin/env python3
"""Archive or release a native app using Xcode-managed Developer ID and notarization."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = {
    "RAPPShot": ("io.rapp.shot", False),
    "RAPPRewind": ("io.rapp.rewind", False),
    "RAPPVoice": ("io.rapp.voice", True),
    "RAPPCrispy": ("io.rapp.crispy", True),
}
PRODUCT_IDS = {
    "RAPPShot": "rapp_shot",
    "RAPPRewind": "rapp_rewind",
    "RAPPVoice": "rapp_voice",
    "RAPPCrispy": "rapp_crispy",
}


class ReleaseError(RuntimeError):
    pass


def command(arguments: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(arguments, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stdout + result.stderr)[-10000:]
        raise ReleaseError(f"{arguments[0]} failed ({result.returncode}):\n{detail}")
    return result.stdout + result.stderr


def source_commit(repo: Path) -> str:
    dirty = command(["git", "-C", str(repo), "status", "--porcelain"]).strip()
    if dirty:
        raise ReleaseError("Release source has uncommitted changes; commit the tested source first.")
    revision = command(["git", "-C", str(repo), "rev-parse", "HEAD"]).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ReleaseError("Release source did not resolve to a full Git commit.")
    return revision


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for data in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def only_app(directory: Path) -> Path:
    apps = list(directory.glob("*.app"))
    if len(apps) != 1:
        raise ReleaseError(f"Expected one application in {directory.name}; found {len(apps)}.")
    return apps[0]


def portable_report(output: str, app: Path) -> str:
    aliases = {str(app), str(app.resolve())}
    for alias in sorted(aliases, key=len, reverse=True):
        output = output.replace(alias, app.name)
    return output


def signature_info(path: Path, expected_team: str, report_root: Path | None = None) -> dict:
    verified = command(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(path)])
    detail = command(["codesign", "-d", "--verbose=4", str(path)])
    lines = detail.splitlines()
    developer_id = any(line.startswith("Authority=Developer ID Application:") for line in lines)
    authority = next((line.partition("=")[2] for line in lines
                      if line.startswith("Authority=Developer ID Application:")), None)
    runtime = any("runtime" in line for line in lines if line.startswith("CodeDirectory"))
    team = next((line.partition("=")[2] for line in lines if line.startswith("TeamIdentifier=")), None)
    cdhash = next((line.partition("=")[2] for line in lines if line.startswith("CDHash=")), None)
    timestamp = next((line.partition("=")[2] for line in lines if line.startswith("Timestamp=")), None)
    entitlement_result = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(path)],
        text=True, capture_output=True, check=True,
    )
    entitlements = plistlib.loads(entitlement_result.stdout.encode()) if entitlement_result.stdout.strip() else {}
    if not developer_id or not runtime or team != expected_team or not timestamp:
        raise ReleaseError(f"{path.name} is missing verified Developer ID/runtime/timestamp/team requirements.")
    if entitlements.get("com.apple.security.get-task-allow", False):
        raise ReleaseError(f"{path.name} retained a development debugging entitlement.")
    return {
        "developer_id": developer_id,
        "hardened_runtime": runtime,
        "team_id": team,
        "code_directory_hash": cdhash,
        "secure_timestamp": timestamp,
        "get_task_allow": False,
        "authority": authority,
        "codesign_details": portable_report(detail, report_root or path),
        "codesign_verify": {
            "exit_code": 0, "output": portable_report(verified, report_root or path),
        },
    }


def verify_app(app: Path, product: str, architecture: str, team: str) -> dict:
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    bundle_id, needs_speech = PRODUCTS[product]
    if info.get("CFBundleIdentifier") != bundle_id:
        raise ReleaseError("The exported application has the wrong bundle identifier.")
    executable = app / "Contents/MacOS" / info["CFBundleExecutable"]
    architectures = command(["lipo", "-archs", str(executable)]).strip().split()
    if architectures != [architecture]:
        raise ReleaseError(f"Wrong application architecture: {architectures}")
    minimum = str(info.get("LSMinimumSystemVersion", ""))
    if not re.fullmatch(r"14(?:\.0){0,2}", minimum):
        raise ReleaseError(f"Unexpected minimum macOS version: {minimum}")
    version = str(info.get("CFBundleShortVersionString", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseError("The native application must declare a full release version.")
    command(["codesign", "--verify", "--deep", "--strict", str(app)])
    signing = signature_info(app, team)
    signing["architectures"] = architectures
    stapler = command(["xcrun", "stapler", "validate", str(app)])
    assessment = command(["spctl", "--assess", "--type", "execute", "--verbose=4", str(app)])
    if "source=Notarized Developer ID" not in assessment:
        raise ReleaseError("Gatekeeper did not recognize a notarized Developer ID application.")
    helpers = []
    if needs_speech:
        helper = app / "Contents/MacOS/whisper-cli"
        if not helper.is_file():
            raise ReleaseError("The speech application is missing its bundled whisper-cli.")
        if command(["lipo", "-archs", str(helper)]).strip().split() != [architecture]:
            raise ReleaseError("The speech helper architecture does not match the application.")
        helpers.append({
            "path": "Contents/MacOS/whisper-cli",
            "sha256": sha256(helper),
            "signing": signature_info(helper, team, report_root=app),
        })
    return {
        "bundle_id": bundle_id,
        "version": version,
        "minimum_macos": minimum,
        "architecture": architecture,
        "signing": signing,
        "notarization": {
            "method": "stapled-app", "app_path": app.name,
            "bundle_id": bundle_id, "version": version, "minimum_os": minimum,
        },
        "gatekeeper": {"exit_code": 0, "output": portable_report(assessment, app)},
        "stapler": {"exit_code": 0, "output": portable_report(stapler, app)},
        "helpers": helpers,
    }


def stage_runtime(app: Path, runtime_root: Path, architecture: str) -> dict:
    runtime = runtime_root / architecture
    manifest = json.loads((runtime / "runtime.json").read_text())
    lock = json.loads((ROOT / "native/dependencies/whisper.json").read_text())
    helper = runtime / "bin/whisper-cli"
    if manifest.get("architecture") != architecture:
        raise ReleaseError("Runtime manifest has the wrong architecture.")
    for key in ("name", "version", "minimum_macos", "source_url", "source_sha256", "license"):
        if manifest.get(key) != lock.get(key):
            raise ReleaseError("The speech runtime provenance differs from the reviewed dependency lock.")
    if manifest.get("executable") != "bin/whisper-cli":
        raise ReleaseError("The speech runtime has an unexpected build-relative executable path.")
    if sha256(helper) != manifest.get("executable_sha256"):
        raise ReleaseError("The staged speech runtime does not match its verified build.")
    libraries = command(["otool", "-L", str(helper)]).splitlines()[1:]
    for line in libraries:
        library = line.strip().split(" (", 1)[0]
        if library and not library.startswith(("/usr/lib/", "/System/Library/")):
            raise ReleaseError("The speech runtime still requires a non-system dynamic library.")
    destination = app / "Contents/MacOS/whisper-cli"
    shutil.copy2(helper, destination)
    destination.chmod(0o755)
    command(["codesign", "--force", "--sign", "-", "--options", "runtime", str(destination)])
    resource = app / "Contents/Resources/runtime"
    resource.mkdir(parents=True, exist_ok=True)
    shutil.copytree(runtime / "licenses", resource / "licenses", dirs_exist_ok=True)
    provenance = {
        **manifest,
        "provenance_scope": "pre-sign-build",
        "build_manifest_sha256": sha256(runtime / "runtime.json"),
        "bundle_executable": "Contents/MacOS/whisper-cli",
        "signed_executable_evidence": "release-result.json#/verification/helpers",
    }
    (resource / "runtime.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return provenance


def stage_icon(app: Path, product: str, attempt: Path) -> None:
    iconset = attempt / f"{product}.iconset"
    command(["swift", str(ROOT / "native/packaging/make_icon.swift"), product, str(iconset)])
    resource = app / "Contents/Resources"
    resource.mkdir(parents=True, exist_ok=True)
    command(["iconutil", "-c", "icns", str(iconset), "-o", str(resource / "RAPPApp.icns")])
    info_path = app / "Contents/Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info["CFBundleIconFile"] = "RAPPApp"
    info.pop("CFBundleIconName", None)
    info["LSApplicationCategoryType"] = "public.app-category.productivity"
    info_path.write_bytes(plistlib.dumps(info))


def export_notarized(archive: Path, attempt: Path, team: str, wait_seconds: int) -> Path:
    options = attempt / "notarization-options.plist"
    options.write_bytes(plistlib.dumps({
        "method": "developer-id",
        "destination": "upload",
        "signingStyle": "automatic",
        "teamID": team,
        "uploadSymbols": False,
    }))
    print("Submitting the application through Xcode-managed signing and notarization...", flush=True)
    command([
        "xcodebuild", "-quiet", "-exportArchive", "-archivePath", str(archive),
        "-exportOptionsPlist", str(options), "-exportPath", str(attempt / "upload"),
        "-allowProvisioningUpdates",
    ])
    exported = attempt / "notarized"
    deadline = time.monotonic() + wait_seconds
    while True:
        result = subprocess.run([
            "xcodebuild", "-quiet", "-exportNotarizedApp",
            "-archivePath", str(archive), "-exportPath", str(exported),
        ], text=True, capture_output=True)
        if result.returncode == 0:
            return only_app(exported)
        detail = result.stdout + result.stderr
        waiting = any(word in detail.lower() for word in (
            "in progress", "not yet", "processing", "has not completed",
        ))
        if not waiting or time.monotonic() >= deadline:
            raise ReleaseError("Notarized export did not complete:\n" + detail[-6000:])
        print("Apple notarization is still processing; checking again in 30 seconds.", flush=True)
        time.sleep(30)


def build(args) -> dict:
    repo = args.repo.resolve()
    source = source_commit(repo)
    tooling_source = source_commit(ROOT)
    if not re.fullmatch(r"[A-Z0-9]{10}", args.team_id):
        raise ReleaseError("Provide the authorized Apple development team identifier.")
    native = repo / "native"
    specification = native / "project.yml"
    if not specification.is_file():
        raise ReleaseError("The application is missing native/project.yml.")
    attempt = args.output.resolve() / args.product / args.arch / (source[:12] + "-" + uuid.uuid4().hex[:8])
    attempt.mkdir(parents=True, exist_ok=False)
    command(["xcodegen", "generate", "--quiet", "--spec", str(specification)], cwd=native)
    if not args.skip_tests:
        print("Running native application tests...", flush=True)
        command(["swift", "test", "-j", "2"], cwd=native)
    archive = attempt / f"{args.product}.xcarchive"
    print(f"Archiving {args.product} for {args.arch}...", flush=True)
    command([
        "xcodebuild", "-quiet", "-project", str(native / f"{args.product}.xcodeproj"),
        "-scheme", args.product, "-configuration", "Release",
        "-destination", "generic/platform=macOS",
        "-archivePath", str(archive), "-derivedDataPath", str(attempt / "DerivedData"),
        "-jobs", "2", "-allowProvisioningUpdates",
        f"ARCHS={args.arch}", "ONLY_ACTIVE_ARCH=NO",
        "CODE_SIGN_STYLE=Automatic", "CODE_SIGN_IDENTITY=Apple Development",
        "CODE_SIGNING_ALLOWED=YES", "CODE_SIGNING_REQUIRED=YES",
        f"DEVELOPMENT_TEAM={args.team_id}", "ENABLE_HARDENED_RUNTIME=YES",
        "archive",
    ], cwd=native)
    app = only_app(archive / "Products/Applications")
    runtime = None
    if PRODUCTS[args.product][1]:
        runtime = stage_runtime(app, args.runtime_root.resolve(), args.arch)
    stage_icon(app, args.product, attempt)
    result = {
        "schema": "rapp-native-release-result/1.0",
        "product": args.product,
        "rapplication_id": PRODUCT_IDS[args.product],
        "source_commit": source,
        "tooling_source_commit": tooling_source,
        "architecture": args.arch,
        "distribution_verified": False,
    }
    if args.action == "archive":
        result["phase"] = "archived-not-for-distribution"
    else:
        app = export_notarized(archive, attempt, args.team_id, args.wait_seconds)
        verification = verify_app(app, args.product, args.arch, args.team_id)
        filename = f"{PRODUCT_IDS[args.product]}-{verification['version']}-{args.arch}.zip"
        artifact = attempt / filename
        command(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(artifact)])
        roundtrip = attempt / "download-roundtrip"
        command(["ditto", "-x", "-k", str(artifact), str(roundtrip)])
        verify_app(only_app(roundtrip), args.product, args.arch, args.team_id)
        result.update({
            "phase": "verified",
            "distribution_verified": True,
            "verification": verification,
            "artifact": {
                "filename": filename, "format": "zip",
                "sha256": sha256(artifact), "bytes": artifact.stat().st_size,
            },
            "runtime": runtime,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })
    (attempt / "release-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--product", choices=sorted(PRODUCTS), required=True)
    parser.add_argument("--arch", choices=["arm64", "x86_64"], required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--action", choices=["archive", "release"], required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "native/dist/apps")
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "native/dist/runtime")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.wait_seconds < 30 or args.wait_seconds > 3600:
        parser.error("--wait-seconds must be between 30 and 3600")
    build(args)


if __name__ == "__main__":
    main()
