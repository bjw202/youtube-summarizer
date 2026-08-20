#!/usr/bin/env python3
"""make_tab_contact_sheet.py — Tab 프레임을 읽기 쉬운 컨택트 시트로 정렬

추출된 tab 프레임을 그리드 형태의 컨택트 시트로 만들어
Claude가 시각적으로 tab 악보를 분석할 수 있도록 한다.

프레임이 많을 경우 여러 페이지로 분할한다.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from common import HarnessError, existing_work_dir, read_json, relpath, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Tab 프레임 컨택트 시트 생성")
    parser.add_argument("run_dir", help="Run 디렉토리 경로")
    parser.add_argument(
        "--thumb-width", type=int, default=640, help="썸네일 너비 픽셀 (기본: 640)"
    )
    parser.add_argument(
        "--columns", type=int, default=2, help="열 수 (기본: 2)"
    )
    parser.add_argument(
        "--rows-per-page", type=int, default=3, help="페이지당 행 수 (기본: 3)"
    )
    args = parser.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise HarnessError("Pillow required: pip install Pillow") from exc

    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)

    manifest_path = internal_dir / "tab-frames" / "tab_manifest.json"
    if not manifest_path.exists():
        raise HarnessError(
            "tab_manifest.json 없음; extract_tab_frames.py를 먼저 실행하세요"
        )

    manifest = read_json(manifest_path)
    frames = manifest["frames"]

    if not frames:
        raise HarnessError("추출된 프레임이 없습니다")

    out_dir = internal_dir / "tab-sheets"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 컨택트 시트 생성 ─────────────────────────────────────────────
    label_h = 36
    frames_per_page = args.columns * args.rows_per_page
    total_pages = math.ceil(len(frames) / frames_per_page)
    pages: list[dict] = []

    for page_num in range(total_pages):
        start = page_num * frames_per_page
        page_frames = frames[start : start + frames_per_page]

        # 썸네일 로드 + 리사이즈
        thumbs: list[tuple[dict, Image.Image]] = []
        for frame in page_frames:
            img_path = internal_dir / "tab-frames" / frame["file"]
            img = Image.open(img_path).convert("RGB")
            ratio = args.thumb_width / img.width
            thumb = img.resize((args.thumb_width, max(1, int(img.height * ratio))))
            thumbs.append((frame, thumb))

        if not thumbs:
            continue

        thumb_h = max(t.height for _, t in thumbs)
        cols = args.columns
        rows = math.ceil(len(thumbs) / cols)

        sheet_w = cols * args.thumb_width
        sheet_h = rows * (thumb_h + label_h)

        sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
        draw = ImageDraw.Draw(sheet)

        for idx, (frame, thumb) in enumerate(thumbs):
            x = (idx % cols) * args.thumb_width
            y = (idx // cols) * (thumb_h + label_h)

            # 썸네일 붙이기
            sheet.paste(thumb, (x, y))

            # 타임스탬프 레이블
            label = f"#{frame['index']+1}  {frame['timecode']}  ({frame['timestamp']}s)"
            draw.rectangle(
                (x, y + thumb_h, x + args.thumb_width, y + thumb_h + label_h),
                fill="#f5f5f5",
            )
            draw.text((x + 8, y + thumb_h + 9), label, fill="#333333")

        out_path = out_dir / f"tab-sheet-{page_num + 1:02d}.jpg"
        sheet.save(out_path, quality=92)

        pages.append(
            {
                "page": page_num + 1,
                "path": relpath(out_path, internal_dir),
                "frame_indices": [f["index"] for f in page_frames],
                "time_range": f"{page_frames[0]['timecode']} - {page_frames[-1]['timecode']}",
            }
        )

    # 매니페스트 저장
    sheets_manifest = {"total_pages": total_pages, "pages": pages}
    write_json(out_dir / "tab-sheets-manifest.json", sheets_manifest)

    print(f"[tab] 컨택트 시트: {total_pages}페이지, 총 {len(frames)}프레임")
    print(f"[tab] 출력: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
