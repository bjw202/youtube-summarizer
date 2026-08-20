#!/usr/bin/env python3
"""extract_tab_frames.py — Tab 악보 영상에서 밀집 프레임 추출 + 중복 제거

기타 연습 영상의 스크롤되는 tab 악보를 시간대별로 캡처하여
전체 악보를 재구성할 수 있도록 고유 프레임을 추출한다.

전략:
1. ffmpeg로 높은 FPS(기본 2)로 프레임 추출
2. 픽셀 평균차이(MAD)로 유사 프레임 제거 (일시정지/중복 구간)
3. 타임스탬프가 포함된 매니페스트 생성
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    HarnessError,
    existing_work_dir,
    format_ts,
    require_executable,
    run,
    write_json,
)

COMPARE_SIZE = 64  # 비교용 축소 해상도 (폭)


def find_frame_source(run_dir: Path) -> Path:
    """Run 디렉토리에서 프레임 소스 비디오를 찾는다."""
    internal_dir = existing_work_dir(run_dir)
    candidates = [
        p for p in sorted(internal_dir.glob("frame-source.*"))
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in {".mp4", ".webm", ".mkv"}
    ]
    candidates.extend(
        p for p in sorted(internal_dir.glob("video-preview.*"))
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in {".mp4", ".webm", ".mkv"}
    )
    if not candidates:
        raise HarnessError("missing frame source video; run fetch_frame_source.py RUN_DIR first")
    return candidates[0]


def mean_abs_diff(img_a, img_b) -> float:
    """두 이미지 간 평균 절대 차이(MAD). 0~255 범위."""
    a_data = list(img_a.getdata())
    b_data = list(img_b.getdata())
    n = len(a_data)
    if n == 0:
        return 0.0
    return sum(abs(a - b) for a, b in zip(a_data, b_data)) / n


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tab 악보 영상에서 밀집 프레임 추출 + 중복 제거"
    )
    parser.add_argument("run_dir", help="Run 디렉토리 경로")
    parser.add_argument(
        "--fps", type=float, default=2, help="초당 프레임 수 (기본: 2)"
    )
    parser.add_argument(
        "--mad-threshold",
        type=float,
        default=2.0,
        help="중복 판정 MAD 임계값 (기본: 2.0, 낮을수록 더 엄격)",
    )
    parser.add_argument(
        "--max-width", type=int, default=1280, help="출력 프레임 최대 너비 (기본: 1280)"
    )
    args = parser.parse_args()

    try:
        from PIL import Image
    except ImportError as exc:
        raise HarnessError("Pillow required: pip install Pillow") from exc

    require_executable("ffmpeg")

    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    video = find_frame_source(run_dir)

    # ── Step 1: 밀집 프레임 추출 ──────────────────────────────────────
    raw_dir = internal_dir / "tab-raw-frames"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps={args.fps}",
        "-q:v",
        "2",
        str(raw_dir / "raw_%06d.png"),
    ]
    run(cmd)

    raw_frames = sorted(raw_dir.glob("raw_*.png"))
    if not raw_frames:
        raise HarnessError("프레임 추출 실패 — 비디오 파일을 확인하세요")

    print(f"[tab] 추출됨: {len(raw_frames)} raw 프레임 @ {args.fps} fps")

    # ── Step 2: 픽셀 MAD 기반 중복 제거 ─────────────────────────────
    # 8x8 perceptual hash는 tab의 미세한 스크롤을 놓치므로
    # 64px 폭 그레이스케일 축소 후 평균 절대 차이로 비교한다.
    tab_dir = internal_dir / "tab-frames"
    tab_dir.mkdir(parents=True, exist_ok=True)

    unique: list[dict] = []
    prev_small = None  # 축소 그레이스케일 이미지

    for raw_path in raw_frames:
        img = Image.open(raw_path)

        # 비교용 축소 그레이스케일
        small = img.convert("L").resize(
            (COMPARE_SIZE, max(1, int(COMPARE_SIZE * img.height / img.width)))
        )

        if prev_small is None:
            is_unique = True
        else:
            mad = mean_abs_diff(prev_small, small)
            is_unique = mad > args.mad_threshold

        if is_unique:
            orig_num = int(raw_path.stem.split("_")[1])
            timestamp = orig_num / args.fps

            # 리사이즈 후 저장
            save_img = img
            if save_img.width > args.max_width:
                ratio = args.max_width / save_img.width
                save_img = save_img.resize(
                    (args.max_width, max(1, int(save_img.height * ratio)))
                )

            idx = len(unique)
            filename = f"tab_{idx:04d}.png"
            save_img.save(tab_dir / filename)

            unique.append(
                {
                    "index": idx,
                    "file": filename,
                    "timestamp": round(timestamp, 2),
                    "timecode": format_ts(timestamp),
                    "original_frame": orig_num,
                }
            )
            prev_small = small

        # raw 프레임 정리
        raw_path.unlink()

    # raw 디렉토리 제거 (비어 있으면)
    try:
        raw_dir.rmdir()
    except OSError:
        pass

    # ── Step 3: 매니페스트 생성 ──────────────────────────────────────
    manifest = {
        "mode": "tab",
        "fps": args.fps,
        "mad_threshold": args.mad_threshold,
        "total_unique": len(unique),
        "frames": unique,
    }
    manifest_path = tab_dir / "tab_manifest.json"
    write_json(manifest_path, manifest)

    print(f"[tab] 고유 프레임: {len(unique)} / {len(raw_frames)}")
    print(f"[tab] 매니페스트: {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
