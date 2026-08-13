## 하네스: YouTube 영상 요약

**목표:** YouTube 공개 영상의 자막 기반 비주얼 요약을 Markdown과 HTML로 생성

**트리거:**
- YouTube/유튜브 영상 **요약** 요청 → `youtube-visual-summary` 스킬
- 기술 세미나·논문 디펜스·학술 발표 영상의 **심층 슬라이드덱 보고서**(리서치 보강 + codex SVG 다이어그램 + 비전공자 눈높이 해설) 요청 → `technical-seminar-deck` 스킬
- 단순 질문은 직접 응답 가능

**변경 이력:**

| 날짜 | 변경 내용 | 대상 | 사유 |
| --- | --- | --- | --- |
| 2026-08-14 | **YouTube fetch 3중 결함 수정 (자막+비디오)** — (1) `setup_venv.py` 기본 `--python`을 시스템(3.9)→`3.12`, `yt-dlp[default,curl-cffi]`로 `yt-dlp-ejs`(EJS 챌린지) + `curl-cffi<0.16`(impersonation) 동시 설치. (2) `common.py`에 공통 헬퍼 통합 — `build_yt_dlp_base_args`(메타데이터/자막: `--remote-components ejs:github`+`--impersonate chrome`), `build_yt_dlp_video_args`(비디오: `--impersonate`만). **비디오엔 `--remote-components`를 빼야 SABR 우회 client(android_vr)가 살아남아 403이 안 남**(#12482). (3) 아래 2026-08-04 두 기록 정정 | `scripts/{setup_venv,common,fetch_youtube,fetch_frame_source}.py`, `SKILL.md`, `troubleshooting.md` | `w4tUGTdQRWU` 요약 시 3.9 venv→EJS 전면 실패 + 비디오→SABR 403. `yt-dlp[default,curl-cffi]`+Python3.12+비디오 EJS 제외로 자막(en)/비디오(720p) 모두 해결 확인 |
| 2026-08-04 | `.venv` 생성 시 **반드시 Python ≥3.10 사용** — `setup_venv.py`를 기본값(시스템 Python 3.9)으로 실행하면 최신 yt-dlp(요구 Python ≥3.10)가 설치되지 않아 YouTube EJS 챌린지가 `The page needs to be reloaded`로 전면 실패. 재현 명령: `python3 setup_venv.py --python 3.12` (uv가 자동으로 Python 3.12 확보) — **2026-08-14에 기본값 자체를 3.12로 고정해 재현 불필요** | `scripts/setup_venv.py` 실행, `troubleshooting.md` | 시스템 Python 3.9 환경에서 메타데이터/자막 fetch가 아예 불가능했음. yt-dlp 2026.7.4 + Python 3.12로 해결 확인 |
| ~~2026-08-04~~ | ~~`--remote-components ejs:github` 플래그는 현재 yt-dlp에 더 이상 존재하지 않음…~~ **⚠️ 정정(2026-08-14)**: 이 기록은 부정확 — `--remote-components`는 **여전히 현행 플래그**(폐지 아님), EJS 챌린지는 yt-dlp 단독이 아닌 **`yt-dlp-ejs` 플러그인(deno)**으로 해결, 429의 진짜 원인은 **impersonation(`curl_cffi`) 부재**. 상세는 상단 2026-08-14 행 참조 | — | 이력 무결성을 위해 취소선+정정 표시로 대체 |
| 2026-08-04 | **자산 지연 주입** — SVG를 `<script type="text/html">`에, 이미지를 `data-src`에 넣고 활성 슬라이드만 DOM에 채운다. 인쇄 시에는 전체 hydrate | `assets/deck-template.html`, `scripts/render_deck.py` | 59장 전체가 렌더 트리에 있으면 Chrome이 래스터 예산 때문에 인라인 SVG를 저해상도로 그려 도해 텍스트가 뭉개짐 (슬라이드 1장 문서에서는 선명함을 실험으로 확인) |
| 2026-08-04 | 프레임 소스를 720p→**1080p**로 올리고 확대 저장 폐지, JPEG→**WebP(q88)** 전환 | `04_visual_manifest.json`, 프레임 재추출 | 720p를 1600px로 업스케일해 저장하던 것이 흐림의 직접 원인. 원본 해상도 유지로 화질↑·용량↓(3.9MB→2.5MB) |
| 2026-08-04 | 발표 모드 도입 — 해설을 닫으면 슬라이드가 뷰포트를 꽉 채우고, 그림에 폭을 몰아주며(0.78fr : 2.3fr), 폰트를 `clamp()` 유동 스케일로 전환. `?notes=off` 파라미터와 상태 기억 추가 | `assets/deck-template.html`, `scripts/render_deck.py` | 한 화면으로 볼 때 그림·글씨가 작고 아래가 비어 시인성이 나쁘다는 피드백 |
| 2026-08-04 | 첫 실행(TEXterity 디펜스) 결과 — 자동 자막 번역이 고유명사를 파괴해 **원어 자막을 정본으로 삼는 정책**을 스킬에 반영. 15초 간격 개관 컨택트 시트를 기획 단계 입력으로 추가하면 프레임 질의 정확도가 크게 오름 | `skills/technical-seminar-deck/SKILL.md` | 실행 중 발견한 개선점 |
| 2026-08-04 | `technical-seminar-deck` 하네스 신설 — 에이전트 5종(seminar-analyst, research-augmenter, deck-planner, visual-producer, deck-writer) + QA 1종(deck-qa), 오케스트레이터 스킬, codex SVG 위임 스크립트, 슬라이드덱 템플릿 | `agents/*.md`, `skills/technical-seminar-deck/` | 기술 세미나는 단순 요약으로 부족 — 이해 순서 재배열·외부 리서치·개념 도해가 필요 |
| 2026-07-22 | HTML 템플릿을 학습 사이트 레이아웃으로 개편 (고정 사이드바 목차 + 스크롤 스파이, 진행률 바, 챕터 번호 배지, 다크모드 토큰화) | `assets/html-template.html` | 장편 영상 정리물의 탐색성·시인성 확보 |
| 2026-07-22 | `key_point`(핵심 정리) / `commentary`(해설) 필드 지원, 타임스탬프를 YouTube `t=` 딥링크로 렌더링 | `render_html.py`, `render_markdown.py` | 요약과 별개로 해설을 시각적으로 분리하고, 원문 대조 비용을 낮추기 위해 |
| 2026-06-09 | Tab 악보 추출 모드 폐지 | `extract_tab_frames.py`, `make_tab_contact_sheet.py`, `tab-extraction-guide.md`, `SKILL.md`, `agents/youtube-summarizer.md` | 비전 모델로 tab 악보 정확도 불가, 코드/프렛 판독 엉망 |
| 2026-06-04 | 자막 개별 다운로드 + 429 재시도 + 멱등성 강화 | `fetch_youtube.py` | 429 에러 시 전체 실패 문제, 재실행 시 처음부터 다시 시작 문제 |
| 2026-06-04 | JS 런타임(deno/node) 감지 + `--remote-components` 자동 추가 | `env_check.py`, `fetch_youtube.py` | yt-dlp EJS 챌린지 해결을 위해 런타임 필요 |
| 2026-06-04 | JS 런타임/429 트러블슈팅 추가 | `troubleshooting.md`, `SKILL.md` | 새 에러 시나리오 대응 가이드 |
| 2026-06-04 | 초기 구성 | 전체 | \- |
