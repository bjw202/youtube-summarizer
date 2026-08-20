#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import site
from pathlib import Path
from typing import Any


class HarnessError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise HarnessError(f"command failed: {' '.join(cmd)}\n{detail}")
    return proc


def require_executable(name: str) -> str:
    found = find_executable(name)
    if not found:
        raise HarnessError(f"missing executable: {name}")
    return found


def find_executable(name: str) -> str | None:
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        venv_candidate = Path(venv) / ("Scripts" if sys.platform == "win32" else "bin") / name
        if venv_candidate.exists() and os.access(venv_candidate, os.X_OK):
            return str(venv_candidate)
    sys_prefix_candidate = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin") / name
    if sys_prefix_candidate.exists() and os.access(sys_prefix_candidate, os.X_OK):
        return str(sys_prefix_candidate)
    found = shutil.which(name)
    if found:
        return found
    candidates = []
    try:
        candidates.append(Path(site.getuserbase()) / "bin" / name)
    except Exception:
        pass
    candidates.append(Path.home() / "Library" / "Python" / f"{sys.version_info.major}.{sys.version_info.minor}" / "bin" / name)
    candidates.append(Path.home() / ".local" / "bin" / name)
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def find_js_runtime() -> str | None:
    """Return the first available JS runtime (deno preferred over node)."""
    for name in ("deno", "node"):
        if shutil.which(name):
            return name
    return None


def has_impersonation() -> bool:
    """True if curl_cffi is importable in this interpreter.

    curl_cffi (installed via the yt-dlp[curl-cffi] extra) is what lets yt-dlp
    impersonate a real browser. Without it YouTube's bot detection returns
    HTTP 403/429 and downloads fail.
    """
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        return False
    return True


_remote_components_supported: bool | None = None


def supports_remote_components(yt_dlp: str) -> bool:
    """Detect once whether this yt-dlp build accepts --remote-components."""
    global _remote_components_supported
    if _remote_components_supported is None:
        try:
            proc = run([yt_dlp, "--help"])
            _remote_components_supported = "--remote-components" in proc.stdout
        except Exception:
            _remote_components_supported = False
    return _remote_components_supported


def build_yt_dlp_base_args(yt_dlp: str) -> list[str]:
    """Build the base yt-dlp args for metadata + caption fetches.

    - ``--remote-components ejs:github``: when a JS runtime (deno/node) is
      present and yt-dlp supports it, let yt-dlp-ejs solve YouTube's EJS
      challenge ("The page needs to be reloaded").
    - ``--impersonate chrome``: when curl_cffi is importable, impersonate a
      browser to avoid YouTube 403/429 bot-detection.
    """
    args = [yt_dlp]
    if find_js_runtime() and supports_remote_components(yt_dlp):
        args.append("--remote-components")
        args.append("ejs:github")
    if has_impersonation():
        args.append("--impersonate")
        args.append("chrome")
    return args


def build_yt_dlp_video_args(yt_dlp: str) -> list[str]:
    """Build yt-dlp args for downloading *video data* — impersonation only.

    Do NOT pass ``--remote-components`` here. The EJS plugin interferes with
    the SABR-bypassing player clients (e.g. android_vr) that yt-dlp falls
    back to once YouTube enables SABR-only streaming (#12482): with the flag
    on, those clients are skipped and the download 403s. Video data is not
    behind the EJS challenge, so impersonation alone is sufficient.

    Force ``player_client=web_embedded,web_safari`` explicitly (2026-08-14).
    Without it, yt-dlp's own client-selection logic currently falls back to
    ``android_vr`` for video-only formats, and YouTube started returning
    HTTP 403 for that specific client's stream URLs (confirmed by hand:
    identical request succeeds on ``web_embedded``/``web_safari``, fails on
    the default-selected client). This is not an EJS/impersonation problem —
    both clients here are unaffected by the EJS-vs-SABR conflict above, and
    still work with impersonation only. yt-dlp's default fallback chain is
    outside our control and can drift again; if 403s return, re-check which
    client is actually being selected (yt-dlp -v) before assuming this list
    is still valid.
    """
    args = [yt_dlp]
    if has_impersonation():
        args.append("--impersonate")
        args.append("chrome")
    args.append("--extractor-args")
    args.append("youtube:player_client=web_embedded,web_safari")
    return args


def slugify(value: str, max_len: int = 80) -> str:
    value = re.sub(r"[^\w\s.-]+", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "-", value.strip())
    value = value.strip(".-").lower()
    return (value or "video")[:max_len]


def format_ts(seconds: float) -> str:
    seconds = max(0, float(seconds))
    whole = int(seconds)
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_ts(value: str) -> float:
    value = value.replace(",", ".").strip()
    parts = value.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        raise ValueError(f"invalid timestamp: {value}")
    return int(h) * 3600 + int(m) * 60 + float(s)


def relpath(path: Path, start: Path) -> str:
    return path.resolve().relative_to(start.resolve()).as_posix()


def work_dir(run_dir: Path) -> Path:
    return run_dir / "_work"


def existing_work_dir(run_dir: Path) -> Path:
    candidate = work_dir(run_dir)
    if candidate.exists():
        return candidate
    return run_dir


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]
