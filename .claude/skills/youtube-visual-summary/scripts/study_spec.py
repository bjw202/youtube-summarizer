#!/usr/bin/env python3
"""Study-view spec loader shared by cut_clips / render_study / check_study.

The spec lives in ``RUN_DIR/_work/study.json`` (schema: references/study-view.md).
Without one, a single-video spec is derived from the run's own chapters, so any
summarized video can get a study page with no extra authoring.
"""
from __future__ import annotations

from pathlib import Path

from common import HarnessError, existing_work_dir, format_ts, group_selections, read_json

# Clip padding around a scene, seconds. Cutting exactly on the chapter boundary
# clips the first syllable and the last word.
PAD_BEFORE = 0.2
PAD_AFTER = 0.4
# A sub-scene clip is never shorter than this, even when its frame is near the chapter end.
MIN_SUB_CLIP = 8.0


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
        transcript_data = read_json(transcript) if transcript.exists() else {}
        url = src.get("url") or read_json(internal / "input.json")["url"]
        sources[str(src["key"])] = {
            **src,
            "url": url,
            "run_dir": src_run,
            "internal_dir": internal,
            "chapters": {c["id"]: c for c in read_json(internal / "chapters.codex.json")["chapters"]},
            "frames": {f["frame_id"]: f for f in read_json(manifest)["frames"]},
            "segments": transcript_data.get("segments", []),
            # 'auto'/'stt' → the study view warns about transcription errors; older
            # transcripts lack the field and get no label
            "caption_kind": transcript_data.get("caption_kind"),
        }
    spec["_sources"] = sources
    spec.setdefault("groups", [{"id": "_all"}])
    for item in spec["items"]:
        item.setdefault("group", spec["groups"][0]["id"])
    return spec


def derive_from_chapters(run_dir: Path) -> dict:
    """One item per chapter: title → name, key_point → definition, bullets → points.
    The scene frame is the chapter's first selected frame, else its middle candidate.
    Every further selected frame of the chapter becomes a sub-scene ("함께 알아두기")
    whose clip runs from the caption line on screen at that frame to the chapter end."""
    internal = existing_work_dir(run_dir)
    meta = read_json(internal / "metadata.json")
    chapters = read_json(internal / "chapters.codex.json")["chapters"]
    selected_path = internal / "selected-frames.json"
    selected = group_selections(read_json(selected_path)) if selected_path.exists() else {}
    by_chapter: dict[str, list[str]] = {}
    for frame in read_json(internal / "frames" / "manifest.json")["frames"]:
        by_chapter.setdefault(frame["chapter_id"], []).append(frame["frame_id"])
    transcript = internal / "transcript.json"
    starts = sorted(float(s["start"]) for s in read_json(transcript).get("segments", [])) if transcript.exists() else []

    items = []
    for ch in chapters:
        picks = [s for s in selected.get(ch["id"], []) if s.get("frame_id")]
        candidates = by_chapter.get(ch["id"], [])
        frame_id = picks[0]["frame_id"] if picks else (candidates[len(candidates) // 2] if candidates else None)
        if not frame_id:
            continue
        item = {
            "id": ch["id"],
            "name": ch.get("title", ch["id"]),
            "definition": ch.get("key_point", ""),
            "points": ch.get("summary_bullets", []),
            "prompt": (ch.get("prompt") or {}).get("text", ""),
            "scene": {"frame_id": frame_id},
        }
        subs = [sub_from_selection(ch, sel, n, starts) for n, sel in enumerate(picks[1:], 2)]
        if subs:
            item["label"] = "장면 1"   # player tabs; the chapter title is too long for a tab
            item["subs"] = subs
        items.append(item)
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


def sub_from_selection(ch: dict, sel: dict, n: int, segment_starts: list[float]) -> dict:
    """A chapter's n-th selected frame (n ≥ 2) as a study sub-scene.
    name: the selection's caption, else "장면 n (mm:ss)"; definition: the bullet the
    figure sits under in the summary (``after_bullet``), else the selection reason.
    Clip: from the start of the caption line showing at the frame to the chapter end."""
    start, end = float(ch["start"]), float(ch["end"])
    ts = float(sel.get("timestamp", start))
    line_start = max((s for s in segment_starts if s <= ts), default=start)
    clip_start = min(max(start, line_start), ts)
    if end - clip_start < MIN_SUB_CLIP:
        clip_start = max(start, end - MIN_SUB_CLIP)
    bullets = ch.get("summary_bullets", [])
    after = sel.get("after_bullet")
    bullet = bullets[after] if isinstance(after, int) and 0 <= after < len(bullets) else ""
    caption = sel.get("caption", "")
    return {
        "id": sel["frame_id"],
        "name": caption or f"장면 {n} ({format_ts(ts)})",
        "label": f"장면 {n}",
        "definition": bullet or ("" if caption else sel.get("reason", "")),
        "scene": {"frame_id": sel["frame_id"], "start": round(clip_start, 2), "end": end},
    }


def selected_scene_gaps(spec: dict) -> list[str]:
    """Selected frames (selected-frames.json of each source run) that no item or
    sub of the study view shows. Only chapters the study view covers count: a
    hand-written spec may leave whole chapters out on purpose, never half of one.
    A spec with ``"own_scenes": true`` picks its own frames (glossary title cards)
    instead of the summary's, and is not compared."""
    if spec.get("own_scenes"):
        return []
    used = {(str(sc.get("source") or next(iter(spec["_sources"]))), sc["frame_id"]) for _, sc in iter_scenes(spec)}
    covered = set()
    for _, sc in iter_scenes(spec):
        s = resolve_scene(spec, sc)
        covered.add((str(sc.get("source") or next(iter(spec["_sources"]))), s["chapter"]["id"]))
    gaps = []
    for key, src in spec["_sources"].items():
        path = src["internal_dir"] / "selected-frames.json"
        if not path.exists():
            continue
        for sel in read_json(path).get("selections", []):
            fid, cid = sel.get("frame_id"), sel.get("chapter_id")
            if fid and (key, cid) in covered and (key, fid) not in used:
                gaps.append(f"{cid}: selected {fid} is not in the study view")
    return gaps


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
