#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_executable  # noqa: E402


REQUIRED_EXECUTABLES = ["yt-dlp", "ffmpeg", "ffprobe"]
REQUIRED_MODULES = []
RECOMMENDED_MODULES = ["PIL", "pydantic", "rich"]
CAPTION_MODULES = ["webvtt"]
JS_RUNTIMES = ["deno", "node"]


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable status")
    args = parser.parse_args()

    data = {
        "executables": {name: find_executable(name) for name in REQUIRED_EXECUTABLES},
        "required_modules": {name: module_available(name) for name in REQUIRED_MODULES},
        "recommended_modules": {name: module_available(name) for name in RECOMMENDED_MODULES},
        "caption_modules": {name: module_available(name) for name in CAPTION_MODULES},
        "js_runtimes": {name: shutil.which(name) for name in JS_RUNTIMES},
        "stt": {"mlx_whisper": module_available("mlx_whisper")},
    }

    missing_required = [
        name for name, path in data["executables"].items() if not path
    ] + [
        name for name, ok in data["required_modules"].items() if not ok
    ]
    data["has_js_runtime"] = any(data["js_runtimes"].values())
    data["has_stt"] = data["stt"]["mlx_whisper"]
    data["ok"] = not missing_required
    data["missing_required"] = missing_required

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for name, path in data["executables"].items():
            print(f"{name}: {path or 'missing'}")
        js_found = [name for name, path in data["js_runtimes"].items() if path]
        print(f"js_runtime: {', '.join(js_found) if js_found else 'none (install deno for yt-dlp EJS support)'}")
        if missing_required:
            print("missing required:", ", ".join(missing_required))
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
