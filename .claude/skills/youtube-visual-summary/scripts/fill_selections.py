#!/usr/bin/env python3
"""Fill and check RUN_DIR/_work/selected-frames.json from the frame manifest.

Phase 6 writes only what needs judgement — per scene ``frame_id``, ``reason``,
``caption`` and, for a second scene in a chapter, ``after_bullet``. This script
looks every ``frame_id`` up in RUN_DIR/_work/frames/manifest.json and writes
``chapter_id``, ``timestamp`` and ``image_path`` (relative to RUN_DIR/_work/,
exactly as the manifest has it), so nothing is copied by hand.

  uv run python .claude/skills/youtube-visual-summary/scripts/fill_selections.py RUN_DIR

Input (RUN_DIR/_work/selected-frames.json, written by Claude):
  {"selections": [
    {"frame_id": "chapter-05-s001", "caption": "…", "reason": "…"},
    {"frame_id": "chapter-08-f007", "after_bullet": 6, "caption": "…", "reason": "…"}]}

The file is rewritten in place, chapters in chapters.codex.json order (scenes of
one chapter keep their written order). Values already there that disagree with
the manifest are replaced and listed.

FAIL (exit 1, file left unchanged): unknown frame_id, the same frame twice, a
frame whose chapter is not in chapters.codex.json, ``after_bullet`` outside the
chapter's bullets, no ``reason``, a chapter with more scenes than --max-per-chapter.
WARN: no ``caption`` (then ``reason`` is shown under the picture to readers —
references/frame-selection-rubric.md "caption"), a chapter without any scene.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import HarnessError, existing_work_dir, read_json, use_utf8_stdio, write_json

FILLED = ("chapter_id", "timestamp", "image_path")
ORDER = ("chapter_id", "frame_id", "timestamp", "image_path", "after_bullet", "caption", "reason")


def fill(run_dir: Path, max_per_chapter: int) -> tuple[dict, list[str], list[str], list[str]]:
    internal = existing_work_dir(run_dir)
    manifest_path = internal / "frames" / "manifest.json"
    selected_path = internal / "selected-frames.json"
    if not manifest_path.exists():
        raise HarnessError(f"missing {manifest_path} — run extract_frames.py first (SKILL.md Phase 5)")
    if not selected_path.exists():
        raise HarnessError(f"missing {selected_path} — write the chosen frame_ids first (SKILL.md Phase 6)")
    frames = {f["frame_id"]: f for f in read_json(manifest_path).get("frames", [])}
    chapters = read_json(internal / "chapters.codex.json").get("chapters", [])
    order = {c["id"]: i for i, c in enumerate(chapters)}
    bullets = {c["id"]: len(c.get("summary_bullets") or []) for c in chapters}
    selections = read_json(selected_path).get("selections", [])

    fails, warns, changed = [], [], []
    seen: set[str] = set()
    out = []
    for n, sel in enumerate(selections):
        fid = sel.get("frame_id")
        label = fid or f"selection #{n + 1}"
        frame = frames.get(fid)
        if not frame:
            fails.append(f"{label}: not in _work/frames/manifest.json")
            continue
        if fid in seen:
            fails.append(f"{fid}: selected twice")
        seen.add(fid)
        for key in FILLED:
            if key in sel and sel[key] != frame[key]:
                changed.append(f"{fid}: {key} {sel[key]!r} → {frame[key]!r}")
        item = {**sel, **{k: frame[k] for k in FILLED}}
        cid = item["chapter_id"]
        if cid not in order:
            fails.append(f"{fid}: chapter {cid} is not in chapters.codex.json")
            continue
        ab = item.get("after_bullet")
        if ab is not None and not (isinstance(ab, int) and 0 <= ab < bullets[cid]):
            fails.append(f"{fid}: after_bullet {ab} — {cid} has bullets 0~{bullets[cid] - 1}")
        if not str(item.get("reason") or "").strip():
            fails.append(f"{fid}: no reason (why this frame beat the other candidates)")
        if not str(item.get("caption") or "").strip():
            warns.append(f"{fid}: no caption — the reason will be shown under the picture instead")
        out.append((order.get(cid, 0), n, {k: item[k] for k in ORDER if k in item}
                    | {k: v for k, v in item.items() if k not in ORDER}))

    per_chapter: dict[str, int] = {}
    for _, _, item in out:
        per_chapter[item["chapter_id"]] = per_chapter.get(item["chapter_id"], 0) + 1
    for cid, count in per_chapter.items():
        if count > max_per_chapter:
            fails.append(f"{cid}: {count} scenes — more than {max_per_chapter} "
                         f"(frame-selection-rubric.md: second and later scenes)")
    for c in chapters:
        if c["id"] not in per_chapter:
            warns.append(f"{c['id']}: no scene selected")
    data = {"selections": [item for _, _, item in sorted(out, key=lambda x: (x[0], x[1]))]}
    return data, fails, warns, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill chapter_id/timestamp/image_path of selected frames from the manifest.")
    parser.add_argument("run_dir")
    parser.add_argument("--max-per-chapter", type=int, default=6,
                        help="most scenes one chapter may carry (rubric: lectures 3, screen demos 6)")
    parser.add_argument("--check", action="store_true", help="report only, do not rewrite the file")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    data, fails, warns, changed = fill(run_dir, args.max_per_chapter)
    for line in changed:
        print("  fixed " + line)
    for line in fails:
        print("  FAIL " + line)
    for line in warns:
        print("  WARN " + line)
    if fails:
        print(f"FAIL selected-frames.json not rewritten ({len(fails)} problems)")
        return 1
    if not args.check:
        write_json(existing_work_dir(run_dir) / "selected-frames.json", data)
    chapters = len({s["chapter_id"] for s in data["selections"]})
    print(f"OK   {len(data['selections'])} scenes in {chapters} chapters"
          f"{' (checked only)' if args.check else ' — chapter_id, timestamp, image_path filled from the manifest'}")
    return 0


if __name__ == "__main__":
    use_utf8_stdio()
    raise SystemExit(main())
