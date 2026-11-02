#!/usr/bin/env python3
"""Kept for compatibility — install.py does the work now.

Old behaviour is preserved: the same options are accepted, and on Apple Silicon
the mlx-whisper package is installed as before (without pre-downloading the
model). New instructions use:

    uv run .claude/skills/youtube-visual-summary/scripts/install.py [--with-stt]
"""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compatibility wrapper around install.py.")
    parser.add_argument("--venv", default=".venv")
    parser.add_argument("--python", default="3.12")
    parser.add_argument("--no-uv", action="store_true", help="ignored — install.py always uses uv")
    args = parser.parse_args()

    cmd = [sys.executable, str(Path(__file__).resolve().parent / "install.py"),
           "--venv", args.venv, "--python", args.python, "--no-doctor"]
    if sys.platform == "darwin" and platform.machine() == "arm64":
        cmd += ["--with-stt", "--skip-model"]  # setup_venv always added mlx-whisper here
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
