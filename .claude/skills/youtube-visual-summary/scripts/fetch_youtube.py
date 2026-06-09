#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import require_executable, run, slugify, work_dir, write_json


def find_js_runtime() -> str | None:
    """Return the first available JS runtime (deno preferred over node)."""
    for name in ("deno", "node"):
        if shutil.which(name):
            return name
    return None


def build_yt_dlp_base_args(yt_dlp: str) -> list[str]:
    """Build base yt-dlp args including --remote-components if a JS runtime is present."""
    args = [yt_dlp]
    if find_js_runtime():
        args.append("--remote-components")
        args.append("ejs:github")
    return args


def fetch_metadata(yt_dlp: str, url: str) -> dict:
    """Fetch video metadata via yt-dlp --dump-single-json."""
    base = build_yt_dlp_base_args(yt_dlp)
    proc = run([*base, "--dump-single-json", "--no-warnings", "--skip-download", url])
    return json.loads(proc.stdout)


def download_captions_for_lang(
    yt_dlp: str, url: str, outtmpl: str, lang: str, max_retries: int = 2
) -> bool:
    """Download captions for a single language. Returns True on success."""
    base = build_yt_dlp_base_args(yt_dlp)
    cmd = [
        *base,
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        lang,
        "--sub-format",
        "vtt/srv3/srv2/srv1/ttml/best",
        "-o",
        outtmpl,
        url,
    ]
    for attempt in range(max_retries + 1):
        try:
            run(cmd)
            return True
        except RuntimeError as exc:
            stderr = str(exc)
            if "429" in stderr and attempt < max_retries:
                wait = 3 * (2 ** attempt)  # 3s, 6s
                print(
                    f"[fetch_youtube] 429 rate-limited for lang={lang}, "
                    f"retrying in {wait}s (attempt {attempt + 1}/{max_retries})",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            # Non-429 error or exhausted retries — skip this language
            print(
                f"[fetch_youtube] caption download failed for lang={lang}: {stderr}",
                file=sys.stderr,
            )
            return False
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch YouTube metadata and captions.")
    parser.add_argument("url")
    parser.add_argument("--run-root", default="runs")
    parser.add_argument(
        "--sub-langs",
        default="ko,ko-orig,en",
        help="comma-separated subtitle languages to try in order (default: ko,ko-orig,en)",
    )
    args = parser.parse_args()

    yt_dlp = require_executable("yt-dlp")
    run_root = Path(args.run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    # Determine run directory — support idempotent re-execution
    internal_dir: Path | None = None
    run_dir: Path | None = None

    # Parse requested languages
    requested_langs = [lang.strip() for lang in args.sub_langs.split(",") if lang.strip()]

    # Phase 1: Fetch metadata (idempotent — skip if already present)
    metadata_path = None
    for existing in sorted(run_root.iterdir(), reverse=True):
        candidate = existing / "_work" / "metadata.json"
        if candidate.exists():
            # Check if this run is for the same URL
            input_path = existing / "_work" / "input.json"
            if input_path.exists():
                prev_input = json.loads(input_path.read_text(encoding="utf-8"))
                if prev_input.get("url") == args.url:
                    run_dir = existing
                    internal_dir = work_dir(run_dir)
                    metadata_path = candidate
                    print(
                        f"[fetch_youtube] resuming existing run: {run_dir}",
                        file=sys.stderr,
                    )
                    break

    if run_dir is None:
        meta_proc = fetch_metadata(yt_dlp, args.url)
        slug = slugify(meta_proc.get("title") or meta_proc.get("id") or "video")
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_dir = run_root / f"{stamp}_{slug}"
        run_dir.mkdir(parents=True, exist_ok=True)
        internal_dir = work_dir(run_dir)
        captions_dir = internal_dir / "captions"
        captions_dir.mkdir(parents=True, exist_ok=True)
        write_json(internal_dir / "input.json", {"url": args.url, "sub_langs": args.sub_langs})
        write_json(internal_dir / "metadata.json", meta_proc)
        metadata_path = internal_dir / "metadata.json"

    assert internal_dir is not None
    assert run_dir is not None

    captions_dir = internal_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)

    # Phase 2: Download captions — per-language with individual fallback
    outtmpl = str(captions_dir / "%(id)s.%(ext)s")
    any_success = False

    for lang in requested_langs:
        # Check if captions for this language pattern already exist
        existing_vtt = list(captions_dir.glob(f"*{lang}*.vtt"))
        if existing_vtt:
            print(f"[fetch_youtube] captions for lang={lang} already exist, skipping", file=sys.stderr)
            any_success = True
            continue

        print(f"[fetch_youtube] downloading captions for lang={lang}...", file=sys.stderr)
        success = download_captions_for_lang(yt_dlp, args.url, outtmpl, lang)
        if success:
            any_success = True
            # Downloaded one language successfully — continue trying others but don't fail

    if not any_success:
        # Check if any VTT files exist from previous runs
        all_vtt = list(captions_dir.glob("*.vtt"))
        if not all_vtt:
            print(
                "[fetch_youtube] WARNING: no captions were downloaded. "
                "The workflow will continue in text-only mode if captions are not required.",
                file=sys.stderr,
            )

    print(run_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
