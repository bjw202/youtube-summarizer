#!/usr/bin/env python3
"""자막 없는 영상 → 로컬 STT 전사.

엔진은 자동으로 고른다 (--engine 으로 고정 가능):
  - mlx            Apple Silicon 맥: mlx-whisper, mlx-community/whisper-large-v3-turbo
  - faster-whisper 그 밖의 컴퓨터(윈도우·리눅스·인텔 맥): faster-whisper turbo, int8, beam 1
                   (이 하네스를 만든 맥에서 같은 영상으로 재 보니 mlx turbo와 정확도가 거의 같았다)
둘 다 `install.py --with-stt` 가 설치한다.

build_transcript.py 호환 형식의 _work/transcript.json 을 생성한다. metadata.json 이
이미 있으면(fetch_youtube.py 가 만든 경우) 덮어쓰지 않고 보존한다. 오디오를 CHUNK_SEC
단위 청크로 분할해 전사하며, 청크별 캐시로 재개 가능하다 (엔진마다 캐시 폴더가 다르다).

사용:
  stt_transcribe.py <audio_path> <run_dir> <url> [--language ko|en|...] [--engine auto|mlx|faster-whisper]
  - language 미지정 시 whisper 자동 감지. 한국어 영상은 --language ko 를 주면
    도메인 용어 initial_prompt 가 주입되어 전사 정확도가 크게 오른다.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path

from common import CHILD_ENV, require_executable, use_utf8_stdio

CHUNK_SEC = 600  # 10분 청크
MODEL = "mlx-community/whisper-large-v3-turbo"  # mlx 엔진
FW_MODEL = "turbo"  # faster-whisper 엔진 (= mobiuslabsgmbh/faster-whisper-large-v3-turbo)
FW_COMPUTE_TYPE = "int8"
FW_BEAM_SIZE = 1

# 한국어 영상용 용어 프롬프트. language == "ko" 일 때만 주입한다.
# (한국어 whisper 는 initial_prompt 에 도메인 용어를 주면 고유명사 전사 정확도가 크게 오름.
#  다른 언어/도메인에서는 prompt 없이 자동 감지에 맡기는 편이 역효과가 적다.)
# 자주 보는 채널·방송의 고유명사는 스킬 폴더의 stt-prompt.local.txt 에 적어 두면 이 기본값 대신 쓴다
# (git 추적 제외 — 개인 용어집).
KO_PROMPT_DEFAULT = (
    "다음은 한국어로 진행되는 기술 영상입니다. "
    "AI, API, MCP, Claude, Claude Code, Codex, Gemini, Cursor, "
    "AI 코딩 에이전트, 에이전트, 프롬프트, 터미널, 명령어, 컨텍스트, 토큰, 모델, "
    "디버깅, 리팩토링, 코드베이스 등의 용어가 자주 등장합니다."
)
KO_PROMPT_FILE = Path(__file__).resolve().parent.parent / "stt-prompt.local.txt"

ENGINES = {
    # name: (python module, transcript "source", cache folder under _work/)
    "mlx": ("mlx_whisper", "stt-mlx-whisper", "stt_chunks"),
    "faster-whisper": ("faster_whisper", "stt-faster-whisper", "stt_chunks_faster_whisper"),
}


def ko_prompt() -> str:
    if KO_PROMPT_FILE.exists():
        text = KO_PROMPT_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    return KO_PROMPT_DEFAULT


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def available_engines() -> list[str]:
    """Usable engines in preference order (mlx only on Apple Silicon)."""
    found = []
    if is_apple_silicon() and importlib.util.find_spec("mlx_whisper"):
        found.append("mlx")
    if importlib.util.find_spec("faster_whisper"):
        found.append("faster-whisper")
    return found


def pick_engine(requested: str) -> str:
    engines = available_engines()
    if requested != "auto":
        if requested not in engines:
            raise SystemExit(f"[stt] engine '{requested}' is not installed here (available: {engines or 'none'}). "
                             f"Run: uv run .claude/skills/youtube-visual-summary/scripts/install.py --with-stt")
        return requested
    if not engines:
        raise SystemExit("[stt] no speech-recognition engine installed. "
                         "Run: uv run .claude/skills/youtube-visual-summary/scripts/install.py --with-stt")
    return engines[0]


def get_duration(audio: Path) -> float:
    out = subprocess.check_output([
        require_executable("ffprobe"), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio),
    ])
    return float(out.strip())


def chunk_options(language: str | None) -> dict:
    kwargs: dict = {}
    if language:
        kwargs["language"] = language
        if language == "ko":
            kwargs["initial_prompt"] = ko_prompt()
    return kwargs


def run_mlx(audio: Path, offset: float, cache_dir: Path, idx: int, language: str | None) -> list[dict]:
    import mlx_whisper

    tmp_wav = cache_dir / f"chunk_{idx:03d}.wav"
    if not tmp_wav.exists():
        subprocess.run([
            require_executable("ffmpeg"), "-y", "-ss", str(offset), "-t", str(CHUNK_SEC),
            "-i", str(audio), "-ar", "16000", "-ac", "1",
            "-c:a", "pcm_s16le", str(tmp_wav),
        ], check=True, capture_output=True)
    result = mlx_whisper.transcribe(str(tmp_wav), path_or_hf_repo=MODEL, **chunk_options(language))
    tmp_wav.unlink(missing_ok=True)  # 디스크 절약
    return [
        {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
        for s in result.get("segments", [])
    ]


_fw_model = None


def run_faster_whisper(audio: Path, offset: float, cache_dir: Path, idx: int, language: str | None) -> list[dict]:
    """faster-whisper 1.2.1 + PyAV 19 raises TypeError on a file-path input, so
    ffmpeg decodes the chunk to a 16 kHz mono float32 array and that is passed in."""
    global _fw_model
    import numpy as np
    from faster_whisper import WhisperModel

    raw = subprocess.run([
        require_executable("ffmpeg"), "-nostdin", "-v", "error", "-ss", str(offset), "-t", str(CHUNK_SEC),
        "-i", str(audio), "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", "16000", "-",
    ], check=True, capture_output=True, env=CHILD_ENV).stdout
    samples = np.frombuffer(raw, dtype=np.float32)
    if samples.size == 0:
        return []
    if _fw_model is None:
        _fw_model = WhisperModel(FW_MODEL, device="auto", compute_type=FW_COMPUTE_TYPE)
    segments, _info = _fw_model.transcribe(samples, beam_size=FW_BEAM_SIZE, **chunk_options(language))
    return [{"start": float(s.start), "end": float(s.end), "text": s.text} for s in segments]


RUNNERS = {"mlx": run_mlx, "faster-whisper": run_faster_whisper}


def transcribe_chunk(engine: str, audio: Path, offset: float, cache_dir: Path, idx: int,
                     language: str | None) -> list[dict]:
    cache_json = cache_dir / f"chunk_{idx:03d}.json"
    if cache_json.exists():
        return json.loads(cache_json.read_text(encoding="utf-8"))
    raw = RUNNERS[engine](audio, offset, cache_dir, idx, language)
    segs = [
        {
            "start": round(s["start"] + offset, 2),
            "end": round(s["end"] + offset, 2),
            "text": s["text"].strip(),
        }
        for s in raw
        if s.get("text", "").strip()
    ]
    cache_json.write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    return segs


def fetch_metadata(url: str) -> dict:
    raw = subprocess.check_output([require_executable("yt-dlp"), "-J", "--no-download", url],
                                  text=True, encoding="utf-8", errors="replace", env=CHILD_ENV)
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
    parser = argparse.ArgumentParser(description="Transcribe audio locally into a build_transcript-compatible transcript.json.")
    parser.add_argument("audio", help="audio file path")
    parser.add_argument("run_dir", help="run directory (writes _work/transcript.json)")
    parser.add_argument("url", help="source YouTube URL (for metadata fallback)")
    parser.add_argument("--language", default=None, help="language code (ko/en/...). Omit for auto-detect.")
    parser.add_argument("--engine", default="auto", choices=["auto", *ENGINES],
                        help="auto = mlx on Apple Silicon, faster-whisper elsewhere")
    args = parser.parse_args()

    engine = pick_engine(args.engine)
    _module, source, cache_name = ENGINES[engine]
    audio = Path(args.audio)
    run_dir = Path(args.run_dir)
    url = args.url

    work = run_dir / "_work"
    cache_dir = work / cache_name
    work.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(exist_ok=True)

    duration = get_duration(audio)
    n_chunks = int(duration // CHUNK_SEC) + 1
    lang_label = args.language or "auto"
    print(f"[stt] 엔진={engine} / 오디오 {duration:.0f}초 ({duration/60:.1f}분) / 청크 {n_chunks}개 @ {CHUNK_SEC}초 / 언어={lang_label}", flush=True)

    segments: list[dict] = []
    for i in range(n_chunks):
        offset = i * CHUNK_SEC
        # 전사 전에 확인해야 한다 — 전사가 끝나면 캐시 파일이 생기므로 나중에 보면 늘 "캐시"로 보인다
        cached = (cache_dir / f"chunk_{i:03d}.json").exists()
        segs = transcribe_chunk(engine, audio, offset, cache_dir, i, args.language)
        segments.extend(segs)
        tag = "캐시" if cached else "전사 완료"
        print(f"[stt] [{i+1}/{n_chunks}] {tag} @ {offset}s → +{len(segs)} segs (누적 {len(segments)})", flush=True)

    transcript = {
        "source": source,
        "model": MODEL if engine == "mlx" else f"faster-whisper:{FW_MODEL} ({FW_COMPUTE_TYPE}, beam {FW_BEAM_SIZE})",
        "language": lang_label,
        "caption_kind": "stt",  # machine transcription — the study view labels it
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
    use_utf8_stdio()
    raise SystemExit(main())
