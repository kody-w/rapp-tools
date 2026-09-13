#!/usr/bin/env python3
"""Build deterministic, licensed tooling bundles from immutable public sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


AUTHORITY_COMMIT = "dda32d741c7218f41443a5bd17eebfe0eae82cb7"
WORKSPACE_COMMIT = "44f6f124c47ed610b32e4d78f596b9b099669657"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files(root: Path, commit: str) -> dict[str, bytes]:
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != commit:
        raise ValueError("Source checkout is not the selected immutable revision")
    subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD"], check=True)
    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).split(b"\0")
    result = {}
    for raw in names:
        if not raw:
            continue
        name = raw.decode("utf-8")
        path = root / name
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if root.resolve() not in resolved.parents or not resolved.is_file():
                raise ValueError("Selected source contains an external or invalid symlink")
        result[name] = path.read_bytes()
    if "LICENSE" not in result or not result["LICENSE"].startswith(b"MIT License"):
        raise ValueError("Selected public source must carry its redistribution license")
    return result


def selected_authority(files: dict[str, bytes]) -> dict[str, bytes]:
    roots = {
        "rapp.py", "rapp_registry.py", "rapp_profile.py", "rapp_cicd.py",
        "rapp_deploy.py", "SPEC.md", "LICENSE", "FOUNDATION.json",
    }
    return {
        path: data for path, data in files.items()
        if path in roots
        or path.startswith(("anchor/", "protocols/rapp-cicd/", "protocols/rapp-deploy/"))
        or path == "protocols/index.json"
    }


def selected_workspace(files: dict[str, bytes]) -> dict[str, bytes]:
    roots = {"SPEC.md", "README.md", "SKILL.md", "LICENSE",
             "tools/workspace_manager.py", "tools/append_frame.py"}
    return {
        path: data for path, data in files.items()
        if path in roots
        or path.startswith((".github/skills/", "protocols/"))
    }


def build_bundle(kind: str, repository: str, commit: str,
                 files: dict[str, bytes], output: Path) -> dict:
    manifest = {
        "schema": "rapp-workspace-tool-bundle/1",
        "kind": kind,
        "repository": repository,
        "commit": commit,
        "license": "MIT",
        "files": [
            {"path": path, "bytes": len(data), "sha256": digest(data)}
            for path, data in sorted(files.items())
        ],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    target = output / f"{kind}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in [("bundle-manifest.json", manifest_bytes), *sorted(files.items())]:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    content = target.read_bytes()
    return {
        "repository": repository,
        "commit": commit,
        "filename": target.name,
        "sha256": digest(content),
        "bytes": len(content),
        "file_count": len(files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    pins = {
        "schema": "rapp-workspace-source-pins/1",
        "authority": build_bundle(
            "authority", "kody-w/rapp-1", AUTHORITY_COMMIT,
            selected_authority(source_files(args.authority_root, AUTHORITY_COMMIT)), args.output
        ),
        "workspace": build_bundle(
            "workspace", "kody-w/rapp-workspace", WORKSPACE_COMMIT,
            selected_workspace(source_files(args.workspace_root, WORKSPACE_COMMIT)), args.output
        ),
    }
    (args.output.parent / "pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    print(json.dumps(pins, indent=2))


if __name__ == "__main__":
    main()
