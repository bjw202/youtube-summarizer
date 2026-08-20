#!/usr/bin/env python3
"""codex CLI에 SVG 다이어그램 생성을 위임하는 래퍼.

- 스펙 JSON을 읽어 다이어그램별로 `codex exec`를 호출한다
- 생성된 SVG를 검증하고, 실패하면 에러를 그대로 codex에 되돌려 재시도한다
- 이미 존재하는 SVG는 건너뛴다 (멱등) — codex 호출은 비용이 있다

사용법:
    python codex_svg.py RUN_DIR --spec RUN_DIR/_work/04_diagram_specs.json
    python codex_svg.py RUN_DIR --spec ... --only slug1,slug2 --force
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_ROUNDS = 3
CODEX_TIMEOUT = 900  # seconds per diagram

TOKENS = """--dg-ink        주 텍스트/선     (기본 #16191d)
--dg-ink-soft   보조 텍스트      (기본 #626a75)
--dg-bg         도면 배경        (기본 #ffffff)
--dg-surface    박스 채움        (기본 #f7f8fa)
--dg-line       테두리/연결선    (기본 #cbd3de)
--dg-accent     강조(파랑)       (기본 #2f5cff)
--dg-accent-soft 강조 채움       (기본 #eef2ff)
--dg-key        긍정/결과(초록)  (기본 #0f7a5a)
--dg-key-soft   긍정 채움        (기본 #e9f7f1)
--dg-warn       주의(주황)       (기본 #a4620a)
--dg-warn-soft  주의 채움        (기본 #fdf5e7)"""

PROMPT_TEMPLATE = """당신은 기술 문서용 SVG 다이어그램을 손으로 작성하는 전문가다.
아래 명세에 맞는 SVG 파일 **한 개**를 생성해 `{filename}` 경로에 저장하라.

## 다이어그램 명세
- 종류: {kind}
- 의도(독자가 이 그림으로 이해해야 하는 것): {intent}
- 반드시 포함할 요소:
{elements}
- 한글 라벨(이 표기를 그대로 사용):
{labels}
- 넣지 말아야 할 것:
{must_not}

## 배경 맥락
{context}

## SVG 하드 제약 (위반 시 반려된다)
1. 파일은 `<svg ...>`로 시작하는 순수 SVG 1.1/2.0. XML 선언은 있어도 되고 없어도 된다.
2. `width`/`height` 속성 대신 **`viewBox="0 0 {width} {height}"`와 `preserveAspectRatio="xMidYMid meet"`**를 지정하고, 추가로 `style="width:100%;height:auto"`를 둔다. 반응형으로 들어간다.
3. **외부 리소스 참조 절대 금지**: `<script>`, `<image href>`, `@import`, `http://`, `https://`, 외부 웹폰트 링크 모두 불가. 자기 완결형이어야 한다.
4. 폰트는 `font-family="-apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif"`만 사용한다.
5. 색은 **CSS 변수 + 폴백** 형태로만 쓴다. 예: `fill="var(--dg-surface, #f7f8fa)"`, `stroke="var(--dg-line, #cbd3de)"`. 하드코딩 색상 단독 사용 금지. 사용 가능한 토큰:
{tokens}
6. 텍스트 최소 크기 13px. 라벨끼리 겹치면 안 된다. 긴 라벨은 `<tspan>`으로 줄바꿈하라 (SVG는 자동 줄바꿈이 없다).
7. 모든 텍스트는 viewBox 안에 완전히 들어와야 한다. 가장자리에서 최소 12px 여백을 둔다.
8. 화살표는 `<defs><marker>`로 정의해 재사용하고, marker의 `fill`도 CSS 변수를 쓴다.
9. `<title>`과 `<desc>`를 최상단에 넣어 접근성 정보를 제공한다.
10. 장식을 최소화한다. 그라디언트·그림자·3D 효과 금지. 정보 전달만 한다.

## 작업 방식
- 파일을 작성한 뒤, 스스로 한 번 읽어 (a) 텍스트 겹침 (b) viewBox 밖으로 나간 요소 (c) 금지된 외부 참조 (d) 하드코딩 색상을 점검하고 고쳐라.
- 설명 문장을 출력할 필요 없다. 파일만 정확히 만들면 된다.
"""

RETRY_TEMPLATE = """직전에 생성한 `{filename}`이 검증에서 반려되었다. 아래 문제를 고쳐 같은 경로에 다시 저장하라.

## 검증 실패 사유
{errors}

## 리뷰 지적
{review}

원래 명세와 SVG 하드 제약은 그대로 유지한다. 파일만 수정하면 된다.
"""


def build_prompt(spec: dict, filename: str) -> str:
    def bullets(key: str, empty: str = "  (없음)") -> str:
        vals = spec.get(key) or []
        if not vals:
            return empty
        return "\n".join(f"  - {v}" for v in vals)

    return PROMPT_TEMPLATE.format(
        filename=filename,
        kind=spec.get("kind", "flow"),
        intent=spec.get("intent", ""),
        elements=bullets("elements"),
        labels=bullets("labels_ko"),
        must_not=bullets("must_not"),
        context=spec.get("context", "(추가 맥락 없음)"),
        width=spec.get("width", 1000),
        height=spec.get("height", 620),
        tokens="\n".join("   " + line for line in TOKENS.splitlines()),
    )


FORBIDDEN = [
    (re.compile(r"<script", re.I), "<script> 태그가 포함됨"),
    (re.compile(r"https?://(?!www\.w3\.org)", re.I), "외부 URL 참조가 포함됨 (w3.org 네임스페이스 제외)"),
    (re.compile(r"@import", re.I), "CSS @import가 포함됨"),
    (re.compile(r"<image\b", re.I), "<image> 외부 이미지 참조가 포함됨"),
    (re.compile(r"<foreignObject\b", re.I), "<foreignObject>는 렌더 호환성 문제로 금지됨"),
]


def validate_svg(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"파일이 생성되지 않음: {path}"]
    raw = path.read_text(encoding="utf-8", errors="replace")
    if len(raw.strip()) < 200:
        errors.append("SVG 내용이 지나치게 짧음 (200바이트 미만)")
    if "<svg" not in raw:
        errors.append("<svg> 루트 요소가 없음")
    for pattern, msg in FORBIDDEN:
        if pattern.search(raw):
            errors.append(msg)
    if "viewBox" not in raw:
        errors.append("viewBox 속성이 없음")
    if "var(--dg-" not in raw:
        errors.append("CSS 변수 색상 토큰(var(--dg-...))이 전혀 사용되지 않음")
    try:
        ET.fromstring(raw)
    except ET.ParseError as exc:
        errors.append(f"XML 파싱 실패: {exc}")
    # 텍스트가 하나도 없으면 라벨 누락 의심
    if "<text" not in raw and "<tspan" not in raw:
        errors.append("텍스트 라벨이 하나도 없음")
    return errors


def run_codex(prompt: str, cwd: Path, model: str | None) -> tuple[int, str]:
    cmd = ["codex", "exec", "--sandbox", "workspace-write", "-C", str(cwd)]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=CODEX_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return 124, f"codex exec 타임아웃 ({CODEX_TIMEOUT}s)"
    except FileNotFoundError:
        return 127, "codex CLI를 찾을 수 없음"
    tail = (proc.stdout or "")[-3000:] + (proc.stderr or "")[-2000:]
    return proc.returncode, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--only", default="", help="쉼표 구분 slug 목록만 생성")
    ap.add_argument("--force", action="store_true", help="기존 SVG도 재생성")
    ap.add_argument("--model", default=None, help="codex 모델 override")
    args = ap.parse_args()

    if shutil.which("codex") is None:
        print("[codex_svg] ERROR: codex CLI가 설치되어 있지 않습니다.", file=sys.stderr)
        return 127

    run_dir: Path = args.run_dir
    out_dir = run_dir / "assets" / "svg"
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_doc = json.loads(args.spec.read_text(encoding="utf-8"))
    diagrams = spec_doc.get("diagrams", spec_doc if isinstance(spec_doc, list) else [])
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    log = {"generated": [], "skipped": [], "failed": []}

    for spec in diagrams:
        slug = spec["slug"]
        if only and slug not in only:
            continue
        target = out_dir / f"{slug}.svg"
        if target.exists() and not args.force:
            print(f"[codex_svg] skip (exists): {slug}")
            log["skipped"].append(slug)
            continue

        filename = f"{slug}.svg"
        prompt = build_prompt(spec, filename)
        errors: list[str] = []
        ok = False
        for rnd in range(1, MAX_ROUNDS + 1):
            print(f"[codex_svg] {slug} — round {rnd}/{MAX_ROUNDS}", flush=True)
            if rnd > 1:
                prompt = RETRY_TEMPLATE.format(
                    filename=filename,
                    errors="\n".join(f"  - {e}" for e in errors),
                    review=spec.get("review_note", "(없음)"),
                )
            code, tail = run_codex(prompt, out_dir, args.model)
            if code not in (0,):
                print(f"[codex_svg]   codex exit={code}: {tail[-500:]}", file=sys.stderr)
            errors = validate_svg(target)
            if not errors:
                ok = True
                break
            print(f"[codex_svg]   검증 실패: {errors}", file=sys.stderr)

        if ok:
            log["generated"].append({"slug": slug, "path": str(target.relative_to(run_dir)), "rounds": rnd})
            print(f"[codex_svg] OK: {slug} ({rnd} round)")
        else:
            log["failed"].append({"slug": slug, "errors": errors})
            print(f"[codex_svg] FAILED: {slug} — {errors}", file=sys.stderr)

    log_path = run_dir / "_work" / "04_codex_svg_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[codex_svg] log → {log_path}")
    return 1 if log["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
