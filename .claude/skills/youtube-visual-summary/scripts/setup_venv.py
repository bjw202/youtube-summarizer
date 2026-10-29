#!/usr/bin/env python3
"""Create or update the project-root Python virtual environment.

Why Python >=3.12 by default:
  yt-dlp (>=2026.x) requires Python >=3.10. On macOS the system ``python3``
  is still 3.9 in many setups; bootstrapping a 3.9 venv silently installs an
  old yt-dlp that cannot solve YouTube's EJS challenge ("The page needs to be
  reloaded"), so every caption/metadata fetch fails. Defaulting to "3.12" and
  letting uv fetch it removes that footgun.

Why yt-dlp[default,curl-cffi]:
  - the ``default`` extra pulls ``yt-dlp-ejs`` (solves the EJS challenge via
    deno) and the standard runtime deps (brotli, requests, ...).
  - the ``curl-cffi`` extra (<0.16) enables browser impersonation, which is
    what lets yt-dlp survive YouTube's 429 bot-detection rate limiting.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path


# yt-dlp[default,curl-cffi] = yt-dlp + yt-dlp-ejs (EJS challenge) + curl_cffi
# (browser impersonation / 429 relief) + brotli/requests/etc.
PACKAGES = ["yt-dlp[default,curl-cffi]", "Pillow", "pydantic", "rich", "PyYAML"]

# mlx-whisper 는 Apple Silicon 전용 로컬 STT — 자막이 없는 영상의 전사 폴백.
# 다른 플랫폼(Linux/Windows/x86)에서는 설치를 건너뛴다(mlx 미지원).
if sys.platform == "darwin" and platform.machine() == "arm64":
    PACKAGES.append("mlx-whisper")

MIN_PYTHON = (3, 10)


def run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update the project-root Python virtual environment.")
    parser.add_argument("--venv", default=".venv", help="virtual environment directory relative to the project root")
    parser.add_argument("--python", default="3.12", help="Python version (e.g. 3.12) or executable path (default: 3.12)")
    parser.add_argument("--no-uv", action="store_true", help="skip uv even if it is installed")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[4]
    venv_dir = (project_root / args.venv).resolve()
    uv = shutil.which("uv")

    if uv and not args.no_uv:
        # uv resolves a bare version like "3.12" to a real interpreter on its own.
        # uv venv refuses an existing dir; skipping it lets reruns reach the --upgrade below
        if not venv_python(venv_dir).exists():
            run([uv, "venv", str(venv_dir), "--python", args.python], cwd=project_root)
        # --upgrade: YouTube breaks old yt-dlp within weeks (2026-09-21: 2026.07.04 could
        # no longer download video data, 2026.8.19 could). Re-running this script is the fix.
        run([uv, "pip", "install", "--upgrade", "--python", str(venv_python(venv_dir)), *PACKAGES], cwd=project_root)
    else:
        # pip fallback: venv is built from the *running* interpreter, so guard its version.
        if sys.version_info < MIN_PYTHON:
            raise SystemExit(
                f"Python {sys.version_info[0]}.{sys.version_info[1]} is too old — yt-dlp requires "
                f">={'.'.join(map(str, MIN_PYTHON))}. Install uv "
                f"(curl -LsSf https://astral.sh/uv/install.sh | sh) so this script can provision "
                f"Python {args.python} automatically, or upgrade your system Python."
            )
        if not venv_python(venv_dir).exists():
            venv.EnvBuilder(with_pip=True).create(venv_dir)
        py = str(venv_python(venv_dir))
        run([py, "-m", "pip", "install", "--upgrade", "pip"], cwd=project_root)
        run([py, "-m", "pip", "install", "--upgrade", *PACKAGES], cwd=project_root)

    print(venv_python(venv_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
