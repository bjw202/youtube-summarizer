#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

from common import HarnessError, existing_work_dir, format_ts, read_json, relpath, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Create contact sheets from extracted frames.")
    parser.add_argument("run_dir")
    parser.add_argument("--thumb-width", type=int, default=480)
    parser.add_argument("--columns", type=int, default=2)
    args = parser.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise HarnessError("Pillow is required for contact sheets: pip install Pillow") from exc

    run_dir = Path(args.run_dir)
    internal_dir = existing_work_dir(run_dir)
    manifest_path = internal_dir / "frames" / "manifest.json"
    if not manifest_path.exists():
        raise HarnessError("missing frames/manifest.json; run extract_frames.py first")
    frames = read_json(manifest_path)["frames"]

    by_chapter: dict[str, list[dict]] = {}
    for frame in frames:
        by_chapter.setdefault(frame["chapter_id"], []).append(frame)

    out_root = internal_dir / "contact-sheets"
    out_root.mkdir(parents=True, exist_ok=True)
    sheets = []
    label_h = 28
    for chapter_id, chapter_frames in by_chapter.items():
        thumbs = []
        for frame in chapter_frames:
            image = Image.open(internal_dir / frame["image_path"]).convert("RGB")
            ratio = args.thumb_width / image.width
            thumb = image.resize((args.thumb_width, max(1, int(image.height * ratio))))
            thumbs.append((frame, thumb))
        if not thumbs:
            continue
        thumb_h = max(t.height for _, t in thumbs)
        cols = max(1, args.columns)
        rows = math.ceil(len(thumbs) / cols)
        sheet = Image.new("RGB", (cols * args.thumb_width, rows * (thumb_h + label_h)), "white")
        draw = ImageDraw.Draw(sheet)
        for idx, (frame, thumb) in enumerate(thumbs):
            x = (idx % cols) * args.thumb_width
            y = (idx // cols) * (thumb_h + label_h)
            sheet.paste(thumb, (x, y))
            label = f"{frame['frame_id']}  {format_ts(frame['timestamp'])}"
            draw.rectangle((x, y + thumb_h, x + args.thumb_width, y + thumb_h + label_h), fill="white")
            draw.text((x + 6, y + thumb_h + 7), label, fill="black")
        out = out_root / f"{chapter_id}-sheet-01.jpg"
        sheet.save(out, quality=92)
        sheet_info = {
            "chapter_id": chapter_id,
            "sheet_path": relpath(out, internal_dir),
            "frames": chapter_frames,
        }
        write_json(out_root / f"{chapter_id}-manifest.json", sheet_info)
        sheets.append(sheet_info)
    write_json(out_root / "manifest.json", {"sheets": sheets})
    print((out_root / "manifest.json").resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
