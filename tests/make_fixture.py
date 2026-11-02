#!/usr/bin/env python3
"""Rebuild tests/fixtures/run-basic — a tiny fake run with no real video material.

Everything here is made up for the tests: a 3-minute "talk" about boiling
water, hand-written Korean captions, three chapters, and solid-colour frames.
Nothing is downloaded, so CI never needs YouTube (which blocks GitHub runners).

usage: uv run python tests/make_fixture.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent / "fixtures" / "run-basic"
WORK = ROOT / "_work"
VIDEO_ID = "Fixture0en0ko"  # contains "en" and "ko" on purpose (caption-language matching)

CUES = [
    (0.0, 8.0, "안녕하세요. 오늘은 물이 끓는 온도를 직접 재 보겠습니다."),
    (8.0, 30.0, "냄비에 물 1.5리터를 붓고 온도계를 꽂았습니다."),
    (30.0, 60.0, "처음 온도는 20도였습니다."),
    (60.0, 85.0, "센 불로 올리니 5분쯤 지나 기포가 생기기 시작했습니다."),
    (85.0, 120.0, "1기압에서는 물이 100도에서 끓습니다."),
    (120.0, 150.0, "높은 산에서는 기압이 낮아서 더 낮은 온도에서 끓습니다."),
    (150.0, 180.0, "그래서 산 위에서 라면이 잘 안 익는 겁니다. 오늘 실험은 여기까지입니다."),
]

CHAPTERS = {
    "summary_level": "normal",
    "chapters": [
        {
            "id": "chapter-01", "title": "실험 준비", "start": 0.0, "end": 60.0,
            "summary_bullets": ["냄비에 물 **1.5리터**를 붓고 온도계를 꽂는다.", "처음 물 온도는 20도."],
            "key_point": "끓는점을 직접 재 보는 실험이다.",
            "visual_query": "냄비와 온도계",
        },
        {
            "id": "chapter-02", "title": "물이 끓는 순간", "start": 60.0, "end": 120.0,
            "summary_bullets": ["센 불에서 5분쯤 지나 기포가 생긴다.", "1기압에서 물은 100도에서 끓는다."],
            "key_point": "물은 1기압에서 100도에 끓는다.",
            "summary_paragraphs": ["불을 올린 뒤 온도가 오르다 기포가 생기는 순간을 지켜본다."],
            "commentary": "끓는점은 압력에 따라 달라진다는 점이 다음 챕터로 이어진다.",
            "visual_query": "기포가 올라오는 냄비",
            "prompt": {"title": "따라 해 보기", "text": "집에서 물을 끓이며 온도를 1분마다 기록해 줘."},
        },
        {
            "id": "chapter-03", "title": "산에서는 왜 다를까", "start": 120.0, "end": 180.0,
            "summary_bullets": ["높은 곳은 기압이 낮아 더 낮은 온도에서 끓는다.", "그래서 산 위에서는 라면이 잘 안 익는다."],
            "key_point": "기압이 낮은 산에서는 물이 더 낮은 온도에서 끓는다.",
            "visual_query": "산 그림",
        },
    ],
}

COLORS = {"chapter-01": [(66, 99, 235), (99, 132, 255)],
          "chapter-02": [(230, 119, 0), (255, 159, 64)],
          "chapter-03": [(47, 158, 68), (105, 219, 124)]}


def ts(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"00:{int(m):02d}:{s:06.3f}"


def main() -> None:
    shutil.rmtree(ROOT, ignore_errors=True)
    (WORK / "captions").mkdir(parents=True)

    vtt = ["WEBVTT", ""]
    for start, end, text in CUES:
        vtt += [f"{ts(start)} --> {ts(end)}", text, ""]
    (WORK / "captions" / f"{VIDEO_ID}.ko.vtt").write_text("\n".join(vtt), encoding="utf-8")

    url = f"https://www.youtube.com/watch?v={VIDEO_ID}"
    meta = {"id": VIDEO_ID, "title": "물 끓는점 실험 (테스트용 가짜 영상)", "channel": "테스트 채널",
            "duration": 180, "duration_string": "3:00", "webpage_url": url,
            "description": "테스트용으로 만든 가짜 영상 정보입니다.",
            "chapters": [{"start_time": c["start"], "end_time": c["end"], "title": c["title"]}
                         for c in CHAPTERS["chapters"]]}
    dump(WORK / "metadata.json", meta)
    dump(WORK / "input.json", {"url": url, "sub_langs": "ko,ko-orig,en"})
    dump(WORK / "chapters.codex.json", CHAPTERS)

    frames, selections = [], []
    for ch in CHAPTERS["chapters"]:
        folder = WORK / "frames" / ch["id"]
        folder.mkdir(parents=True)
        for n, color in enumerate(COLORS[ch["id"]], 1):
            frame_id = f"{ch['id']}-f{n:03d}"
            Image.new("RGB", (320, 180), color).save(folder / f"{frame_id}.jpg", quality=80)
            stamp = ch["start"] + 15 * n
            frames.append({"chapter_id": ch["id"], "frame_id": frame_id, "timestamp": stamp,
                           "image_path": f"frames/{ch['id']}/{frame_id}.jpg"})
        selections.append({"chapter_id": ch["id"], "frame_id": f"{ch['id']}-f001",
                           "timestamp": ch["start"] + 15, "image_path": f"frames/{ch['id']}/{ch['id']}-f001.jpg",
                           "reason": "단색 테스트 이미지"})
    # a second frame placed after the first bullet (multi-frame chapters)
    selections.append({"chapter_id": "chapter-02", "frame_id": "chapter-02-f002", "timestamp": 90.0,
                       "image_path": "frames/chapter-02/chapter-02-f002.jpg", "after_bullet": 0,
                       "caption": "두 번째 테스트 이미지"})
    dump(WORK / "frames" / "manifest.json", {"frames": frames})
    dump(WORK / "selected-frames.json", {"selections": selections})
    print(ROOT)


def dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
