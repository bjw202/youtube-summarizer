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


# Child processes (yt-dlp is Python too) talk UTF-8 regardless of the OS locale —
# a Korean Windows console defaults to cp949, which cannot hold every title.
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True,
                          encoding="utf-8", errors="replace", env=CHILD_ENV)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise HarnessError(f"command failed: {' '.join(cmd)}\n{detail}")
    return proc


def use_utf8_stdio() -> None:
    """Print UTF-8 on every OS (Windows pipes default to the locale code page)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


# Every script imports this module, so this one call covers them all: run-folder
# names hold Korean and other non-ASCII text that cp949 (Korean Windows) may not encode.
use_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
IS_WINDOWS = sys.platform == "win32"
BIN_DIR_NAME = "Scripts" if IS_WINDOWS else "bin"
# Found on the system first, then in the project .venv (install.py puts copies there)
SYSTEM_FIRST_TOOLS = ("ffmpeg", "ffprobe", "deno", "node")


def venv_bin_dirs() -> list[Path]:
    """bin/ (Scripts\\ on Windows) of the running venv and of the project .venv."""
    dirs: list[Path] = []
    for prefix in (os.environ.get("VIRTUAL_ENV"), sys.prefix, str(PROJECT_ROOT / ".venv")):
        if not prefix:
            continue
        d = Path(prefix) / BIN_DIR_NAME
        if d.is_dir() and d.resolve() not in [x.resolve() for x in dirs]:
            dirs.append(d)
    return dirs


def system_path() -> str:
    """PATH without the venv bin dirs. `uv run` puts .venv first on PATH; tools
    that the system already has must still win over the copies in .venv."""
    venv = {d.resolve() for d in venv_bin_dirs()}
    keep = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            if Path(entry).resolve() in venv:
                continue
        except OSError:
            pass
        keep.append(entry)
    return os.pathsep.join(keep)


def static_ffmpeg_tool(name: str, fetch: bool = True) -> str | None:
    """ffmpeg/ffprobe from the static-ffmpeg package (installed in .venv by
    install.py). The binaries are downloaded for this OS on first use."""
    try:
        import static_ffmpeg.run as sf
    except ImportError:
        return None
    exe = name + (".exe" if IS_WINDOWS else "")
    cached = Path(sf.get_platform_dir()) / exe
    if cached.is_file():
        return str(cached)
    if not fetch:
        return None
    import contextlib
    with contextlib.redirect_stdout(sys.stderr):  # it prints download progress
        ffmpeg, ffprobe = sf.get_or_fetch_platform_executables_else_raise()
    return ffmpeg if name == "ffmpeg" else ffprobe


def find_tool(name: str, fetch: bool = True) -> str | None:
    """Locate ffmpeg, ffprobe, deno or node: system PATH first, then .venv.
    ffmpeg/ffprobe fall back to static-ffmpeg (downloads once when fetch=True)."""
    found = shutil.which(name, path=system_path())
    if found:
        return found
    for d in venv_bin_dirs():
        found = shutil.which(name, path=str(d))
        if found:
            return found
    if name in ("ffmpeg", "ffprobe"):
        return static_ffmpeg_tool(name, fetch=fetch)
    return None


def require_executable(name: str) -> str:
    found = find_tool(name) if name in SYSTEM_FIRST_TOOLS else find_executable(name)
    if not found:
        raise HarnessError(f"missing executable: {name} — run: uv run "
                           f".claude/skills/youtube-visual-summary/scripts/install.py")
    return found


def find_executable(name: str) -> str | None:
    """Python tools such as yt-dlp: the venv copy first (a system yt-dlp is often
    too old for YouTube), then PATH."""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        found = shutil.which(name, path=str(Path(venv) / BIN_DIR_NAME))
        if found:
            return found
    found = shutil.which(name, path=str(Path(sys.prefix) / BIN_DIR_NAME))
    if found:
        return found
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


def find_js_runtime_path() -> tuple[str, str] | None:
    """(name, path) of the JS runtime yt-dlp should use — deno preferred over node."""
    for name in ("deno", "node"):
        path = find_tool(name)
        if path:
            return name, path
    return None


def find_js_runtime() -> str | None:
    """Return the first available JS runtime name (deno preferred over node)."""
    found = find_js_runtime_path()
    return found[0] if found else None


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


_yt_dlp_help: dict[str, str] = {}


def supports_option(yt_dlp: str, option: str) -> bool:
    """Whether this yt-dlp build accepts ``option`` (its --help is read once)."""
    if yt_dlp not in _yt_dlp_help:
        try:
            _yt_dlp_help[yt_dlp] = run([yt_dlp, "--help"]).stdout
        except Exception:
            _yt_dlp_help[yt_dlp] = ""
    return option in _yt_dlp_help[yt_dlp]


def supports_remote_components(yt_dlp: str) -> bool:
    """Detect once whether this yt-dlp build accepts --remote-components."""
    return supports_option(yt_dlp, "--remote-components")


def build_yt_dlp_base_args(yt_dlp: str) -> list[str]:
    """Build the base yt-dlp args for metadata + caption fetches.

    - ``--remote-components ejs:github``: when a JS runtime (deno/node) is
      present and yt-dlp supports it, let yt-dlp-ejs solve YouTube's EJS
      challenge ("The page needs to be reloaded").
    - ``--impersonate chrome``: when curl_cffi is importable, impersonate a
      browser to avoid YouTube 403/429 bot-detection.
    """
    args = [yt_dlp]
    runtime = find_js_runtime_path()
    if runtime and supports_option(yt_dlp, "--js-runtimes"):
        # name the exact binary: under `uv run`, a deno inside .venv would otherwise
        # shadow the system one, and node is only used when named explicitly
        args += ["--js-runtimes", f"{runtime[0]}:{runtime[1]}"]
    if runtime and supports_remote_components(yt_dlp):
        args.append("--remote-components")
        args.append("ejs:github")
    if has_impersonation():
        args.append("--impersonate")
        args.append("chrome")
    args += ffmpeg_location_args(fetch=False)
    return args


def ffmpeg_location_args(fetch: bool = True) -> list[str]:
    """yt-dlp looks for ffmpeg only on PATH; name the one find_tool chose so a
    static-ffmpeg copy inside .venv is used too (merging, audio extraction)."""
    ffmpeg = find_tool("ffmpeg", fetch=fetch)
    return ["--ffmpeg-location", ffmpeg] if ffmpeg else []


# Player-client attempts for video data, tried in order by fetch_frame_source.
# ``None`` = let yt-dlp pick (its default chain is maintained upstream and is
# the first thing to fix itself after a YouTube change — keep yt-dlp current).
# ``mweb`` = mobile-web client; without a PO token it only exposes the
# combined 360p format 18, but that is enough for frame extraction.
# ``web_embedded,web_safari`` = the 2026-08-14 workaround, kept as a last
# resort; it fails with "Video unavailable" on some uploads (confirmed
# 2026-09-21 on Stanford Online lectures).
VIDEO_CLIENT_FALLBACKS: list[str | None] = [None, "mweb", "web_embedded,web_safari"]


def build_yt_dlp_video_args(yt_dlp: str, player_client: str | None = None) -> list[str]:
    """Build yt-dlp args for downloading *video data* — impersonation only.

    Do NOT pass ``--remote-components`` here. The EJS plugin interferes with
    the SABR-bypassing player clients that yt-dlp falls back to once YouTube
    enables SABR-only streaming (#12482): with the flag on, those clients are
    skipped and the download 403s. Video data is not behind the EJS
    challenge, so impersonation alone is sufficient.

    Do NOT pin a single ``player_client`` (2026-09-21). Which client works
    drifts every few weeks: on 2026-08-14 the default (``android_vr``) 403ed
    and ``web_embedded,web_safari`` worked; by 2026-09-21 yt-dlp 2026.07.04's
    default still 403ed, the pinned pair returned "Video unavailable", and
    yt-dlp 2026.8.19's new default (``visionos``) worked. So the default call
    pins nothing, and callers iterate ``VIDEO_CLIENT_FALLBACKS``. If every
    attempt fails, upgrade yt-dlp first (``install.py`` does this), then
    check ``yt-dlp -v`` to see which client is being selected.
    """
    args = [yt_dlp]
    if has_impersonation():
        args.append("--impersonate")
        args.append("chrome")
    if player_client:
        args.append("--extractor-args")
        args.append(f"youtube:player_client={player_client}")
    args += ffmpeg_location_args(fetch=True)
    return args


def slugify(value: str, max_len: int = 80) -> str:
    value = re.sub(r"[^\w\s.-]+", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "-", value.strip())
    value = value.strip(".-").lower()
    return (value or "video")[:max_len]


def caption_lang(path: Path) -> str | None:
    """Language code of a caption file named ``<video id>.<lang>.vtt``.

    YouTube ids never contain dots, so the code is the last dotted part before
    ``.vtt``: ``ko``, ``ko-orig``, ``en-j3PyPqV-e1s`` (an uploader track).
    Matching on this, not on a substring of the name, keeps an id such as
    ``Xen4koQ`` from passing for an English or Korean file.
    """
    stem, dot, ext = path.name.rpartition(".")
    if not dot or ext.lower() != "vtt" or "." not in stem:
        return None
    return stem.rpartition(".")[2].lower() or None


def caption_base_lang(path: Path) -> str | None:
    """``en`` for ``en``, ``en-orig`` and ``en-j3PyPqV-e1s``."""
    lang = caption_lang(path)
    return lang.split("-", 1)[0] if lang else None


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


VIDEO_SUFFIXES = {".mp4", ".webm", ".mkv"}


def find_frame_source(run_dir: Path) -> Path:
    internal_dir = existing_work_dir(run_dir)
    candidates = [
        p for p in sorted(internal_dir.glob("frame-source.*"))
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in VIDEO_SUFFIXES
    ]
    candidates.extend(
        p for p in sorted(internal_dir.glob("video-preview.*"))
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in VIDEO_SUFFIXES
    )
    if not candidates:
        raise HarnessError("missing frame source video; run fetch_frame_source.py RUN_DIR first "
                           "(add --with-audio for the study view). clean_run.py deletes it after delivery.")
    return candidates[0]


def has_audio_stream(path: Path) -> bool:
    """True if ffprobe sees at least one audio stream in ``path``.

    The default frame source is video-only (``bv*``), so anything cut from it
    plays silently. Study-view clips must be checked with this, not assumed.
    """
    proc = run([require_executable("ffprobe"), "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
    return bool(proc.stdout.strip())


def group_selections(selected: dict) -> dict[str, list[dict]]:
    """Selections per chapter, in file order. A chapter may carry several frames;
    each one is placed at the top, or after bullet ``after_bullet`` (0-based)."""
    grouped: dict[str, list[dict]] = {}
    for item in selected.get("selections", []):
        grouped.setdefault(item["chapter_id"], []).append(item)
    return grouped


def selection_image_name(chapter_id: str, n: int, suffix: str) -> str:
    """File name in images/ of a chapter's n-th selected frame (0-based); the first
    keeps the legacy ``{chapter_id}`` name."""
    name = chapter_id if n == 0 else f"{chapter_id}-{n + 1:02d}"
    return f"{name}{suffix}"


def place_selections(
    chapter_id: str, items: list[dict], internal_dir: Path, run_dir: Path, images_dir: Path
) -> dict[int | None, list[tuple[dict, Path]]]:
    """Copy each selected frame into images/ and bucket it by insertion point
    (None = top of chapter). The first frame keeps the legacy ``{chapter_id}`` name."""
    placed: dict[int | None, list[tuple[dict, Path]]] = {}
    for n, sel in enumerate(items):
        source = first_existing(internal_dir / sel["image_path"], run_dir / sel["image_path"])
        if not source.exists():
            raise HarnessError(f"selected image does not exist: {source}")
        target = images_dir / selection_image_name(chapter_id, n, source.suffix)
        shutil.copy2(source, target)
        placed.setdefault(sel.get("after_bullet"), []).append((sel, target))
    return placed


# ── 출력 페이지 공통 (references/design.md) ──
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
TOOL_URL = "https://github.com/bjw202/youtube-summarizer"


def load_page_template(name: str) -> str:
    """Read assets/<name> with the shared assets/base.css inlined at {{BASE_CSS}},
    so every rendered page stays a single self-contained file."""
    template = ASSETS_DIR / name
    base_css = ASSETS_DIR / "base.css"
    for path in (template, base_css):
        if not path.exists():
            raise HarnessError(f"page asset not found: {path}")
    return template.read_text(encoding="utf-8").replace(
        "{{BASE_CSS}}", base_css.read_text(encoding="utf-8"))
