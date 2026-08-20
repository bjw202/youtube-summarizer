# codex SVG 위임 규격

`visual-producer`가 codex CLI에 다이어그램 생성을 맡길 때의 규격.

## 왜 SVG인가

로컬 codex CLI에는 이미지 생성 모델이 붙어 있지 않다. 대신 codex는 **코드를 쓴다.** 기술 다이어그램에서는 이 편이 오히려 낫다:

- 라벨 텍스트가 정확하다 (래스터 생성 모델은 글자를 뭉갠다)
- 무한 확대해도 선명하고, 인쇄 품질이 보장된다
- CSS 변수로 다크모드에 자동 대응한다
- 파일이 작아 HTML 한 파일에 인라인할 수 있다
- 잘못된 부분을 텍스트 지시로 정확히 고칠 수 있다

## 실행

```bash
.venv/bin/python .claude/skills/technical-seminar-deck/scripts/codex_svg.py RUN_DIR \
  --spec RUN_DIR/_work/04_diagram_specs.json
# 특정 다이어그램만 재생성
.venv/bin/python .claude/skills/technical-seminar-deck/scripts/codex_svg.py RUN_DIR \
  --spec RUN_DIR/_work/04_diagram_specs.json --only pipeline-pose --force
```

`codex exec --sandbox workspace-write -C RUN_DIR/assets/svg` 로 실행되므로, codex는 그 디렉토리에만 쓴다. 스크립트가 프롬프트 조립·검증·재시도(최대 3라운드)를 담당한다. **`codex exec`를 손으로 조립하지 않는다.**

## 색상 토큰

SVG는 하드코딩 색 대신 `var(--dg-*, 폴백)` 형태만 쓴다. `render_deck.py`가 SVG를 HTML에 인라인하므로 부모 문서의 토큰을 상속받아 라이트/다크가 자동 전환된다.

| 토큰 | 용도 | 라이트 폴백 |
|------|------|-----------|
| `--dg-ink` | 주 텍스트, 주 선 | `#16191d` |
| `--dg-ink-soft` | 보조 라벨 | `#626a75` |
| `--dg-bg` | 도면 배경 | `#ffffff` |
| `--dg-surface` | 박스 채움 | `#f7f8fa` |
| `--dg-line` | 테두리, 연결선 | `#cbd3de` |
| `--dg-accent` | 강조(파랑) | `#2f5cff` |
| `--dg-accent-soft` | 강조 채움 | `#eef2ff` |
| `--dg-key` | 결과·긍정(초록) | `#0f7a5a` |
| `--dg-key-soft` | 긍정 채움 | `#e9f7f1` |
| `--dg-warn` | 주의·문제(주황) | `#a4620a` |
| `--dg-warn-soft` | 주의 채움 | `#fdf5e7` |

**색으로만 정보를 구분하지 않는다.** 색은 강조 수단이고, 구분은 라벨·형태·위치로 한다.

## 하드 제약 (스크립트가 자동 검증)

1. `<svg>` 루트, `viewBox` 필수, `width`/`height` 속성 대신 `style="width:100%;height:auto"`
2. 외부 참조 전면 금지 — `<script>`, `<image>`, `@import`, `http(s)://`(w3.org 네임스페이스 제외), 웹폰트
3. `<foreignObject>` 금지 (렌더 호환성)
4. `var(--dg-*)` 토큰을 최소 1회 이상 사용
5. 텍스트 요소 존재 (라벨 없는 그림은 반려)
6. XML 파싱 통과

자동 검증이 잡지 **못하는** 것: 텍스트 겹침, viewBox 밖 요소, 논리적 오류, 잘못된 화살표 방향. **반드시 사람(에이전트)이 SVG를 열어 확인한다.**

## 다이어그램 종류별 지침

| kind | 권장 크기 | 핵심 |
|------|----------|------|
| `flow` | 1080×420~560 | 좌→우 단계 박스, 단계 아래 입출력 자료형 라벨, 되먹임은 아래쪽 곡선 |
| `architecture` | 1000×640 | 모듈 그룹 박스로 계층 표현, 경계면에 데이터 형식 명시 |
| `geometry` | 900×600 | 좌표축·각도·힘 벡터. 기준 프레임을 반드시 표시 |
| `comparison` | 1040×520 | 좌우 2분할, 상단에 대비 축 이름, 하단에 결론 한 줄 |
| `timeline` | 1100×360 | 가로 축, 눈금 라벨, 항목은 축 위아래 교대 배치 |
| `equation` | 1000×480 | 수식을 크게 두고, 각 항에서 콜아웃 선을 빼 설명 상자로 연결 |

## 프롬프트 작성 요령

`diagram_spec`이 곧 발주서다. 다음이 모호하면 codex가 지어낸다.

- **`intent`**: "무엇을 그려라"가 아니라 **"독자가 이 그림을 보고 무엇을 이해해야 하는가"**를 쓴다
- **`elements`**: 배치·개수·방향까지 구체적으로. "박스 4개를 좌→우로" 처럼
- **`labels_ko`**: 그림에 들어갈 한글 문자열을 **그대로** 나열. codex가 번역하게 두지 않는다
- **`must_not`**: 근거 없는 수치, 원 논문 그림 모방, 확인하지 않은 하드웨어 형상을 항상 포함
- **`context`**: 발표 타임스탬프와 화자의 설명 요지. codex가 맥락을 알아야 적절한 추상화 수준을 고른다

## 검수 체크리스트

생성된 SVG를 열어 확인한다.

- [ ] 라벨끼리, 라벨과 선이 겹치지 않는가
- [ ] viewBox 밖으로 나간 요소가 없는가 (가장자리 12px 여백)
- [ ] 화살표 방향이 데이터 흐름과 일치하는가
- [ ] `labels_ko`의 문자열이 그대로 들어갔는가 (오타·번역 없이)
- [ ] `must_not` 위반이 없는가 (특히 지어낸 수치)
- [ ] 다크모드에서 텍스트가 읽히는가 (`--dg-ink` 사용 여부)
- [ ] 폰트 크기 13px 이상인가
- [ ] 그림 하나가 한 가지만 설명하는가 (욕심내면 아무것도 전달 안 된다)

문제가 있으면 spec에 `review_note`를 추가하고 `--only {slug} --force`로 재요청한다. `review_note`는 구체적으로 쓴다 — "라벨이 겹침"이 아니라 "'이진 접촉 패치' 라벨이 아래 화살표와 겹침. 박스 높이를 늘리거나 라벨을 박스 안으로 옮길 것".

## 실패 처리

3라운드 후에도 불량이면 포기한다. 그 슬라이드는 `visual.type: "none"`으로 두고, `deck-writer`가 해설 노트에 텍스트로 설명하며, `gaps`에 기록한다. 불량 그림을 넣는 것보다 없는 편이 낫다.
