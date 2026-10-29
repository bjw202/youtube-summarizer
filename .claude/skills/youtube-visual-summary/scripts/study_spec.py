#!/usr/bin/env python3
"""Study-view spec loader shared by cut_clips / render_study / check_study.

The spec lives in ``RUN_DIR/_work/study.json`` (schema: references/study-view.md).
Without one, a single-video spec is derived from the run's own chapters, so any
summarized video can get a study page with no extra authoring.
"""
from __future__ import annotations

from pathlib import Path

from common import HarnessError, existing_work_dir, group_selections, read_json

# Clip padding around a scene, seconds. Cutting exactly on the chapter boundary
# clips the first syllable and the last word.
PAD_BEFORE = 0.2
PAD_AFTER = 0.4


def load_study(run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    path = existing_work_dir(run_dir) / "study.json"
    spec = read_json(path) if path.exists() else derive_from_chapters(run_dir)
    sources = {}
    for src in spec["sources"]:
        src_run = (run_dir / src.get("run", ".")).resolve()
        internal = existing_work_dir(src_run)
        manifest = internal / "frames" / "manifest.json"
        if not manifest.exists():
            raise HarnessError(f"missing frames/manifest.json in {src_run} — run extract_frames.py first")
        transcript = internal / "transcript.json"
        url = src.get("url") or read_json(internal / "input.json")["url"]
        sources[str(src["key"])] = {
            **src,
            "url": url,
            "run_dir": src_run,
            "internal_dir": internal,
            "chapters": {c["id"]: c for c in read_json(internal / "chapters.codex.json")["chapters"]},
            "frames": {f["frame_id"]: f for f in read_json(manifest)["frames"]},
            "segments": read_json(transcript).get("segments", []) if transcript.exists() else [],
        }
    spec["_sources"] = sources
    spec.setdefault("groups", [{"id": "_all"}])
    for item in spec["items"]:
        item.setdefault("group", spec["groups"][0]["id"])
    return spec


def derive_from_chapters(run_dir: Path) -> dict:
    """One item per chapter: title → name, key_point → definition, bullets → points.
    The scene frame is the chapter's first selected frame, else its middle candidate."""
    internal = existing_work_dir(run_dir)
    meta = read_json(internal / "metadata.json")
    chapters = read_json(internal / "chapters.codex.json")["chapters"]
    selected_path = internal / "selected-frames.json"
    selected = group_selections(read_json(selected_path)) if selected_path.exists() else {}
    by_chapter: dict[str, list[str]] = {}
    for frame in read_json(internal / "frames" / "manifest.json")["frames"]:
        by_chapter.setdefault(frame["chapter_id"], []).append(frame["frame_id"])

    items = []
    for ch in chapters:
        picks = [s["frame_id"] for s in selected.get(ch["id"], []) if s.get("frame_id")]
        candidates = by_chapter.get(ch["id"], [])
        frame_id = picks[0] if picks else (candidates[len(candidates) // 2] if candidates else None)
        if not frame_id:
            continue
        items.append({
            "id": ch["id"],
            "name": ch.get("title", ch["id"]),
            "definition": ch.get("key_point", ""),
            "points": ch.get("summary_bullets", []),
            "prompt": (ch.get("prompt") or {}).get("text", ""),
            "scene": {"frame_id": frame_id},
        })
    channel = meta.get("channel") or meta.get("uploader") or ""
    return {
        "title": meta.get("title") or "Study Notes",
        "subtitle": f"{channel} · 챕터 {len(items)}개를 영상 구간과 함께 공부하기",
        "sources": [{
            "key": "1", "run": ".", "title": meta.get("title", ""), "channel": channel,
            "duration": meta.get("duration_string", ""), "url": meta.get("webpage_url", ""),
        }],
        "items": items,
    }


def iter_scenes(spec: dict):
    """(asset name, scene) for every item and sub. Asset names key clips and images."""
    for item in spec["items"]:
        yield item["id"], item["scene"]
        for sub in item.get("subs", []):
            yield f'{item["id"]}--{sub["id"]}', sub["scene"]


def resolve_scene(spec: dict, scene: dict) -> dict:
    """Source, chapter, frame and clip window of a scene ``{source?, frame_id, start?, end?}``.
    The chapter comes from the frame manifest; ``start``/``end`` narrow the clip."""
    sources = spec["_sources"]
    key = str(scene.get("source") or next(iter(sources)))
    src = sources[key]
    frame = src["frames"].get(scene["frame_id"])
    if frame is None:
        raise HarnessError(f"frame not in manifest of source {key}: {scene['frame_id']}")
    chapter = src["chapters"][scene.get("chapter_id") or frame["chapter_id"]]
    start = float(scene.get("start", chapter["start"]))
    end = float(scene.get("end", chapter["end"]))
    clip_start = max(0.0, start - PAD_BEFORE)
    return {
        "source": src, "chapter": chapter, "frame": frame,
        "start": start, "end": end, "clip_start": clip_start, "clip_dur": end + PAD_AFTER - clip_start,
    }
