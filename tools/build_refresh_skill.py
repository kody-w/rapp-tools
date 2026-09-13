#!/usr/bin/env python3
"""Rebuild the portable skill from the reviewed operator and installed converter."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--converter", type=Path, required=True,
                        help="Reviewed installed rapp_skills.py; never run an untrusted converter")
    args = parser.parse_args()
    source = ROOT / "rapp_workspace.py"
    subprocess.run([
        sys.executable, "-B", str(args.converter), "to-skill", str(source),
        "--out", str(ROOT / "skills"),
        "--origin", "https://github.com/kody-w/rapp-tools/blob/workspace-v0.1.0/rapp_workspace.py",
        "--license", "MIT",
    ], check=True)
    spec = importlib.util.spec_from_file_location("reviewed_refresh", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    skill = ROOT / "skills/rapp-workspace-refresh"
    path = skill / "SKILL.md"
    text = path.read_text()
    text = text.replace("## What it needs\n", module.REFRESH_WORKFLOW + "\n## What it needs\n", 1)
    path.write_text(text)
    (skill / "LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
    for command in ("check", "prove"):
        subprocess.run([sys.executable, "-B", str(args.converter), command, str(skill)], check=True)


if __name__ == "__main__":
    main()
