#!/usr/bin/env python3
"""자막 없는 영상 → mlx-whisper 로컬 STT 전사 (Apple Silicon).

build_transcript.py 호환 형식의 _work/transcript.json 을 생성한다. metadata.json 이
이미 있으면(fetch_youtube.py 가 만든 경우) 덮어쓰지 않고 보존한다. 오디오를 CHUNK_SEC
단위 청크로 분할해 전사하며, 청크별 캐시로 재개 가능하다.

사용:
  stt_transcribe.py <audio_path> <run_dir> <url> [--language ko|en|...]
  - language 미지정 시 whisper 자동 감지. 한국어 영상은 --language ko 를 주면
    도메인 용어 initial_prompt 가 주입되어 전사 정확도가 크게 오른다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import mlx_whisper

CHUNK_SEC = 600  # 10분 청크
MODEL = "mlx-community/whisper-large-v3-turbo"

# 한국어 기술 라이브 방송 전용 도메인 용어. language == "ko" 일 때만 주입한다.
# (한국어 whisper 는 initial_prompt 에 도메인 용어를 주면 고유명사 전사 정확도가 크게 오름.
#  다른 언어/도메인에서는 prompt 없이 자동 감지에 맡기는 편이 역효과가 적다.)
KO_TECH_PROMPT = (
    "다음은 한국어로 진행되는 기술 라이브 방송입니다. "
    "오르카(Orca), ADE, IDE, AI 코딩 에이전트, Claude Code, Claude, Codex, "
    "Kimi Code, Kimi, Gemini, Cursor, Cline, 멀티 에이전트, 에이전트, "
    "프롬프트, 터미널, 명령어, API, MCP, 컨텍스트, 토큰, 모델, 바이브랩스, "
    "Vibe Labs, 디버깅, 리팩토링, 코드베이스 등의 용어가 자주 등장합니다."
)


def get_duration(audio: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio),
    ])
    return float(out.strip())


def transcribe_chunk(audio: Path, offset: float, cache_dir: Path, idx: int, language: str | None) -> list[dict]:
    cache_json = cache_dir / f"chunk_{idx:03d}.json"
    if cache_json.exists():
        return json.loads(cache_json.read_text(encoding="utf-8"))

    tmp_wav = cache_dir / f"chunk_{idx:03d}.wav"
    if not tmp_wav.exists():
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(offset), "-t", str(CHUNK_SEC),
            "-i", str(audio), "-ar", "16000", "-ac", "1",
            "-c:a", "pcm_s16le", str(tmp_wav),
        ], check=True, capture_output=True)

    kwargs: dict = {"path_or_hf_repo": MODEL}
    if language:
        kwargs["language"] = language
        if language == "ko":
            kwargs["initial_prompt"] = KO_TECH_PROMPT
    result = mlx_whisper.transcribe(str(tmp_wav), **kwargs)
    segs = [
        {
            "start": round(s["start"] + offset, 2),
            "end": round(s["end"] + offset, 2),
            "text": s["text"].strip(),
        }
        for s in result.get("segments", [])
        if s.get("text", "").strip()
    ]
    cache_json.write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    tmp_wav.unlink(missing_ok=True)  # 디스크 절약
    return segs


def fetch_metadata(url: str) -> dict:
    raw = subprocess.check_output(["yt-dlp", "-J", "--no-download", url], text=True)
    meta = json.loads(raw)
    return {
        "title": meta.get("title"),
        "webpage_url": meta.get("webpage_url") or url,
        "channel": meta.get("channel"),
        "uploader": meta.get("uploader"),
        "duration": meta.get("duration"),
        "upload_date": meta.get("upload_date"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio with mlx-whisper into a build_transcript-compatible transcript.json.")
    parser.add_argument("audio", help="audio file path")
    parser.add_argument("run_dir", help="run directory (writes _work/transcript.json)")
    parser.add_argument("url", help="source YouTube URL (for metadata fallback)")
    parser.add_argument("--language", default=None, help="language code (ko/en/...). Omit for auto-detect.")
    args = parser.parse_args()

    audio = Path(args.audio)
    run_dir = Path(args.run_dir)
    url = args.url

    work = run_dir / "_work"
    cache_dir = work / "stt_chunks"
    work.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(exist_ok=True)

    duration = get_duration(audio)
    n_chunks = int(duration // CHUNK_SEC) + 1
    lang_label = args.language or "auto"
    print(f"[stt] 오디오 {duration:.0f}초 ({duration/60:.1f}분) / 청크 {n_chunks}개 @ {CHUNK_SEC}초 / 언어={lang_label}", flush=True)

    segments: list[dict] = []
    for i in range(n_chunks):
        offset = i * CHUNK_SEC
        n_before = len(segments)
        segs = transcribe_chunk(audio, offset, cache_dir, i, args.language)
        cached = (cache_dir / f"chunk_{i:03d}.json").exists() and not (cache_dir / f"chunk_{i:03d}.wav").exists()
        segments.extend(segs)
        tag = "캐시" if cached else "전사 완료"
        print(f"[stt] [{i+1}/{n_chunks}] {tag} @ {offset}s → +{len(segs)-n_before} segs (누적 {len(segments)})", flush=True)

    transcript = {
        "source": "stt-mlx-whisper",
        "model": MODEL,
        "language": lang_label,
        "video_title": None,
        "segments": segments,
    }
    (work / "transcript.json").write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[stt] transcript.json 저장: {len(segments)} 세그먼트", flush=True)

    # metadata.json 이 이미 있으면(fetch_youtube.py 가 만든 경우) 보존한다.
    metadata_path = work / "metadata.json"
    if metadata_path.exists():
        print("[stt] metadata.json 이미 존재 → 보존", flush=True)
    else:
        try:
            metadata = fetch_metadata(url)
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print("[stt] metadata.json 저장", flush=True)
        except Exception as e:
            print(f"[stt] metadata 수집 실패(무시 가능): {e}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
