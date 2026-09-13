#!/usr/bin/env python3
"""Bind a verified native ZIP and public build run to the RAPP Store evidence contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import tempfile
import urllib.request
import zipfile

import release_app


def check_zip_paths(archive: Path, app_name: str) -> None:
    with zipfile.ZipFile(archive) as source:
        total = 0
        seen: set[str] = set()
        for info in source.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise release_app.ReleaseError("Native ZIP contains an unsafe path.")
            if path.parts[0] not in (app_name, "__MACOSX"):
                raise release_app.ReleaseError("Native ZIP contains an unexpected top-level item.")
            if info.filename in seen:
                raise release_app.ReleaseError("Native ZIP contains duplicate entries.")
            seen.add(info.filename)
            total += info.file_size
            if total > 4 * 1024 * 1024 * 1024:
                raise release_app.ReleaseError("Native ZIP exceeds the extraction limit.")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                target = source.read(info).decode("utf-8")
                resolved = posixpath.normpath(posixpath.join(str(path.parent), target))
                if target.startswith("/") or not resolved.startswith(app_name + "/"):
                    raise release_app.ReleaseError("Native ZIP symlink escapes its application.")
            elif stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise release_app.ReleaseError("Native ZIP contains a special filesystem entry.")


def verify_workflow(url: str, repo: str, commit: str) -> None:
    pattern = rf"https://github\.com/{re.escape(repo)}/actions/runs/([1-9][0-9]*)"
    match = re.fullmatch(pattern, url)
    if not match:
        raise release_app.ReleaseError("Workflow URL must belong to the native source repository.")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/runs/{match.group(1)}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "RAPP-native-release/1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise release_app.ReleaseError("Workflow response exceeded its size limit.")
    run = json.loads(body)
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("head_sha") != commit
        or run.get("repository", {}).get("full_name") != repo
    ):
        raise release_app.ReleaseError("The public workflow did not successfully verify this source commit.")


def make_evidence(result_path: Path, repo: str, workflow_run: str) -> dict:
    result = json.loads(result_path.read_text())
    if result.get("distribution_verified") is not True:
        raise release_app.ReleaseError("The input is not a verified native distribution result.")
    product = result["product"]
    rapp_id = release_app.PRODUCT_IDS[product]
    if result.get("rapplication_id") != rapp_id:
        raise release_app.ReleaseError("Native result application identity mismatch.")
    expected_repo = "kody-w/" + rapp_id.replace("_", "-")
    if repo != expected_repo:
        raise release_app.ReleaseError("The source repository does not match the application.")
    verification = result["verification"]
    version = verification["version"]
    arch = result["architecture"]
    filename = f"{rapp_id}-{version}-{arch}.zip"
    artifact = result["artifact"]
    if artifact.get("filename") != filename or artifact.get("format") != "zip":
        raise release_app.ReleaseError("Native result has an unexpected archive name or format.")
    archive = result_path.parent / filename
    if (
        archive.stat().st_size != artifact["bytes"]
        or release_app.sha256(archive) != artifact["sha256"]
    ):
        raise release_app.ReleaseError("The native archive changed after distribution verification.")
    commit = result["source_commit"]
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise release_app.ReleaseError("The native source commit is not immutable.")
    verify_workflow(workflow_run, repo, commit)
    app_name = verification["notarization"]["app_path"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()-]*\.app", app_name):
        raise release_app.ReleaseError("Native result has an unsafe application name.")
    check_zip_paths(archive, app_name)
    with tempfile.TemporaryDirectory(prefix="rapp-evidence-") as temporary:
        extracted = Path(temporary)
        release_app.command(["ditto", "-x", "-k", str(archive), str(extracted)])
        observed = release_app.verify_app(
            release_app.only_app(extracted), product, arch, verification["signing"]["team_id"]
        )
    if observed["version"] != version or observed["bundle_id"] != verification["bundle_id"]:
        raise release_app.ReleaseError("The extracted native application does not match its build record.")
    asset_url = f"https://github.com/{repo}/releases/download/v{version}/{filename}"
    signing = observed["signing"]
    evidence = {
        "schema": "rapp-desktop-evidence/1.0",
        "subject": {
            "id": rapp_id, "version": version, "bundle_id": observed["bundle_id"],
            "arch": arch, "url": asset_url, "bytes": artifact["bytes"],
            "sha256": artifact["sha256"],
        },
        "source": {"repo": repo, "commit_sha": commit},
        "workflow_run": workflow_run,
        "signing": {
            key: signing[key] for key in (
                "team_id", "authority", "codesign_details", "codesign_verify", "architectures"
            )
        },
        "notarization": observed["notarization"],
        "gatekeeper": observed["gatekeeper"],
        "stapler": observed["stapler"],
    }
    evidence_bytes = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
    evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
    evidence_name = filename + f".evidence.{evidence_hash}.json"
    evidence_path = result_path.parent / evidence_name
    if evidence_path.exists() and evidence_path.read_bytes() != evidence_bytes:
        raise release_app.ReleaseError("Existing immutable evidence does not match its content address.")
    if not evidence_path.exists():
        evidence_path.write_bytes(evidence_bytes)
    entry = {
        "arch": arch, "format": "zip", "url": asset_url,
        "bytes": artifact["bytes"], "sha256": artifact["sha256"],
        "evidence": {
            "url": f"https://github.com/{repo}/releases/download/v{version}/{evidence_name}",
            "bytes": evidence_path.stat().st_size,
            "sha256": release_app.sha256(evidence_path),
        },
    }
    (result_path.parent / (filename + ".descriptor.json")).write_text(
        json.dumps(entry, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(entry, indent=2))
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--workflow-run", required=True)
    args = parser.parse_args()
    make_evidence(args.result.resolve(), args.repo, args.workflow_run)


if __name__ == "__main__":
    main()
