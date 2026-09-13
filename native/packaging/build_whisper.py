#!/usr/bin/env python3
"""Build a pinned, self-contained whisper-cli for one supported Mac architecture."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "native/dependencies/whisper.json"
ARCHIVE_LIMIT = 128 * 1024 * 1024
EXTRACTED_LIMIT = 512 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_source(lock: dict, cache: Path) -> Path:
    target = cache / f"whisper-{lock['version']}.tar.gz"
    if target.is_file() and sha256(target) == lock["source_sha256"]:
        return target
    if not lock["source_url"].startswith(
        "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/"
    ):
        raise ValueError("Whisper source must come from the declared upstream release archive")
    with tempfile.NamedTemporaryFile(prefix="download-", dir=cache, delete=False) as output:
        temporary = Path(output.name)
        try:
            request = urllib.request.Request(
                lock["source_url"], headers={"User-Agent": "RAPP-native-build/1"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                if not response.geturl().startswith("https://"):
                    raise ValueError("Source download redirected away from HTTPS")
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > ARCHIVE_LIMIT:
                        raise ValueError("Source archive exceeded its size limit")
                    output.write(block)
            output.flush()
            if sha256(temporary) != lock["source_sha256"]:
                raise ValueError("Whisper source archive failed SHA-256 verification")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def extract_verified(archive: Path, destination: Path) -> Path:
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        total = 0
        roots: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"Unsafe source archive path: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"Unsupported source archive member: {member.name}")
            total += member.size
            if total > EXTRACTED_LIMIT:
                raise ValueError("Extracted source archive exceeded its size limit")
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("Source archive must contain exactly one source root")
        source.extractall(destination, members=members, filter="data")
    return destination / next(iter(roots))


def inspect_binary(binary: Path, arch: str) -> list[str]:
    architectures = subprocess.check_output(
        ["lipo", "-archs", str(binary)], text=True
    ).strip().split()
    if architectures != [arch]:
        raise ValueError(f"Runtime architecture mismatch: {architectures}, expected {arch}")
    lines = subprocess.check_output(["otool", "-L", str(binary)], text=True).splitlines()[1:]
    libraries = [line.strip().split(" (", 1)[0] for line in lines if line.strip()]
    external = [
        name for name in libraries
        if not name.startswith(("/usr/lib/", "/System/Library/"))
    ]
    if external:
        raise ValueError(f"Runtime still depends on non-system libraries: {external}")
    return libraries


def build(arch: str, cache: Path, output: Path, jobs: int) -> dict:
    lock = json.loads(LOCK.read_text())
    if arch not in lock["architectures"]:
        raise ValueError(f"Unsupported architecture: {arch}")
    if jobs < 1 or jobs > 16:
        raise ValueError("jobs must be between 1 and 16")
    if shutil.which("cmake") is None:
        raise RuntimeError("Missing declared build dependency: cmake")
    cache.mkdir(parents=True, exist_ok=True)
    archive = download_source(lock, cache)
    options = dict(lock["cmake_options"])
    options.update({
        "CMAKE_OSX_ARCHITECTURES": arch,
        "GGML_METAL": "OFF",
        "GGML_BLAS": "ON",
        "GGML_BLAS_VENDOR": "Apple",
    })
    with tempfile.TemporaryDirectory(prefix=f"build-{arch}-", dir=cache) as temporary:
        build_root = Path(temporary)
        source = extract_verified(archive, build_root)
        compiled = build_root / "compiled"
        path_flags = shlex.join([
            f"-ffile-prefix-map={source}=whisper.cpp",
            f"-fdebug-prefix-map={build_root}=build",
        ])
        build_options = {
            **options,
            "CMAKE_C_FLAGS": path_flags,
            "CMAKE_CXX_FLAGS": path_flags,
        }
        subprocess.run([
            "cmake", "-S", str(source), "-B", str(compiled),
            *[f"-D{name}={value}" for name, value in sorted(build_options.items())],
        ], check=True)
        subprocess.run([
            "cmake", "--build", str(compiled), "--config", "Release",
            "--target", "whisper-cli", "--parallel", str(jobs),
        ], check=True)
        executable = compiled / "bin/whisper-cli"
        libraries = inspect_binary(executable, arch)
        strings = subprocess.check_output(["strings", str(executable)])
        if str(Path.home()).encode() + b"/" in strings:
            raise ValueError("Runtime contains a private local build path")
        destination = output / arch
        binaries = destination / "bin"
        notices = destination / "licenses"
        binaries.mkdir(parents=True, exist_ok=True)
        notices.mkdir(parents=True, exist_ok=True)
        shutil.copy2(executable, binaries / "whisper-cli")
        (binaries / "whisper-cli").chmod(0o755)
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
                relative = path.relative_to(source)
                target = notices / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        if not (notices / "LICENSE").is_file():
            raise ValueError("The upstream license is missing from the runtime bundle")
        result = {
            "schema": "rapp-native-runtime/1.0",
            "name": lock["name"],
            "version": lock["version"],
            "architecture": arch,
            "minimum_macos": lock["minimum_macos"],
            "backend": "cpu",
            "source_url": lock["source_url"],
            "source_sha256": lock["source_sha256"],
            "license": lock["license"],
            "executable": "bin/whisper-cli",
            "executable_sha256": sha256(binaries / "whisper-cli"),
            "system_libraries": libraries,
            "cmake_options": options,
            "source_path_remapping": True,
        }
        (destination / "runtime.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=["arm64", "x86_64"], required=True)
    parser.add_argument("--cache", type=Path, default=ROOT / "native/.cache")
    parser.add_argument("--output", type=Path, default=ROOT / "native/dist/runtime")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    build(args.arch, args.cache.resolve(), args.output.resolve(), args.jobs)


if __name__ == "__main__":
    main()
