#!/usr/bin/env python3
"""Short readiness check (kept for compatibility; doctor.py is the full version
with per-item fix commands). Same JSON keys as before: ok, missing_required,
has_js_runtime, has_stt, executables, js_runtimes, stt."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import find_executable, find_tool, use_utf8_stdio  # noqa: E402


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
        "executables": {name: (find_tool(name, fetch=False) if name in ("ffmpeg", "ffprobe") else find_executable(name))
                        for name in REQUIRED_EXECUTABLES},
        "required_modules": {name: module_available(name) for name in REQUIRED_MODULES},
        "recommended_modules": {name: module_available(name) for name in RECOMMENDED_MODULES},
        "caption_modules": {name: module_available(name) for name in CAPTION_MODULES},
        "js_runtimes": {name: find_tool(name) for name in JS_RUNTIMES},
        "stt": {"mlx_whisper": module_available("mlx_whisper"), "faster_whisper": module_available("faster_whisper")},
    }

    data["has_js_runtime"] = any(data["js_runtimes"].values())
    missing_required = [
        name for name, path in data["executables"].items() if not path
    ] + [
        name for name, ok in data["required_modules"].items() if not ok
    ]
    # yt-dlp cannot pass YouTube's EJS challenge without a JS runtime, and every
    # visual run needs Pillow (contact sheets, study-view posters).
    if not data["has_js_runtime"]:
        missing_required.append("js-runtime (deno or node)")
    if not data["recommended_modules"]["PIL"]:
        missing_required.append("Pillow")
    data["has_stt"] = any(data["stt"].values())
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
    use_utf8_stdio()
    raise SystemExit(main())
