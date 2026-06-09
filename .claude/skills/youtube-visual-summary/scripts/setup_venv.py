#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path


PACKAGES = ["yt-dlp", "Pillow", "pydantic", "rich", "PyYAML"]


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
    parser.add_argument("--python", default=sys.executable, help="Python executable to use when creating the venv")
    parser.add_argument("--no-uv", action="store_true", help="skip uv even if it is installed")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[4]
    venv_dir = (project_root / args.venv).resolve()
    uv = shutil.which("uv")

    if uv and not args.no_uv:
        run([uv, "venv", str(venv_dir), "--python", args.python], cwd=project_root)
        run([uv, "pip", "install", "--python", str(venv_python(venv_dir)), *PACKAGES], cwd=project_root)
    else:
        if not venv_python(venv_dir).exists():
            venv.EnvBuilder(with_pip=True).create(venv_dir)
        py = str(venv_python(venv_dir))
        run([py, "-m", "pip", "install", "--upgrade", "pip"], cwd=project_root)
        run([py, "-m", "pip", "install", *PACKAGES], cwd=project_root)

    print(venv_python(venv_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
