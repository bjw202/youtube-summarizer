#!/usr/bin/env python3
"""deck.json 자동 검증기 — deck-qa 에이전트가 눈으로 훑는 대신 실행하는 스크립트.

검사 항목:
  구조   슬라이드 ID 중복, 고아 슬라이드(section_id 무효), 필수 필드 누락
  자산   visual.src 존재, SVG 파싱/외부참조/토큰, alt·caption 공백
  근거   notes.source.t 범위, research 항목의 URL 유무
  눈높이 슬라이드당 신규 용어 수, 불릿 개수/길이, 정의 없는 용어

종료 코드: 0 = 통과, 1 = major 이상 발견, 2 = blocker 발견
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BULLETS = 4
MAX_BULLET_CHARS = 90
MAX_NEW_TERMS = 2

FORBIDDEN_SVG = [
    (re.compile(r"<script", re.I), "SVG에 <script> 포함"),
    (re.compile(r"https?://(?!www\.w3\.org)", re.I), "SVG에 외부 URL 참조"),
    (re.compile(r"@import", re.I), "SVG에 @import"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--deck", default="_work/05_deck.json")
    ap.add_argument("--json-out", default="_work/06_auto_checks.json")
    args = ap.parse_args()

    run_dir: Path = args.run_dir
    deck = json.loads((run_dir / args.deck).read_text(encoding="utf-8"))
    meta = deck.get("meta", {})
    duration = float(meta.get("duration_sec") or 0)

    findings: list[dict] = []

    def add(sev, cat, sid, msg):
        findings.append({"severity": sev, "category": cat, "slide_id": sid, "summary": msg})

    # ── 구조 ──
    sec_ids = {s["id"] for s in deck.get("sections", [])}
    seen: set[str] = set()
    for s in deck.get("slides", []):
        sid = s.get("id")
        if not sid:
            add("blocker", "structure", "?", "슬라이드에 id가 없음")
            continue
        if sid in seen:
            add("blocker", "structure", sid, "슬라이드 id 중복")
        seen.add(sid)
        if not s.get("title"):
            add("major", "structure", sid, "title 누락")
        if s.get("section_id") and s["section_id"] not in sec_ids:
            add("major", "structure", sid, f"유효하지 않은 section_id: {s['section_id']}")
        if s.get("kind") not in {
            "cover", "agenda", "section", "problem", "prereq", "concept", "architecture",
            "math", "demo", "result", "limitation", "qa", "takeaway", "refs", "glossary",
        }:
            add("minor", "structure", sid, f"알 수 없는 kind: {s.get('kind')}")

    # ── 자산 ──
    broken: list[str] = []
    for s in deck.get("slides", []):
        sid = s.get("id", "?")
        v = s.get("visual") or {}
        if v.get("type", "none") == "none" or not v.get("src"):
            continue
        p = run_dir / v["src"]
        if not p.exists():
            add("blocker", "asset", sid, f"비주얼 파일 없음: {v['src']}")
            broken.append(v["src"])
            continue
        if not v.get("alt"):
            add("major", "asset", sid, "alt 텍스트 없음")
        if not v.get("caption"):
            add("minor", "asset", sid, "캡션 없음")
        if p.suffix.lower() == ".svg":
            raw = p.read_text(encoding="utf-8", errors="replace")
            try:
                ET.fromstring(raw)
            except ET.ParseError as e:
                add("blocker", "asset", sid, f"SVG XML 파싱 실패: {e}")
            for pat, msg in FORBIDDEN_SVG:
                if pat.search(raw):
                    add("blocker", "asset", sid, msg)
            if "var(--dg-" not in raw:
                add("major", "asset", sid, "SVG가 --dg-* 색상 토큰을 쓰지 않음 (다크모드 미대응)")
            if "viewBox" not in raw:
                add("major", "asset", sid, "SVG에 viewBox 없음")
        if v.get("type") == "frame" and "caption" in v and v["caption"]:
            if not re.search(r"\d+:\d{2}", v["caption"]):
                add("minor", "asset", sid, "프레임 캡션에 출처 타임스탬프가 없음")

    # ── 근거 ──
    for s in deck.get("slides", []):
        sid = s.get("id", "?")
        n = s.get("notes") or {}
        src = n.get("source") or {}
        if src.get("t") is not None:
            try:
                t = float(src["t"])
            except (TypeError, ValueError):
                add("major", "fact", sid, f"notes.source.t가 숫자가 아님: {src['t']}")
            else:
                if t < 0 or (duration and t > duration + 5):
                    add("major", "fact", sid, f"notes.source.t가 영상 길이({duration:.0f}s) 범위 밖: {t}")
        for r in n.get("research") or []:
            if not r.get("url"):
                add("major", "fact", sid, f"리서치 근거에 URL 없음: {str(r.get('claim') or r.get('title'))[:50]}")
        if s.get("kind") in {"result", "math"} and not (src.get("t") is not None or n.get("research")):
            add("major", "fact", sid, "결과/수식 슬라이드에 근거(타임스탬프 또는 출처)가 없음")

    # ── 눈높이 ──
    glossary_terms = {g.get("term", "").lower() for g in deck.get("glossary", [])}
    defined: set[str] = set()
    for s in deck.get("slides", []):
        sid = s.get("id", "?")
        n = s.get("notes") or {}
        terms = [t for t in (n.get("terms") or [])]
        new = [t for t in terms if t.lower() not in defined]
        if len(new) > MAX_NEW_TERMS:
            add("minor", "level", sid, f"신규 용어 {len(new)}개 (권장 {MAX_NEW_TERMS}개 이하): {', '.join(new)}")
        for t in terms:
            if t.lower() not in glossary_terms:
                add("major", "level", sid, f"용어 '{t}'가 glossary에 없음")
        defined |= {t.lower() for t in terms}

        bl = s.get("bullets") or []
        if len(bl) > MAX_BULLETS:
            add("minor", "level", sid, f"불릿 {len(bl)}개 (권장 {MAX_BULLETS}개 이하)")
        for b in bl:
            if len(b) > MAX_BULLET_CHARS:
                add("minor", "level", sid, f"불릿이 너무 긺({len(b)}자): {b[:40]}…")
        if s.get("kind") == "math" and not (n.get("explain")):
            add("major", "level", sid, "수식 슬라이드에 문장 해설이 없음")

    # ── 요약 ──
    counts = {"blocker": 0, "major": 0, "minor": 0}
    for f in findings:
        counts[f["severity"]] += 1

    report = {
        "slides": len(deck.get("slides", [])),
        "assets_checked": sum(1 for s in deck.get("slides", []) if (s.get("visual") or {}).get("src")),
        "broken_assets": broken,
        "counts": counts,
        "findings": findings,
    }
    out = run_dir / args.json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for f in findings:
        print(f"[{f['severity']:7}] {f['slide_id']:>14}  {f['category']:9} {f['summary']}")
    print(f"\n슬라이드 {report['slides']}장 · blocker {counts['blocker']} / major {counts['major']} / minor {counts['minor']}")
    print(f"리포트 → {out}")

    if counts["blocker"]:
        return 2
    if counts["major"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
