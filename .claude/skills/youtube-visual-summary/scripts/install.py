#!/usr/bin/env python3
"""Install everything this skill needs into the project's .venv — macOS, Windows, Linux.

    uv run .claude/skills/youtube-visual-summary/scripts/install.py [--with-stt]

Safe to run again and again: an existing .venv is kept, packages that are
already there are left alone, and only yt-dlp (+ its YouTube plugin) is always
upgraded, because YouTube breaks old yt-dlp within weeks. Never uses sudo or
administrator rights — everything lands inside the project folder (and uv's
own user-level cache).

What goes into .venv (all through uv):
  yt-dlp[default,curl-cffi]  YouTube metadata/captions/video; EJS plugin + browser impersonation
  Pillow                     contact sheets, study-view posters
  static-ffmpeg              ffmpeg/ffprobe for this OS, downloaded on first use
                             (skipped when the system already has ffmpeg and ffprobe)
  deno (PyPI)                JS runtime for YouTube's EJS challenge — macOS, Linux, Windows x64.
                             Windows ARM has no build: node is used if present, else a hint is printed.
  --with-stt                 Apple Silicon: mlx-whisper · elsewhere: faster-whisper (+ the turbo
                             model, about 1.5 GB, unless --skip-model)

Tools are looked up system-first (common.find_tool), so a machine that already
has ffmpeg or deno keeps using those.

This file runs under whatever Python `uv run` finds first (even 3.8), so it
uses only the standard library and imports nothing from this folder.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS.parents[3]
IS_WINDOWS = sys.platform == "win32"

# yt-dlp[default,curl-cffi] = yt-dlp + yt-dlp-ejs (EJS challenge) + curl_cffi
# (browser impersonation, fewer 429s) + brotli/requests/etc.
BASE_PACKAGES = [
    "yt-dlp[default,curl-cffi]",
    "Pillow",
    "static-ffmpeg",
    "pydantic", "rich", "PyYAML",
    # no Windows-ARM wheel on PyPI (only an sdist that cannot build there)
    'deno; sys_platform != "win32" or platform_machine == "AMD64"',
]
ALWAYS_UPGRADE = ["yt-dlp", "yt-dlp-ejs"]
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FW_MODEL = "turbo"
MIN_PYTHON = (3, 10)

UV_INSTALL = {
    "windows": 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
    "unix": "curl -LsSf https://astral.sh/uv/install.sh | sh",
}


def say(msg: str) -> None:
    print(f"[install] {msg}", flush=True)


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def is_windows_arm() -> bool:
    return IS_WINDOWS and platform.machine().upper() in ("ARM64", "AARCH64")


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if check and proc.returncode != 0:
        say(f"FAILED ({proc.returncode}): {' '.join(cmd)}")
        raise SystemExit(proc.returncode)
    return proc


def py_version(python: Path) -> tuple[int, int] | None:
    try:
        out = subprocess.run([str(python), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=60).stdout.strip()
        major, minor = out.split(".")
        return int(major), int(minor)
    except Exception:
        return None


def venv_eval(python: Path, code: str) -> str | None:
    proc = subprocess.run([str(python), "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=PROJECT_ROOT,
                          env={**os.environ, "PYTHONUTF8": "1"})
    return proc.stdout.strip() if proc.returncode == 0 else None


def system_has(name: str, venv_dir: Path) -> bool:
    """On PATH outside .venv (`uv run` prepends .venv to PATH)."""
    venv_bin = (venv_dir / ("Scripts" if IS_WINDOWS else "bin")).resolve()
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                           if p and Path(p).resolve() != venv_bin)
    return shutil.which(name, path=path) is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Install this skill's dependencies into the project .venv (no admin rights).")
    parser.add_argument("--with-stt", action="store_true",
                        help="also install local speech recognition (mlx-whisper on Apple Silicon, faster-whisper elsewhere)")
    parser.add_argument("--skip-model", action="store_true", help="with --with-stt: do not pre-download the model")
    parser.add_argument("--venv", default=".venv", help="virtual environment directory relative to the project root")
    parser.add_argument("--python", default="3.12", help="Python for a new .venv (uv downloads it if needed)")
    parser.add_argument("--recreate-venv", action="store_true",
                        help="rebuild .venv when its Python is older than 3.10 (yt-dlp needs 3.10+)")
    parser.add_argument("--no-doctor", action="store_true", help="skip the doctor.py summary at the end")
    args = parser.parse_args()

    uv = shutil.which("uv")
    if not uv:
        cmd = UV_INSTALL["windows" if IS_WINDOWS else "unix"]
        say("uv is not installed. Install it (no admin rights needed), open a new terminal, and run this again:")
        say(f"  {cmd}")
        return 2

    venv_dir = (PROJECT_ROOT / args.venv).resolve()
    python = venv_python(venv_dir)

    # 1. .venv — keep an existing one; only a too-old one is rebuilt, and only on request
    version = py_version(python) if python.exists() else None
    if python.exists() and args.recreate_venv and (not version or version < MIN_PYTHON):
        version = (0, 0)  # broken or too old: rebuild below
    if version and version < MIN_PYTHON:
        if not args.recreate_venv:
            say(f"{venv_dir} uses Python {version[0]}.{version[1]}; yt-dlp needs 3.10+. "
                f"Run again with --recreate-venv to rebuild it with Python {args.python}.")
            return 3
        say(f"rebuilding {venv_dir} with Python {args.python}")
        run([uv, "venv", str(venv_dir), "--python", args.python, "--clear"])
    elif not version:
        say(f"creating {venv_dir} (Python {args.python}; uv downloads it if this computer lacks it)")
        run([uv, "venv", str(venv_dir), "--python", args.python])
    else:
        say(f"using existing {venv_dir} (Python {version[0]}.{version[1]})")

    # 2. packages — install what is missing, always refresh yt-dlp
    packages = list(BASE_PACKAGES)
    if args.with_stt:
        packages.append("mlx-whisper" if is_apple_silicon() else "faster-whisper")
    upgrade = [flag for name in ALWAYS_UPGRADE for flag in ("--upgrade-package", name)]
    say("installing packages: " + ", ".join(p.split(";")[0] for p in packages))
    run([uv, "pip", "install", "--python", str(python), *upgrade, *packages])

    # 3. ffmpeg/ffprobe — use the system's if it has both, else fetch the static build once
    if system_has("ffmpeg", venv_dir) and system_has("ffprobe", venv_dir):
        say("ffmpeg/ffprobe: using the system copies")
    else:
        say("ffmpeg/ffprobe: not on the system — using the static build in .venv (downloaded for this OS on the first run only)")
        out = venv_eval(python, "import contextlib, sys, static_ffmpeg.run as r\n"
                                "with contextlib.redirect_stdout(sys.stderr):\n"
                                "    f, p = r.get_or_fetch_platform_executables_else_raise()\n"
                                "print(f)")
        say(f"ffmpeg: {out}" if out else "ffmpeg download FAILED — check the network and run again")

    # 4. JS runtime — deno from PyPI covers macOS/Linux/Windows x64
    if system_has("deno", venv_dir):
        say("JS runtime: using the system deno")
    elif is_windows_arm() and not system_has("node", venv_dir):
        say("JS runtime: no deno build exists for Windows ARM and node is not installed.")
        say("  Install Node.js LTS for your user (no admin): download the Windows ARM64 .zip from")
        say("  https://nodejs.org/en/download , unzip it, add that folder to your user PATH, open a new terminal.")
    elif is_windows_arm():
        say("JS runtime: using the system node (Windows ARM has no deno build)")
    else:
        say("JS runtime: deno inside .venv")

    # 5. speech recognition model (about 1.5 GB) — only with --with-stt
    if args.with_stt and not args.skip_model:
        if is_apple_silicon():
            say(f"STT model: {MLX_MODEL} (downloads once, ~1.5 GB)")
            code = f"from huggingface_hub import snapshot_download; print(snapshot_download({MLX_MODEL!r}))"
        else:
            say(f"STT model: faster-whisper {FW_MODEL} (downloads once, ~1.5 GB)")
            code = f"from faster_whisper.utils import download_model; print(download_model({FW_MODEL!r}))"
        out = venv_eval(python, code)
        say(f"STT model ready: {out}" if out else "STT model download FAILED — check the network and run again")

    if args.no_doctor:
        print(python)
        return 0
    say("checking with doctor.py")
    return run([str(python), str(SCRIPTS / "doctor.py")], check=False).returncode


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # project paths may hold non-ASCII text
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    raise SystemExit(main())
