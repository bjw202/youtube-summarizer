#!/usr/bin/env python3
"""Offline end-to-end test on the fake run in tests/fixtures/run-basic.

No network, no YouTube: copies the fixture to a temp folder and runs
build_transcript → compact_transcript → check_summary → render_markdown →
render_html → render_study, plus check_design, caption-kind labels, the key_point
rule, the SKILL.md field table against the fields the renderers read, sub-scenes in
the study view, and on a made-up video: scene candidates, --at, cut_clips, sub-scene
clips, check_study (incl. selected scenes left out) and clean_run.
Runs the same on macOS, Windows and Linux (CI: .github/workflows/install-and-render.yml).

usage: uv run python tests/run_fixture_tests.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".claude" / "skills" / "youtube-visual-summary" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "run-basic"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
failures: list[str] = []


def step(name: str, args: list[str], expect: int = 0) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, str(SCRIPTS / args[0]), *args[1:]], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=ENV)
    ok = proc.returncode == expect
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(name)
        print(f"      exit {proc.returncode}, expected {expect}")
        print("      " + (proc.stdout + proc.stderr).strip().replace("\n", "\n      ")[-1500:])
    return proc


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(name)
        if detail:
            print(f"      {detail}")


SKILL_MD = SCRIPTS.parent / "SKILL.md"
FIELD_TABLE_HEADING = "#### `chapters.codex.json` 필드"


def documented_chapter_fields() -> set[str]:
    """Field names in the first column of the SKILL.md Phase 4 field table."""
    text = SKILL_MD.read_text(encoding="utf-8")
    if FIELD_TABLE_HEADING not in text:
        return set()
    section = text.split(FIELD_TABLE_HEADING, 1)[1]
    fields: set[str] = set()
    for line in section.splitlines()[1:]:
        if line.startswith("#"):
            break
        if line.startswith("| `"):
            fields.update(re.findall(r"`(\w+)`", line.split("|")[1]))
    return fields


def fields_read_by_renderers(run: Path) -> set[str]:
    """Run render_markdown / render_html / render_study / check_summary in-process on ``run`` and
    record every key they look up in chapters.codex.json (top level and chapters).
    Recording the lookups — not grepping the source — catches any variable name."""
    sys.path.insert(0, str(SCRIPTS))
    import check_summary, render_html, render_markdown, render_study, study_spec

    seen: set[str] = set()

    class Recording(dict):
        def get(self, key, default=None):
            seen.add(key)
            return super().get(key, default)

        def __getitem__(self, key):
            seen.add(key)
            return super().__getitem__(key)

        def __contains__(self, key):
            seen.add(key)
            return super().__contains__(key)

    def recording_reader(original):
        def read(path):
            data = original(path)
            if Path(path).name == "chapters.codex.json":
                data = Recording(data, chapters=[Recording(ch) for ch in data.get("chapters", [])])
            return data
        return read

    modules = (render_markdown, render_html, study_spec, check_summary)
    originals = {m: m.read_json for m in modules}
    argv, stdout = sys.argv, sys.stdout
    try:
        for m in modules:
            m.read_json = recording_reader(originals[m])
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        for module in (render_markdown, render_html, render_study, check_summary):
            sys.argv = [module.__name__, str(run)]
            module.main()
    finally:
        sys.stdout.close()
        sys.argv, sys.stdout = argv, stdout
        for m, original in originals.items():
            m.read_json = original
    return seen - {"chapters"}


DOCS = [SKILL_MD, *sorted((SCRIPTS.parent / "references").glob("*.md"))]
# _work/ paths the docs name that a finished media run does not have (other modes, optional files)
OPTIONAL_WORK_PATHS = {"_work/stt_chunks/", "_work/stt_chunks_faster_whisper/", "_work/audio.mp3",
                       "_work/study.json", "_work/frame-source.log"}
PLACEHOLDERS = {"<chapter_id>": "chapter-01", "<frame_id>": "chapter-01-f001"}


def documented_work_paths() -> set[str]:
    """Every `_work/…` path written in SKILL.md and references/*.md (RUN_DIR/ prefix dropped,
    <chapter_id>/<frame_id> filled in; patterns with other placeholders skipped)."""
    out = set()
    for doc in DOCS:
        for token in re.findall(r"`([^`\s]*_work/[^`\s]*)`", doc.read_text(encoding="utf-8")):
            token = token.split("RUN_DIR/", 1)[-1]
            if not token.startswith("_work/"):
                continue
            for k, v in PLACEHOLDERS.items():
                token = token.replace(k, v)
            if not any(c in token for c in "<>{}*…") and "NN" not in token:
                out.add(token)
    return out


def doc_path_tests() -> None:
    """Docs name the run files where they really are."""
    wrong = []
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        for pattern in (r"(?<![\w/])frames/manifest\.json", r"(?<![\w/])contact-sheets/"):
            for m in re.finditer(pattern, text):
                line = text.count("\n", 0, m.start()) + 1
                wrong.append(f"{doc.name}:{line} {m.group(0)}")
    check("docs write the manifest and contact sheets as _work/frames/manifest.json, _work/contact-sheets/",
          not wrong, "; ".join(wrong))
    code = (SCRIPTS / "extract_frames.py").read_text(encoding="utf-8")
    reasons = set(re.findall(r'"reason": "(\w+)"', code)) | set(re.findall(r'\("(\w+)", (?:dup|shot)\)', code))
    skill = SKILL_MD.read_text(encoding="utf-8")
    check("SKILL.md names every reason extract_frames gives for a dropped scene change",
          len(reasons) >= 5 and all(f"`{r}`" in skill for r in reasons), str(sorted(reasons)))


def documented_paths_exist(run: Path) -> None:
    paths = documented_work_paths()
    missing = sorted(p for p in paths - OPTIONAL_WORK_PATHS if not (run / p).exists())
    check(f"every _work/ path in the docs exists in a finished run ({len(paths)} paths)",
          len(paths) >= 10 and not missing, f"missing: {missing}")


def find_moment_tests(tmp: Path) -> None:
    """find_moment.py: word times from YouTube-style captions, estimates otherwise."""
    run = tmp / "moment run"
    shutil.copytree(FIXTURE, run)
    work = run / "_work"
    step("build_transcript (moment run)", ["build_transcript.py", str(run)])
    proc = step("find_moment without word times estimates inside the segment",
                ["find_moment.py", str(run), "기포가 생기기"])
    m = re.search(r"^(\d\d):(\d\d\.\d)\s+estimate", proc.stdout, re.M)
    t = int(m.group(1)) * 60 + float(m.group(2)) if m else -1
    check("…between the cue's start and end (60~85 s), with an --at line", 60 <= t <= 85 and "--at" in proc.stdout,
          proc.stdout)
    vtt = work / "captions" / "Fixture0en0ko.ko.vtt"
    vtt.write_text("WEBVTT\n\n00:01:00.000 --> 00:01:05.000\n"
                   "센<00:01:00.500><c> 불로</c><00:01:01.200><c> 올리니</c><00:01:02.400><c> 여기</c>"
                   "<00:01:03.100><c> 보시면</c><00:01:03.600><c> 기포가</c>\n\n", encoding="utf-8")
    proc = step("find_moment with word times", ["find_moment.py", str(run), "여기 보시면"])
    check("…gives the first word's time and --at = time + 1 s",
          "01:02.4  word" in proc.stdout and "--at 63.4 --chapter chapter-02" in proc.stdout, proc.stdout)
    step("find_moment reports no match", ["find_moment.py", str(run), "없는 말"], expect=1)


def lead_tests(tmp: Path) -> None:
    """A slide that appears 0.4 s before a chapter starts is a candidate of that chapter,
    found by scene detection; a later evenly spaced frame of the same picture gives way."""
    sys.path.insert(0, str(SCRIPTS))
    from common import require_executable
    ffmpeg = require_executable("ffmpeg")
    run = tmp / "lead run"
    shutil.copytree(FIXTURE, run)
    work = run / "_work"
    video = work / "frame-source.mp4"
    color = lambda c, d: ["-f", "lavfi", "-i", f"color=c={c}:s=320x180:r=10:d={d}"]
    proc = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", *color("blue", 30), *color("red", 1.5),
                           *color("blue", 13.5), *color("white", 15), "-filter_complex",
                           "[0][1][2][3]concat=n=4:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                           "-y", str(video)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("lead video made", proc.returncode == 0, proc.stderr[-300:])
    (work / "frame-source.json").write_text(json.dumps({"source_path": "frame-source.mp4"}), encoding="utf-8")
    base = json.loads((work / "chapters.codex.json").read_text(encoding="utf-8"))["chapters"][0]
    two = [dict(base, id="chapter-01", start=0.0, end=30.4), dict(base, id="chapter-02", start=30.4, end=60.0)]
    (work / "chapters.codex.json").write_text(json.dumps({"summary_level": "normal", "chapters": two},
                                                         ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(work / "frames")
    step("extract_frames (slide 0.4 s before a chapter)", ["extract_frames.py", str(run)])
    manifest = json.loads((work / "frames" / "manifest.json").read_text(encoding="utf-8"))
    frames, info = manifest["frames"], manifest["scene_detection"]
    red = [f for f in frames if f["source"] == "scene" and f["chapter_id"] == "chapter-02" and f["timestamp"] < 31.5]
    check("the change at 30.0 s is a scene candidate of chapter-02 (not dropped as chapter_edge)",
          len(red) == 1 and red[0]["timestamp"] >= 30.4 and not any(r.get("reason") == "chapter_edge" for r in info["rejected"]),
          json.dumps(info["rejected"]) + str([(f["frame_id"], f["timestamp"]) for f in frames]))
    if red:
        from PIL import Image
        with Image.open(work / red[0]["image_path"]) as im:
            rgb = im.convert("RGB").getpixel((im.width // 2, im.height // 2))
        check("…and it shows the red slide", rgb[0] > 150 and rgb[2] < 100, f"rgb={rgb}")
    swapped = {r["interval"]: r["by"] for r in info.get("replaced_interval", [])}
    white = [f for f in frames if f["chapter_id"] == "chapter-02" and f["timestamp"] >= 45]
    check("an evenly spaced frame showing the white picture gives way to the change that brought it in",
          "chapter-02-f002" in swapped and not (work / "frames" / "chapter-02" / "chapter-02-f002.jpg").exists()
          and any(f["source"] == "scene" and 45 <= f["timestamp"] < 46 for f in white), json.dumps(swapped))
    check("…without adding candidates (chapter-02 keeps 3 evenly spaced slots + the red slide)",
          len([f for f in frames if f["chapter_id"] == "chapter-02"]) == 4,
          str([(f["frame_id"], f["timestamp"]) for f in frames if f["chapter_id"] == "chapter-02"]))


def plan_tests(tmp: Path) -> None:
    """plan_chapters.py: boundaries snap to hand-over sentences, split points prefer them,
    greeting chapters merge, --anchor moves a split point, check_summary compares."""
    run = tmp / "plan run"
    shutil.copytree(FIXTURE, run)
    work = run / "_work"
    cues = [(0.0, "안녕하세요. 오늘은 실험입니다."), (21.0, "자, 본론으로 갑니다."), (40.0, "물을 붓습니다."),
            (88.0, "온도가 오릅니다."), (105.0, "다음으로 산에서는 어떨까요."), (149.0, "끓는점이 낮습니다."),
            (160.0, "마지막으로 정리합니다."), (175.0, "감사합니다.")]
    lines = ["WEBVTT", ""]
    for t, text in cues:
        first, *rest = text.split(" ")
        tagged = first + "".join(f"<00:{int(t + 0.3 * (i + 1)) // 60:02d}:{(t + 0.3 * (i + 1)) % 60:06.3f}><c> {w}</c>"
                                 for i, w in enumerate(rest))
        lines += [f"00:{int(t) // 60:02d}:{t % 60:06.3f} --> 00:{int(t + 3) // 60:02d}:{(t + 3) % 60:06.3f}", tagged, ""]
    (work / "captions" / "Fixture0en0ko.ko.vtt").write_text("\n".join(lines), encoding="utf-8")
    meta_path = work / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["duration"] = 180
    meta["chapters"] = [{"start_time": 0, "end_time": 20, "title": "실험 소개"},
                        {"start_time": 20, "end_time": 150, "title": "본론"},
                        {"start_time": 150, "end_time": 170, "title": "광고"},
                        {"start_time": 170, "end_time": 180, "title": "정리"}]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    step("build_transcript (plan run)", ["build_transcript.py", str(run)])
    sys.path.insert(0, str(SCRIPTS))
    import plan_chapters
    saved = dict(plan_chapters.LEVELS["detailed"]), plan_chapters.MIN_PIECE
    plan_chapters.LEVELS["detailed"].update(max_len=100, piece_len=80)   # a 3-minute stand-in for 6 min / 5 min
    plan_chapters.MIN_PIECE = 30
    try:
        got = plan_chapters.plan(run, "detailed", [])
        edges = [(c["start"], c["end"]) for c in got["chapters"]]
        check("plan: boundary 20→21 (자,), split at the hand-over sentence 105 over the nearer plain 88, "
              "the 20 s ad merged, boundary 150→160 (마지막으로)",
              edges == [(0.0, 21.0), (21.0, 105.0), (105.0, 160.0), (160.0, 180.0)]
              and got["sentence_times"] == "word", str(edges))
        anchored = [(c["start"], c["end"]) for c in plan_chapters.plan(run, "detailed", [80.0])["chapters"]]
        check("plan --anchor 80 (25 s from the split at 105) moves it to the sentence start nearest it (88)",
              anchored == [(0.0, 21.0), (21.0, 88.0), (88.0, 160.0), (160.0, 180.0)], str(anchored))
        near = [(c["start"], c["end"]) for c in plan_chapters.plan(run, "detailed", [89.0])["chapters"]]
        check("plan --anchor 89 (16 s from the split) leaves it at 105", near == [(c["start"], c["end"]) for c in got["chapters"]], str(near))
        many = plan_chapters.plan(run, "detailed", [30.0, 72.0, 110.0, 150.0])
        check("plan with several anchors: of those in the window (72, 110) the one nearest the ideal point 90.5 (72) wins; "
              "30 and 150 are outside it",
              [(c["start"], c["end"]) for c in many["chapters"]] == [(0.0, 21.0), (21.0, 88.0), (88.0, 160.0), (160.0, 180.0)]
              and many["chapters"][2]["start_rule"] == "split: anchor 72", str(many["chapters"]))
        check("plan: same input, same chapters", plan_chapters.plan(run, "detailed", [])["chapters"] == got["chapters"])
    finally:
        plan_chapters.LEVELS["detailed"].clear()
        plan_chapters.LEVELS["detailed"].update(saved[0])
        plan_chapters.MIN_PIECE = saved[1]
    proc = step("plan_chapters CLI writes _work/chapter-plan.json", ["plan_chapters.py", str(run), "--level", "normal"])
    check("…with a table", (work / "chapter-plan.json").is_file() and "chapter-01" in proc.stdout, proc.stdout)
    plan = json.loads((work / "chapter-plan.json").read_text(encoding="utf-8"))
    chapters = json.loads((work / "chapters.codex.json").read_text(encoding="utf-8"))
    for ch, pl in zip(chapters["chapters"], plan["chapters"]):
        ch["start"], ch["end"] = pl["start"], pl["end"]
    chapters["chapters"] = [dict(chapters["chapters"][i % 3], id=c["id"], start=c["start"], end=c["end"])
                            for i, c in enumerate(plan["chapters"])]
    (work / "chapters.codex.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
    proc = step("check_summary with chapters equal to the plan", ["check_summary.py", str(run)])
    check("…no plan warning", "chapter-plan" not in proc.stdout, proc.stdout)
    chapters["chapters"][1]["start"] = chapters["chapters"][0]["end"] = chapters["chapters"][1]["start"] + 5
    (work / "chapters.codex.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
    proc = step("check_summary with a boundary 5 s off the plan", ["check_summary.py", str(run)])
    check("…warns and names it", "chapters differ from chapter-plan.json" in proc.stdout and "chapter-02 start" in proc.stdout,
          proc.stdout)


def media_tests(tmp: Path) -> None:
    """Scene candidates, --at, clips and clean_run on a made-up 3-minute video:
    blue; a yellow 'slide' from 53 s — 0.7 s after an evenly spaced candidate that
    still shows blue; a red 'slide' for only 10 s (60~70 s, between two evenly
    spaced candidates); blue again. A 440 Hz tone as audio."""
    sys.path.insert(0, str(SCRIPTS))
    from common import require_executable
    ffmpeg = require_executable("ffmpeg")

    run = tmp / "media run"
    shutil.copytree(FIXTURE, run)
    work = run / "_work"
    video = work / "frame-source.mp4"
    color = lambda c, d: ["-f", "lavfi", "-i", f"color=c={c}:s=320x180:r=10:d={d}"]
    proc = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", *color("blue", 53), *color("yellow", 7),
                           *color("red", 10), *color("blue", 110), "-f", "lavfi", "-i", "sine=frequency=440:duration=180",
                           "-filter_complex", "[0][1][2][3]concat=n=4:v=1:a=0[v]", "-map", "[v]", "-map", "4",
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", str(video)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("synthetic video made", proc.returncode == 0 and video.is_file(), proc.stderr[-300:])
    (work / "frame-source.json").write_text(json.dumps({"source_path": "frame-source.mp4", "has_audio": True}),
                                            encoding="utf-8")
    chapters = json.loads((work / "chapters.codex.json").read_text(encoding="utf-8"))
    one = dict(chapters["chapters"][0], start=0.0, end=180.0)
    (work / "chapters.codex.json").write_text(json.dumps({"summary_level": "normal", "chapters": [one]},
                                                         ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(work / "frames")

    proc = step("extract_frames with scene candidates", ["extract_frames.py", str(run)])
    check("extract_frames prints no DeprecationWarning (Pillow getdata)", "DeprecationWarning" not in proc.stderr,
          proc.stderr[-300:])
    manifest = json.loads((work / "frames" / "manifest.json").read_text(encoding="utf-8"))
    frames = manifest["frames"]
    interval = [f for f in frames if f["source"] == "interval"]
    scene = [f for f in frames if f["source"] == "scene"]
    check("interval candidates miss the red slide", not any(60 <= f["timestamp"] < 70 for f in interval),
          str([f["timestamp"] for f in interval]))
    check("a scene candidate lands on the red slide", any(60 <= f["timestamp"] < 70 for f in scene),
          str([(f["timestamp"], f.get("scene_score")) for f in scene]))
    near = [f for f in interval if 50 <= f["timestamp"] < 53]
    check("an interval candidate sits just before the yellow slide (still blue)", len(near) == 1,
          str([f["timestamp"] for f in interval]))
    check("…the yellow slide 0.7 s later is kept although it is within 3 s (different picture)",
          any(53 <= f["timestamp"] < 60 for f in scene), str([f["timestamp"] for f in scene]))
    check("the return to blue is dropped as a duplicate picture", len(scene) == 2, str([f["timestamp"] for f in scene]))
    rejected = manifest.get("scene_detection", {}).get("rejected", [])
    back = [r for r in rejected if 69 <= r["time"] <= 71]
    check("manifest lists the dropped change with reason, duplicate and distances",
          len(back) == 1 and back[0]["reason"] == "same_picture" and back[0]["duplicate_of"].startswith("chapter-01-f")
          and "hash_distance" in back[0] and "colour_distance" in back[0], str(rejected))
    check("manifest records scene detection time", "seconds" in manifest.get("scene_detection", {}))
    check("no probe image left behind", not list((work / "frames").rglob("*-probe.jpg")))
    step("make_contact_sheets (media run)", ["make_contact_sheets.py", str(run)])
    from PIL import Image
    for lo, hi, colour, test in ((53, 60, "yellow", lambda r, g, b: r > 150 and g > 150 and b < 100),
                                 (60, 70, "red", lambda r, g, b: r > 150 and b < 100)):
        hit = next((f for f in scene if lo <= f["timestamp"] < hi), None)
        if hit:
            with Image.open(work / hit["image_path"]) as im:
                rgb = im.convert("RGB").getpixel((im.width // 2, im.height // 2))
            check(f"…the {colour} candidate shows the {colour} picture", test(*rgb), f"rgb={rgb}")

    step("extract_frames --at adds one manual frame", ["extract_frames.py", str(run), "--at", "1:05"])
    step("extract_frames --no-scenes re-run", ["extract_frames.py", str(run), "--no-scenes"])
    frames = json.loads((work / "frames" / "manifest.json").read_text(encoding="utf-8"))["frames"]
    check("manual frame survives a re-run, scene frames are gone",
          [f["frame_id"] for f in frames if f["source"] == "manual"] == ["chapter-01-m001"]
          and not any(f["source"] == "scene" for f in frames))

    second = next(f for f in frames if f["source"] == "interval" and f["timestamp"] > 100)
    # Phase 6 writes only frame_id + judgement; fill_selections.py fills the rest from the manifest
    selected = work / "selected-frames.json"
    bad = {"selections": [{"frame_id": "chapter-01-x999", "reason": "test"},
                          {"frame_id": second["frame_id"], "after_bullet": 9, "caption": "c", "reason": "test"}]}
    selected.write_text(json.dumps(bad), encoding="utf-8")
    proc = step("fill_selections fails on an unknown frame and a bullet out of range",
                ["fill_selections.py", str(run)], expect=1)
    check("…names both and leaves the file alone",
          "chapter-01-x999" in proc.stdout and "after_bullet 9" in proc.stdout
          and json.loads(selected.read_text(encoding="utf-8")) == bad, proc.stdout)
    sel = {"selections": [{"frame_id": "chapter-01-m001", "timestamp": 1.0, "reason": "test"},
                          {"frame_id": second["frame_id"], "after_bullet": 0, "caption": "둘째 장면", "reason": "test"}]}
    selected.write_text(json.dumps(sel, ensure_ascii=False), encoding="utf-8")
    proc = step("fill_selections fills chapter_id, timestamp, image_path", ["fill_selections.py", str(run)])
    filled = json.loads(selected.read_text(encoding="utf-8"))["selections"]
    by_id = {f["frame_id"]: f for f in frames}
    check("…values equal the manifest (a wrong timestamp is replaced), caption-less scene warned",
          all(s[k] == by_id[s["frame_id"]][k] for s in filled for k in ("chapter_id", "timestamp", "image_path"))
          and "timestamp 1.0" in proc.stdout and "WARN chapter-01-m001: no caption" in proc.stdout,
          proc.stdout + json.dumps(filled))
    step("build_transcript (media run)", ["build_transcript.py", str(run)])
    step("plan_chapters (media run, no uploader chapters)", ["plan_chapters.py", str(run), "--level", "normal"])
    step("render_html (media run)", ["render_html.py", str(run)])
    step("render_study (media run)", ["render_study.py", str(run)])
    step("check_study fails before clips are cut", ["check_study.py", str(run)], expect=1)
    proc = step("clean_run refuses an incomplete run", ["clean_run.py", str(run)], expect=1)
    check("…and keeps the video", video.is_file(), proc.stdout)
    step("cut_clips", ["cut_clips.py", str(run)])
    step("check_study OK with clips", ["check_study.py", str(run)])
    sub_name = f'chapter-01--{second["frame_id"]}'
    check("second selected scene became a sub-scene with its own clip",
          (run / "clips" / f"{sub_name}.mp4").is_file() and "둘째 장면" in (run / "study.html").read_text(encoding="utf-8"))
    sys.path.insert(0, str(SCRIPTS))
    from study_spec import load_study, resolve_scene
    spec = load_study(run)
    sub = resolve_scene(spec, spec["items"][0]["subs"][0]["scene"])
    check("…its clip starts at the caption line on screen, ends at the chapter end",
          sub["start"] <= second["timestamp"] and sub["start"] > 0 and sub["end"] == 180.0, str((sub["start"], sub["end"])))
    study_json = work / "study.json"
    hand = {"title": "t", "sources": [{"key": "1", "run": "."}],
            "items": [{"id": "chapter-01", "name": "하나", "scene": {"frame_id": "chapter-01-m001"}}]}
    study_json.write_text(json.dumps(hand, ensure_ascii=False), encoding="utf-8")
    proc = step("check_study fails when a selected scene is left out", ["check_study.py", str(run)], expect=1)
    check("…and names it", f"selected {second['frame_id']} is not in the study view" in proc.stdout, proc.stdout)
    study_json.write_text(json.dumps({**hand, "own_scenes": True}, ensure_ascii=False), encoding="utf-8")
    step("check_study OK when the spec picks its own scenes (own_scenes)", ["check_study.py", str(run)])
    study_json.unlink()

    # timing.log: one line per mark, --summary gives durations
    step("timing mark start", ["timing.py", str(run), "Phase 5", "start"])
    step("timing mark end", ["timing.py", str(run), "Phase 5", "end"])
    sys.path.insert(0, str(SCRIPTS))
    from timing import mark
    mark(run, "download", "start")
    mark(run, "download", "failed")
    proc = step("timing --summary", ["timing.py", str(run), "--summary"])
    check("…lists the phase, a failed download and a total",
          "Phase 5" in proc.stdout and "(failed)" in proc.stdout and "total" in proc.stdout, proc.stdout)
    step("compact_transcript (media run)", ["compact_transcript.py", str(run)])

    proc = step("clean_run --dry-run", ["clean_run.py", str(run), "--dry-run"])
    check("…deletes nothing", video.is_file() and "would delete" in proc.stdout, proc.stdout)
    proc = step("clean_run deletes the source video", ["clean_run.py", str(run)])
    marker = json.loads((work / "frame-source.json").read_text(encoding="utf-8"))
    check("…video gone, images and clips kept, removal recorded",
          not video.exists() and (run / "images" / "chapter-01.jpg").is_file()
          and (run / "clips" / "chapter-01.mp4").is_file() and "source_removed" in marker, proc.stdout)
    step("clean_run again has nothing to delete", ["clean_run.py", str(run)])
    log = work / "clean_run.log"
    log_text = log.read_text(encoding="utf-8") if log.exists() else ""
    check("clean_run output is kept in _work/clean_run.log (dry run, deletion, size)",
          log_text.count("== ") >= 3 and "would delete" in log_text and "freed" in log_text, log_text[-500:])
    documented_paths_exist(run)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tmp = Path(tempfile.mkdtemp(prefix="yvs-test-"))
    # a Korean folder name with a space: the same shape as real run folders
    run = tmp / "2026-01-01_000000_물-끓는점 실험"
    shutil.copytree(FIXTURE, run)
    work = run / "_work"
    try:
        step("build_transcript", ["build_transcript.py", str(run)])
        transcript = json.loads((work / "transcript.json").read_text(encoding="utf-8"))
        check("transcript picked the Korean file", transcript["caption_file"].endswith(".ko.vtt"))
        step("build_transcript --lang en fails (no English track)", ["build_transcript.py", str(run), "--lang", "en"], expect=1)

        step("compact_transcript", ["compact_transcript.py", str(run)])
        compact = (work / "transcript.compact.txt").read_text(encoding="utf-8")
        check("compact transcript has [mm:ss] lines", compact.startswith("[00:00] "), compact[:80])

        step("check_summary OK", ["check_summary.py", str(run)])

        step("render_markdown", ["render_markdown.py", str(run)])
        md = (run / "summary.md").read_text(encoding="utf-8")
        check("summary.md has every chapter", all(t in md for t in ("실험 준비", "물이 끓는 순간", "산에서는 왜 다를까")))

        step("render_html", ["render_html.py", str(run)])
        html = (run / "summary.html").read_text(encoding="utf-8")
        check("summary.html has base.css inlined", "--fs-base" in html and "{{" not in html)
        check("summary.html image paths use /", 'src="images/chapter-01.jpg"' in html and "\\" not in html.split("<script>")[0].split("</style>")[-1])
        check("summary.html has the prompt card", "따라 해 보기" in html)
        check("images copied", (run / "images" / "chapter-02-02.jpg").is_file())

        step("render_study", ["render_study.py", str(run)])
        study = (run / "study.html").read_text(encoding="utf-8")
        check("study.html rendered without placeholders", "{{" not in study and "산에서는 왜 다를까" in study)
        check("study.html shows chapter-02's second selected frame as a sub-scene",
              'class="also"' in study and "두 번째 테스트 이미지" in study and ">장면 2</button>" in study)
        check("study.html lead sentence comes from key_point", "물은 1기압에서 100도에 끓는다." in study)

        # SKILL.md Phase 4 field table == the fields the renderers actually read
        contract = tmp / "contract"
        shutil.copytree(run, contract)
        documented, read = documented_chapter_fields(), fields_read_by_renderers(contract)
        check("SKILL.md field table lists exactly the chapter fields the renderers and check_summary read",
              documented and documented == read,
              f"read but not documented: {sorted(read - documented)}; documented but not read: {sorted(documented - read)}")

        check("study.html has no auto-caption label when caption_kind is unknown", 'class="caption-note"' not in study)

        # caption_kind: decided from metadata.json, recorded in transcript.json, shown in the study view
        meta_path = work / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for kind, extra in (("auto", {"automatic_captions": {"ko": []}}),
                            ("manual", {"subtitles": {"ko": []}, "automatic_captions": {"ko": []}})):
            meta_path.write_text(json.dumps({**meta, **extra}, ensure_ascii=False), encoding="utf-8")
            step(f"build_transcript ({kind} captions)", ["build_transcript.py", str(run)])
            got = json.loads((work / "transcript.json").read_text(encoding="utf-8")).get("caption_kind")
            check(f"transcript.json caption_kind = {kind}", got == kind, f"got {got!r}")
            step(f"render_study ({kind} captions)", ["render_study.py", str(run)])
            page = (run / "study.html").read_text(encoding="utf-8")
            labelled = "자동 생성 자막 — 받아쓰기 오류가 있을 수 있음" in page
            check(f"study.html label {'shown' if kind == 'auto' else 'hidden'} for {kind} captions",
                  labelled == (kind == "auto"))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        step("check_design", ["check_design.py"])

        # negative cases on a broken copy
        broken = tmp / "broken"
        shutil.copytree(run, broken)
        chapters = json.loads((broken / "_work" / "chapters.codex.json").read_text(encoding="utf-8"))
        chapters["chapters"][1]["start"] = 50.0      # overlaps chapter-01
        chapters["chapters"][2]["end"] = 400.0       # past the 3-minute video
        (broken / "_work" / "chapters.codex.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
        proc = step("check_summary catches overlap and out-of-range", ["check_summary.py", str(broken)], expect=1)
        check("…reports both problems", "overlap" in proc.stdout and "past the video length" in proc.stdout, proc.stdout)

        (broken / "_work" / "selected-frames.json").unlink()   # text-only: images not required
        chapters["chapters"][1]["start"], chapters["chapters"][2]["end"] = 60.0, 180.0
        (broken / "_work" / "chapters.codex.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
        step("check_summary OK for a text-only run", ["check_summary.py", str(broken)])
        step("render_html works for a text-only run", ["render_html.py", str(broken)])
        # key_point is required: FAIL without it, WARN with --allow-missing-key-point
        nokey = tmp / "nokey"
        shutil.copytree(run, nokey)
        chapters = json.loads((nokey / "_work" / "chapters.codex.json").read_text(encoding="utf-8"))
        del chapters["chapters"][2]["key_point"]
        (nokey / "_work" / "chapters.codex.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
        proc = step("check_summary fails on a chapter without key_point", ["check_summary.py", str(nokey)], expect=1)
        check("…and names the chapter", "no key_point" in proc.stdout and "chapter-03" in proc.stdout, proc.stdout)
        proc = step("check_summary --allow-missing-key-point passes with a WARN",
                    ["check_summary.py", str(nokey), "--allow-missing-key-point"])
        check("…as a WARN", "WARN" in proc.stdout and "no key_point" in proc.stdout, proc.stdout)
        # a number read off the screen: WARN until listed in verified_numbers
        screen = tmp / "screen"
        shutil.copytree(run, screen)
        chapters = json.loads((screen / "_work" / "chapters.codex.json").read_text(encoding="utf-8"))
        chapters["chapters"][1]["summary_bullets"].append("화면 그래프에서는 37%가 좋아졌다.")
        (screen / "_work" / "chapters.codex.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
        proc = step("check_summary warns on a number not in the transcript", ["check_summary.py", str(screen)])
        check("…37 is named", "numbers not found in the transcript: 37" in proc.stdout, proc.stdout)
        chapters["chapters"][1]["verified_numbers"] = [{"value": "37", "seen": "01:10 화면 그래프"}]
        (screen / "_work" / "chapters.codex.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
        proc = step("check_summary with verified_numbers", ["check_summary.py", str(screen)])
        check("…no longer warns about 37", "37" not in proc.stdout, proc.stdout)
        import check_summary
        check("check_summary: chapter references are not numbers (17장, 챕터 14) up to the chapter count",
              check_summary.numbers_in("17장에서 다시 본다. 챕터 14 화면. 혈압 140", 18) == {"140"}
              and check_summary.numbers_in("사진 25장", 18) == {"25"}, str(check_summary.numbers_in("17장에서 다시 본다. 챕터 14 화면. 혈압 140", 18)))

        sys.path.insert(0, str(SCRIPTS))
        import doctor
        from datetime import date, timedelta
        old = (date.today() - timedelta(days=45)).strftime("%Y.%m.%d")
        check("doctor: yt-dlp age from its version date", doctor.yt_dlp_age_days(old) == 45
              and doctor.yt_dlp_age_days("2026.10.26.232920") is not None and doctor.yt_dlp_age_days(None) is None)

        doc_path_tests()
        find_moment_tests(tmp)
        plan_tests(tmp)
        lead_tests(tmp)
        media_tests(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
