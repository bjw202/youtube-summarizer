#!/usr/bin/env python3
"""Check whether this computer can run the skill, and say how to fix what is missing.

    uv run .claude/skills/youtube-visual-summary/scripts/doctor.py [--json]

--json gives, for every required item under "checks":
  ok       true/false
  missing  what is absent (only when ok is false)
  fix      one command that fixes it on THIS operating system, run from the
           project root (null when it needs a person — then see "hint")
"optional" holds speech recognition (STT): install it only if the user agrees.
"features" says which jobs work: summary, text_only, study_view, stt.
Top-level "ok" is true when a normal summary (with images) can run.
Exit code 0 when ok, 1 otherwise.

Modules are probed by running the .venv's own Python, so the answer is right
whichever Python started this script.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CHILD_ENV, PROJECT_ROOT, IS_WINDOWS, find_tool, use_utf8_stdio  # noqa: E402

SKILL_SCRIPTS = ".claude/skills/youtube-visual-summary/scripts"
INSTALL = f"uv run {SKILL_SCRIPTS}/install.py"
UV_INSTALL = ('powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
              if IS_WINDOWS else "curl -LsSf https://astral.sh/uv/install.sh | sh")
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FW_MODEL = "turbo"
# Phase 2 runs install.py (which always upgrades yt-dlp) when doctor is not ok, so an
# old yt-dlp counts as not ok. YouTube changes break yt-dlp releases within weeks.
YT_DLP_MAX_AGE_DAYS = 30

# Runs inside .venv's python; prints one JSON object.
PROBE = r'''
import importlib.util as u, importlib.metadata as m, json, sys, os
def ver(dist):
    try: return m.version(dist)
    except Exception: return None
out = {"python": "%d.%d.%d" % sys.version_info[:3],
       "yt_dlp": ver("yt-dlp"), "yt_dlp_ejs": ver("yt-dlp-ejs"), "curl_cffi": ver("curl_cffi"),
       "pillow": ver("Pillow"), "static_ffmpeg": ver("static-ffmpeg"), "deno": ver("deno"),
       "mlx_whisper": ver("mlx-whisper"), "faster_whisper": ver("faster-whisper"),
       "static_ffmpeg_dir": None, "stt_model": None}
try:
    import static_ffmpeg.run as r
    out["static_ffmpeg_dir"] = r.get_platform_dir()
except Exception:
    pass
engine = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    if engine == "mlx" and out["mlx_whisper"]:
        from huggingface_hub import snapshot_download
        out["stt_model"] = snapshot_download(__MLX__, local_files_only=True)
    elif engine == "faster-whisper" and out["faster_whisper"]:
        from faster_whisper.utils import download_model
        out["stt_model"] = download_model(__FW__, local_files_only=True)
except Exception:
    pass
print(json.dumps(out))
'''.replace("__MLX__", repr(MLX_MODEL)).replace("__FW__", repr(FW_MODEL))


def os_label() -> str:
    name = {"darwin": "macos", "win32": "windows"}.get(sys.platform, sys.platform)
    return f"{name}-{platform.machine().lower()}"


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def is_windows_arm() -> bool:
    return IS_WINDOWS and platform.machine().upper() in ("ARM64", "AARCH64")


def venv_python() -> Path:
    return PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def probe(python: Path, engine: str) -> dict:
    if not python.exists():
        return {}
    try:
        proc = subprocess.run([str(python), "-c", PROBE, engine], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=CHILD_ENV, timeout=120)
        return json.loads(proc.stdout) if proc.returncode == 0 else {}
    except Exception:
        return {}


def impersonation_works(python: Path) -> bool:
    """yt-dlp lists a curl_cffi target only when it accepts the installed curl_cffi
    version (a version outside its pin shows up as "unavailable")."""
    try:
        proc = subprocess.run([str(python), "-m", "yt_dlp", "--list-impersonate-targets"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=CHILD_ENV, timeout=120)
    except Exception:
        return False
    rows = [line for line in proc.stdout.splitlines() if "curl_cffi" in line]
    return any("unavailable" not in line.lower() for line in rows)


def yt_dlp_age_days(version: str | None) -> int | None:
    """Days since the release date in a yt-dlp version ("2026.10.26", nightly
    "2026.10.26.232920"); None when the version has no date."""
    try:
        y, m, d = (int(x) for x in str(version).split(".")[:3])
        return (date.today() - date(y, m, d)).days
    except (TypeError, ValueError):
        return None


def item(ok: bool, missing: str = "", fix: str | None = INSTALL, **info) -> dict:
    out = {"ok": ok, **{k: v for k, v in info.items() if v is not None}}
    if not ok:
        out["missing"] = missing
        out["fix"] = fix
    return out


def tool_item(name: str, p: dict) -> dict:
    path = find_tool(name, fetch=False)
    if not path and p.get("static_ffmpeg_dir"):
        exe = Path(p["static_ffmpeg_dir"]) / (name + (".exe" if IS_WINDOWS else ""))
        path = str(exe) if exe.is_file() else None
    source = None
    if path:
        source = "static-ffmpeg" if "static_ffmpeg" in path else (".venv" if ".venv" in path else "system")
    return item(bool(path), f"{name} executable (install.py fetches a static build when the system has none)",
                path=path, source=source)


def collect() -> dict:
    py = venv_python()
    engine = "mlx" if is_apple_silicon() else "faster-whisper"
    p = probe(py, engine)
    uv = shutil.which("uv")
    checks: dict[str, dict] = {}

    checks["uv"] = item(bool(uv), "uv (the installer this project uses)", fix=UV_INSTALL, path=uv)
    py_ok = bool(p) and tuple(int(x) for x in p["python"].split(".")[:2]) >= (3, 10)
    if not py.exists():
        checks["venv"] = item(False, f".venv with Python 3.10+ ({py} not found)", path=str(py))
    elif not p:
        checks["venv"] = item(False, f".venv Python did not answer ({py}). Run doctor again; if it repeats, "
                                     f"the .venv is broken — rebuild it", fix=f"{INSTALL} --recreate-venv", path=str(py))
    else:
        checks["venv"] = item(py_ok, f".venv Python {p['python']} is older than 3.10",
                              fix=f"{INSTALL} --recreate-venv", path=str(py), python=p["python"])
    age = yt_dlp_age_days(p.get("yt_dlp"))
    if p.get("yt_dlp") and age is not None and age > YT_DLP_MAX_AGE_DAYS:
        checks["yt_dlp"] = item(False, f"a yt-dlp newer than {YT_DLP_MAX_AGE_DAYS} days — {p['yt_dlp']} is {age} days "
                                       f"old and YouTube breaks old versions within weeks (install.py upgrades it)",
                                version=p.get("yt_dlp"), age_days=age)
    else:
        checks["yt_dlp"] = item(bool(p.get("yt_dlp")), "yt-dlp in .venv", version=p.get("yt_dlp"), age_days=age)
    checks["yt_dlp_ejs"] = item(bool(p.get("yt_dlp_ejs")), "yt-dlp-ejs (solves YouTube's JS challenge)",
                                version=p.get("yt_dlp_ejs"))
    checks["impersonation"] = item(impersonation_works(py) if p.get("curl_cffi") else False,
                                   "curl_cffi that yt-dlp can use (browser-style requests, fewer 429 errors)",
                                   version=p.get("curl_cffi"))

    js = None
    for name in ("deno", "node"):
        path = find_tool(name, fetch=False)
        if path:
            js = (name, path)
            break
    if js:
        checks["js_runtime"] = item(True, name=js[0], path=js[1])
    elif is_windows_arm():
        checks["js_runtime"] = item(False, "deno or node — deno has no Windows ARM build", fix=None,
                                    hint="Install Node.js LTS without admin rights: download the Windows ARM64 .zip "
                                         "from https://nodejs.org/en/download, unzip it, add the folder to your user "
                                         "PATH, open a new terminal.")
    else:
        checks["js_runtime"] = item(False, "deno or node (install.py puts deno in .venv)")

    checks["ffmpeg"] = tool_item("ffmpeg", p)
    checks["ffprobe"] = tool_item("ffprobe", p)
    checks["pillow"] = item(bool(p.get("pillow")), "Pillow in .venv", version=p.get("pillow"))

    stt_version = p.get("mlx_whisper") if engine == "mlx" else p.get("faster_whisper")
    stt_ok = bool(stt_version) and bool(p.get("stt_model"))
    stt_missing = (f"{engine} package" if not stt_version else
                   f"{MLX_MODEL if engine == 'mlx' else 'faster-whisper ' + FW_MODEL} model (~1.5 GB)")
    optional = {"stt": item(stt_ok, stt_missing, fix=f"{INSTALL} --with-stt",
                            engine=engine, version=stt_version, model=p.get("stt_model"),
                            note="optional — ask the user first (about 1.5 GB)")}

    needs = {
        "text_only": ["uv", "venv", "yt_dlp", "yt_dlp_ejs", "impersonation", "js_runtime"],
        "summary": ["uv", "venv", "yt_dlp", "yt_dlp_ejs", "impersonation", "js_runtime", "ffmpeg", "ffprobe", "pillow"],
        "study_view": ["uv", "venv", "yt_dlp", "yt_dlp_ejs", "impersonation", "js_runtime", "ffmpeg", "ffprobe", "pillow"],
    }
    features = {}
    for feature, keys in needs.items():
        missing = [k for k in keys if not checks[k]["ok"]]
        features[feature] = {"ok": not missing, "missing": missing}
    stt_missing_keys = [k for k in ("venv", "ffmpeg", "ffprobe") if not checks[k]["ok"]]
    if not optional["stt"]["ok"]:
        stt_missing_keys.append("stt")
    features["stt"] = {"ok": not stt_missing_keys, "missing": stt_missing_keys}

    fixes: list[str] = []
    for c in checks.values():
        if not c["ok"] and c.get("fix") and c["fix"] not in fixes:
            fixes.append(c["fix"])
    return {
        "ok": features["summary"]["ok"],
        "os": os_label(),
        "project_root": str(PROJECT_ROOT),
        "checks": checks,
        "optional": optional,
        "features": features,
        "fixes": fixes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check this computer for the youtube-visual-summary skill.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    data = collect()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"{'OK' if data['ok'] else 'NOT READY'} — {data['os']}")
        for name, c in {**data["checks"], **data["optional"]}.items():
            detail = c.get("path") or c.get("version") or c.get("name") or ""
            print(f"  {'ok ' if c['ok'] else 'NO '} {name:14} {detail if c['ok'] else c['missing']}")
        print("  features: " + ", ".join(f"{k} {'ok' if v['ok'] else 'no'}" for k, v in data["features"].items()))
        for fix in data["fixes"]:
            print(f"  fix: {fix}")
        hint = data["checks"]["js_runtime"].get("hint")
        if hint:
            print(f"  hint: {hint}")
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    use_utf8_stdio()
    raise SystemExit(main())
