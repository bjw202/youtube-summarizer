---
name: youtube-visual-summary
description: "YouTube/유튜브 영상의 자막 기반 비주얼 요약을 Markdown과 HTML로 생성. YouTube URL이 주어지면 반드시 이 스킬을 사용할 것. 영상 요약, 비디오 요약, 비디오 서머리, 자막 요약, 챕터 분할, 프레임 추출, visual summary, 마크다운 요약, HTML 요약, summary.md, summary.html 생성 시에도 이 스킬 사용. 영상 구간을 설명과 나란히 놓고 섹션별로 공부하는 학습 페이지(학습 보기, study.html) — '섹션별로 영상이랑 같이 보고 싶어', '학습 노트', '용어집 페이지', '왼쪽 영상 오른쪽 설명', '구간 재생', '여러 영상을 하나로 묶어서 공부' — 요청 시에도 이 스킬을 사용. 후속 작업 — 다시 요약, 요약 수정, 요약 보완, 더 자세히, 간단히, 텍스트 전용 요약, 프레임만 재선택, 학습 보기 추가 — 요청 시에도 반드시 이 스킬을 사용."
---

# YouTube Visual Summary

YouTube 공개 영상의 자막 기반 비주얼 요약을 Markdown과 HTML 두 형식으로 생성하는 오케스트레이터 스킬.

## 실행 모드: 단일 오케스트레이터 (직접 수행)

순차 파이프라인이므로 에이전트 팀이나 서브 에이전트를 사용하지 않는다. 이 스킬이 직접 전체 워크플로우를 드라이브한다.

## 워크플로우

**단계 시간 기록:** 각 Phase를 시작하고 끝낼 때 한 줄씩 남긴다. `RUN_DIR`이 생기기 전(Phase 0~2)은 기록하지 않는다. 스스로 적는 것: Phase 3 시작은 `fetch_youtube.py`, 백그라운드 영상 받기의 `download` 시작·끝(실패면 `failed`)은 `fetch_frame_source.py`. **Phase 3 끝은 백그라운드 영상 받기 명령을 띄운 직후**(정본 자막 `transcript.json`이 확정된 뒤)에 적는다. 보고할 때 `--summary`로 단계별·전체 시간을 읽는다:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/timing.py RUN_DIR "Phase 5" start   # 끝나면 … end
uv run python .claude/skills/youtube-visual-summary/scripts/timing.py RUN_DIR --summary           # → _work/timing.log 요약
```

### Phase 0: 컨텍스트 확인

1. `runs/` 디렉토리에서 기존 산출물 확인
2. 실행 모드 결정:
   - 기존 run 없음 + 새 URL → **초기 실행** (Phase 1)
   - 기존 run 있음 + 수정 요청 → **부분 재실행** (해당 단계부터)
   - 기존 run 있음 + 새 URL → **새 실행**

### Phase 1: 입력 파싱

사용자 요청에서 다음을 추출한다:

- `url`: YouTube URL
- `summary_level`: `short`, `normal`, `detailed` (기본값: `normal`)
- `output_format`: `both`, `markdown`, `html` (기본값: `both`)
- `text_only`: `true`면 프레임 추출 생략 (기본값: `false`)
- `study_view`: `true`면 Phase 7 뒤에 학습 보기 단계 실행 (기본값: `false`). "섹션별로 영상과 같이 공부", "학습 노트/용어집 페이지", "구간 재생" 요청이면 `true`. 처음부터 `true`면 Phase 5의 프레임 소스를 `--with-audio`로 받는다

### Phase 2: 환경 준비

모든 명령은 **프로젝트 루트에서 `uv run`으로** 실행한다(`uv run python …`이 프로젝트의 `.venv`를 찾아 쓴다). `.venv/bin/python`처럼 경로를 직접 쓰지 않는다 — 윈도우에서는 `.venv\Scripts\python.exe`라서 동작하지 않는다.

1. 상태 확인:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/doctor.py --json
```

2. **`.venv`가 없거나(`checks.venv.ok: false`) `ok`가 `false`면 설치를 스스로 돌린다** — README를 건너뛴 첫 실행도 여기서 준비된다. 관리자 권한은 쓰지 않는다:

```bash
uv run .claude/skills/youtube-visual-summary/scripts/install.py
```

3. 다시 `doctor.py --json`. 아직 `ok: false`인 `checks` 항목은 그 항목의 `fix` 명령을 실행한다(같은 운영체제용으로 만들어져 있다). `fix`가 `null`이면 `hint`를 사용자에게 전하고 멈춘다. 두 번 고쳐도 안 되면 그대로 보고하고 멈춘다.

- `uv`가 없으면(`checks.uv.ok: false`) 설치 한 줄을 사용자에게 보여 준다 — macOS·Linux `curl -LsSf https://astral.sh/uv/install.sh | sh`, Windows PowerShell `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` — 설치 뒤에는 새 터미널이 필요하다.
- `features`가 기능별 가능 여부다: `summary`(기본), `text_only`, `study_view`, `stt`. 사용자가 고른 기능이 `ok`면 진행한다.
- 음성 인식은 `optional.stt`에 따로 있다. 자막이 없는 영상을 만났을 때만, **사용자에게 먼저 묻고**(모델 약 1.5GB) 동의하면 `install.py --with-stt`를 돌린다.

`install.py`가 하는 일 (몇 번을 다시 돌려도 안전):
- uv로 **Python 3.12 `.venv`**를 만든다(이미 있으면 그대로 쓴다). yt-dlp(≥2026.x)는 Python 3.10 이상이 필요하다 — 시스템 Python 3.9로 만들면 구버전 yt-dlp가 깔려 EJS 챌린지가 "The page needs to be reloaded"로 전면 실패한다.
- `yt-dlp[default,curl-cffi]`: `default` extra → `yt-dlp-ejs`(deno로 EJS 챌린지 해결) + brotli/requests 등, `curl-cffi` extra → 브라우저와 같은 방식으로 접속(impersonation)해 YouTube의 429(요청 과다) 응답을 줄인다(curl_cffi 버전 범위는 yt-dlp가 정한다). **`install.py`는 돌 때마다 yt-dlp를 최신으로 올린다**(YouTube 변경에 몇 주 안에 뒤처진다). 나머지 패키지는 없을 때만 설치한다.
- **`install.py`가 도는 때 = yt-dlp가 올라가는 때**: ① 첫 실행(`.venv` 없음) ② `doctor.py`가 `ok: false`일 때 — 설치된 yt-dlp가 **30일보다 오래됐으면** `checks.yt_dlp`가 `ok: false`(`age_days`에 날수)라서 여기에 들어간다 ③ 영상·자막 받기가 403·"Video unavailable" 등으로 실패할 때(`references/troubleshooting.md`). 그 밖의 실행에서는 올리지 않는다 — 매번 PyPI를 확인하지 않아 빠르고, 같은 달 안의 실행은 같은 yt-dlp로 돈다.
- `Pillow`, `static-ffmpeg`(시스템에 ffmpeg·ffprobe가 없으면 이 운영체제용 실행 파일을 한 번 받는다), PyPI `deno`(macOS·Linux·Windows x64. Windows ARM은 빌드가 없어 node를 쓰고, 없으면 설치 안내만 한다).
- `--with-stt`: Apple Silicon 맥은 mlx-whisper, 그 밖은 faster-whisper와 turbo 모델.

ffmpeg·ffprobe·deno·node는 **시스템에 있는 것을 먼저** 쓰고 없으면 `.venv` 쪽을 쓴다(`common.find_tool`). yt-dlp에는 고른 JS 런타임 경로를 `--js-runtimes`로 넘긴다.

### Phase 3: 데이터 수집

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_youtube.py "URL" --run-root runs
```

stdout에서 run 디렉토리 경로를 읽는다.

**자막 다운로드 동작:**
- 언어별 개별 다운로드: `ko` → `ko-orig` → `en` 순서로 시도
- 429 (Too Many Requests) 에러 시 지수 백오프로 최대 2회 재시도
- 부분 성공 허용: 하나의 언어라도 다운로드되면 워크플로우 계속 진행
- 멱등 재실행: 동일 URL의 기존 run이 있으면 메타데이터/자막을 스킵하고 누락분만 재시도
- JS 런타임 + curl_cffi가 감지되면 yt-dlp에 `--remote-components ejs:github`(EJS 챌린지 해결)와 `--impersonate chrome`(브라우저 방식 접속, 429 응답 감소)을 자동 추가

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/build_transcript.py RUN_DIR [--lang en]
```

**정본 자막 선택:** 기본 우선순위는 `ko` > `en`이고, 같은 언어 안에서는 업로더가 올린 수동 트랙(`.en-XXXX.vtt`)이 자동 생성(`.en.vtt`)보다 앞선다. **외국어 강의·세미나는 `--lang en`으로 원어를 정본으로 고정한다** — 한국어 자동 번역 자막은 고유명사를 파괴한다. 수동 트랙은 기본 fetch에 포함되지 않으므로 `_work/metadata.json`의 `subtitles`에 `en-...` 같은 키가 있으면 따로 받는다(자동 자막은 "AIME"→"Amy", "ORM"→"OM"처럼 받아쓴다):

```bash
uv run yt-dlp --skip-download --write-subs --sub-langs "<키>" --sub-format vtt \
  --impersonate chrome --remote-components ejs:github -o "RUN_DIR/_work/captions/%(id)s" "URL"
```

**영상은 지금 백그라운드로 받기 시작한다 (텍스트 전용이 아닐 때).** 영상 받기는 전체 시간의 대부분을 차지한다(63분 강의 1080p: 13분 26초, 그동안 Phase 4 분석은 약 4분). 자막을 받은 직후 시작해 두고 Phase 4를 진행한다. 출력을 로그로 남기고 마지막 줄에 종료 코드를 적는다:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR [--with-audio] \
  > RUN_DIR/_work/frame-source.log 2>&1; echo "exit=$?" >> RUN_DIR/_work/frame-source.log
```

- Claude Code에서는 Bash 도구의 `run_in_background: true`로 실행한다. 끝나면 완료 알림이 온다. 기다리는 동안 로그 파일을 반복해서 들여다보거나 `sleep`으로 기다리지 않는다.
- `study_view`면 처음부터 `--with-audio`를 붙인다(같은 파일로 프레임과 클립을 처리).
- **Phase 5 앞에서 기다린다.** 완료 알림을 받았거나 로그 마지막 줄이 `exit=…`이면 끝난 것이다. Phase 4가 먼저 끝났으면 알림이 올 때까지 다른 일을 하지 않고 기다린다(같은 다운로드를 두 번 시작하지 않는다).
- **실패하면(`exit=0`이 아니면)** 로그의 마지막 오류를 읽고, 같은 명령을 앞에서(foreground) 한 번 다시 돌린다. 그래도 안 되면 `install.py`로 yt-dlp를 올린 뒤 다시 시도하고(`references/troubleshooting.md`의 "Video Download 403"), 계속 실패하면 원인을 사용자에게 보고한다. 텍스트 전용으로 조용히 넘어가지 않는다.

**자막이 없어 실패하면 STT 폴백** (`doctor.py --json`의 `features.stt.ok`가 `true`일 때. `false`면 사용자에게 물어 동의하면 `install.py --with-stt`). 엔진은 자동 선택 — Apple Silicon 맥은 mlx-whisper, 그 밖은 faster-whisper(turbo, int8, beam 1):

```bash
# 1. 오디오만 다운로드 → RUN_DIR/_work/audio.mp3 (impersonation과 ffmpeg 위치를 스크립트가 넘긴다)
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_audio.py RUN_DIR

# 2. 전사 (한국어 영상은 --language ko 로 도메인 용어 prompt 주입; 영어 등은 생략 시 자동 감지)
uv run python .claude/skills/youtube-visual-summary/scripts/stt_transcribe.py RUN_DIR/_work/audio.mp3 RUN_DIR "URL" --language ko
```

- 10분 청크 캐시(`_work/stt_chunks/`)로 **재개 가능** — 긴 영상(3시간 라이브 등)도 중단 후 같은 명령으로 이어서.
- 결과는 `source: stt-mlx-whisper`(또는 `stt-faster-whisper`)인 `transcript.json` → 이후 Phase 4~ 파이프라인을 그대로 재사용.
- 자주 보는 채널의 고유명사는 스킬 폴더의 `stt-prompt.local.txt`(git 추적 제외)에 적어 두면 한국어 기본 용어 프롬프트 대신 쓰인다.
- **자막도 음성 인식도 쓸 수 없으면 여기서 멈춘다.** 텍스트 전용 모드는 영상 화면(프레임)만 빼는 모드이지 전사(`transcript.json`)가 없어도 되는 모드가 아니다 — 챕터 나누기와 요약이 전사를 읽기 때문이다. 사용자에게 이유(이 영상에 자막이 없고, 이 컴퓨터에서 음성 인식을 쓸 수 없거나 사용자가 원하지 않음)를 알리고, 할 수 있는 길(음성 인식을 설치한 뒤 다시 실행, 자막이 있는 다른 영상)을 제시한 뒤 끝낸다.

### Phase 4: 콘텐츠 분석 (Claude 직접 수행)

1. 압축 자막을 만들어 읽는다:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/compact_transcript.py RUN_DIR
```

   `_work/transcript.compact.txt`에 `[mm:ss] 문장` 한 줄씩 들어간다(`transcript.json`과 같은 내용, 키·끝 시각을 뺀 형태). **영상이 1시간을 넘으면 한 번에 읽지 말고 나눠 읽는다** — 스크립트가 30분 단위 `transcript.compact.partNN.txt`도 만든다. 조각마다 읽으면서 주제가 바뀌는 시각과 핵심 문장을 메모해 두고, 다 읽은 뒤 메모를 모아 챕터를 정한다. 조각 경계에 걸친 주제는 앞 조각의 메모에 "다음 조각으로 이어짐"을 남겨 끊기지 않게 한다.
2. **업로더 챕터와 설명란을 먼저 본다.** `_work/metadata.json`의 `chapters`(업로더가 단 `start_time`·`end_time`·`title` 목록 — 기존 run의 약 60%에 있다)와 `description`(설명란의 타임스탬프 목차·링크·용어)을 읽는다. **챕터 경계는 직접 정하지 않고 `plan_chapters.py`로 계산한다** — 같은 영상이면 어느 세션이 돌려도 같은 경계가 나온다:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/plan_chapters.py RUN_DIR --level detailed
```

   업로더 챕터 → 설명란 타임스탬프 → 영상 전체 순으로 출발점을 잡고, `references/summary-levels.md` "챕터 나누기 수치"의 결정 규칙(6분 넘는 챕터 나누기, 1분 미만 인사·광고 합치기, 경계를 ±15초 안의 넘김 문장 첫 단어로 옮기기, 나누는 지점 고르기)을 적용해 `_work/chapter-plan.json`과 표를 낸다. `chapters.codex.json`의 `start`·`end`는 **이 표의 값을 그대로** 쓰고(챕터 수도 같게), 제목·요점은 Claude가 쓴다. 표와 다르면 Phase 6.5의 `check_summary.py`가 WARN을 낸다. 나누는 지점은 Phase 6에서 화면 주제 자막 바로 한 번 더 확인한다(아래).
   **고유명사 교정 규칙.** 자동 자막·음성 인식은 사람 이름·약 이름·기관명을 자주 틀리게 받아쓴다(예: "산화세륨"→"산나세륨", "대도서관"→"대도소관").
   - **확정 교정**: 화면 글자(영상에 박힌 자막·슬라이드·이름 자막 — Phase 6에서 프레임을 볼 때), 설명란, 메타데이터(제목·태그·업로더 챕터)에서 같은 철자를 **확인한 경우에만** 고쳐 쓴다.
   - **추정 교정**: 확인하지 못하고 소리·문맥으로 짐작한 교정은 결과물에 원래 자막과 함께 `강수연(자막: 강수현, 추정 교정)`처럼 표시한다. 나중에 화면에서 확인되면 표시를 지운다.
   - **표시 범위: 챕터마다 그 이름이 처음 나오는 곳 한 번**(`title`→`key_point`→`summary_paragraphs`→`summary_bullets`→`caption` 순서로 처음). 같은 챕터의 이후 등장은 교정한 이름만 쓴다.
   - **의학·법률처럼 틀리면 해가 되는 분야는 특히 조심한다**: 약 이름·성분·용량, 질환명, 법 이름·조항 번호, 기관명을 추정으로 확정하지 않고, 숫자·용량·조항은 자막 값 그대로 옮긴다. 확인할 수 없으면 추정 표시를 남긴다.
3. `references/summary-levels.md` 읽어 요약 밀도 확인
4. 챕터 분할 및 `RUN_DIR/_work/chapters.codex.json` 생성:

```json
{
  "summary_level": "normal",
  "chapters": [
    {
      "id": "chapter-01",
      "title": "챕터 제목",
      "start": 12.0,
      "end": 145.5,
      "key_point": "이 장을 한 문장으로 — 무엇을 알게 되는가",
      "summary_bullets": ["..."],
      "visual_query": "찾아야 할 시각적 장면 설명",
      "summary_paragraphs": ["(선택) 요점 목록 앞에 놓일 설명 문단"],
      "prompt": {"title": "(선택) 카드 제목", "text": "영상에 나온 프롬프트·명령 원문"},
      "commentary": "(선택) 영상 밖 배경·해석 — 문자열 또는 문자열 목록"
    }
  ]
}
```

#### `chapters.codex.json` 필드

렌더러(`render_markdown.py`·`render_html.py`·`render_study.py`), 학습 보기 자동 구성(`study_spec.py`), 요약 점검(`check_summary.py`)이 읽는 필드는 아래가 전부다. 이 표와 스크립트가 실제로 읽는 필드가 같은지는 가짜 자료 테스트(`tests/run_fixture_tests.py`)가 확인한다. 스크립트에 필드를 더하면 이 표에도 더한다.

| 필드 | 필수 | 결과물 어디에 나오나 | `short` | `normal` | `detailed` |
| --- | --- | --- | --- | --- | --- |
| `summary_level` (맨 위) | 필수 | summary.md 머리의 "Summary level", summary.html 머리의 "간단·보통·상세 정리" | `short` | `normal` | `detailed` |
| `id` | 필수 | 목차 앵커, `images/`의 그림 이름, 학습 보기 항목·클립 이름 (`chapter-01` 꼴) | 같음 | 같음 | 같음 |
| `title` | 필수 | 장 제목·목차, 학습 보기 항목 이름 | 넓은 주제 이름 | 주제 이름 | 하위 주제까지 드러나게 |
| `start`, `end` | 필수 | 시각 표시와 유튜브 링크, 학습 보기 클립 구간 | 같음 | 같음 | 같음 |
| `key_point` | 필수 | summary.md "> **핵심 정리** —", summary.html "핵심" 상자, 학습 보기 항목 맨 위 리드 문장과 훑어보기 카드 설명 | 한 문장: 그 장의 결론 | 한 문장 | 한 문장 (길어지면 나머지는 요점으로) |
| `summary_bullets` | 필수 | 요점 목록(그림은 `after_bullet`으로 그 사이에), 학습 보기 요점 | 1~2개 | 2~4개 | 6~10개 |
| `visual_query` | 필수 | Phase 6 장면 고르기 기준. 장면에 `caption`이 없으면 그림의 대체 글(alt) | 가장 강한 장면 하나 | 구체적으로 | 구체적으로 |
| `summary_paragraphs` | 선택 | 요점 목록 앞 문단(md·html), 학습 보기 "영상 속 설명 자세히" | 쓰지 않음 | 논리 흐름이 있는 장에 1문단 | 과정·논증이 있는 장에 1~2문단(학습 보기를 만들면 권장) |
| `prompt` | 선택 | `{"title", "text"}` — md는 제목+코드 블록, html은 복사 버튼 카드, 학습 보기는 "AI에게 이렇게 요청" 카드(`text`만) | 영상에 따라 칠 프롬프트·명령이 나올 때만, 원문 그대로 | 같음 | 같음 |
| `commentary` | 선택 | 문자열 또는 목록 — md "### 해설", html "해설" 상자. 학습 보기에는 안 나옴 | 쓰지 않음 | 영상이 말하지 않은 배경·해석이 꼭 필요할 때만 | 같음 |
| `verified_numbers` | 선택 | 결과물에는 안 나옴. `check_summary.py`가 "자막에서 못 찾은 숫자" 경고에서 뺀다. `[{"value": "54", "seen": "56:08 원그래프 Improved 54%"}]` 꼴(문자열 `"54"`만 써도 됨) | 요약에 쓴 숫자가 말이 아니라 **화면**(슬라이드·도표·표)에만 있을 때, Phase 6에서 그 프레임을 보고 확인한 값만 | 같음 | 같음 |

- `key_point`는 제목을 되풀이하지 않는다. 그 문장만 읽고도 이 장에서 무엇을 알게 되는지 알 수 있어야 한다. 빠지면 `check_summary.py`가 FAIL을 낸다.
- `commentary`는 영상 내용과 섞지 않는다. 영상이 한 말은 `summary_bullets`·`summary_paragraphs`에, 덧붙인 해석만 여기에 쓴다.
- 화면에서 읽은 숫자를 요점에 쓸 때는 그 문장에 출처를 밝히고("화면 원그래프에서는 54%") `verified_numbers`에 값과 본 곳(시각·화면 이름)을 적는다. 짐작한 숫자는 넣지 않는다.

챕터 분할 원칙:
- 트랜스크립트 타임스탬프를 기준으로 의미 단위로 분할
- 챕터는 영상 처음부터 끝까지 빈틈없이, 겹치지 않게 잇는다(앞 챕터 `end` = 다음 챕터 `start`). 시각은 영상 길이(`metadata.json`의 `duration`)를 넘지 않는다
- 요약에 쓰는 숫자(금액·비율·연도·개수)는 자막에 나온 값 그대로 쓴다. 직접 계산한 값이면 계산했다고 밝힌다. 화면에서 읽은 값은 `verified_numbers`에 적는다
- 챕터 경계·개수는 `plan_chapters.py`가 낸 `_work/chapter-plan.json` 그대로다(규칙은 `references/summary-levels.md` "챕터 나누기 수치")
- 학습 보기를 만들어도 강의·발표 영상은 이 규칙의 챕터를 그대로 항목으로 쓴다(더 쪼개지 않는다). 10~40초 단위는 용어집·기능 소개·단계별 튜토리얼처럼 영상 자체가 짧은 단위로 나뉜 경우만이다
- 각 챕터에 구체적인 `visual_query` 포함

### Phase 5: 비주얼 처리 (텍스트 전용이 아닌 경우)

영상은 Phase 3 직후 백그라운드로 받기 시작했다 — 완료 알림(또는 로그의 `exit=0`)을 확인하고 시작한다.

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/extract_frames.py RUN_DIR
uv run python .claude/skills/youtube-visual-summary/scripts/make_contact_sheets.py RUN_DIR
```

**만들어지는 파일** (모두 `RUN_DIR/_work/` 아래):
- `_work/frames/manifest.json` — 후보 목록(`frame_id`·`chapter_id`·`timestamp`·`image_path`·`source`). `image_path`는 **`RUN_DIR/_work/` 기준** 상대 경로(`frames/chapter-01/chapter-01-f003.jpg`)
- `_work/frames/<chapter_id>/<frame_id>.jpg` — 후보 그림
- `_work/contact-sheets/<chapter_id>-sheet-01.jpg` — Phase 6에서 보는 컨택트 시트(후보를 한 장에 모은 그림), 목록은 `_work/contact-sheets/manifest.json`

**후보는 두 종류다** (manifest의 `source`): 일정 간격(`interval`, `…-f001`)과 **화면이 바뀌는 시점**(`scene`, `…-s001`). 화면 전환 검출은 영상 전체를 낮은 해상도로 한 번 훑는다(63분 VP9 영상 6구간 병렬 25초). 그림이 거의 같은 후보는 하나만 남는다 — 그 그림이 **처음 나온 전환**이 이기고, 그 뒤에 같은 그림을 찍은 일정 간격 후보는 전환 후보로 바뀐다(`scene_detection.replaced_interval`, 후보 수는 그대로). 그래서 슬라이드는 일정 간격 후보가 우연히 그 위에 떨어졌는지와 상관없이 전환 검출로 잡힌다. 다른 후보와 3초 안으로 가까운 전환은 **같은 카메라 구도(shot)일 때만** 버린다 — 일정 간격 후보가 슬라이드가 뜨기 1초 전 발표자를 찍었어도 슬라이드는 남는다. **챕터 시작 2초 전까지의 전환은 그 챕터의 후보**다(슬라이드가 경계 직전에 떠도 새 챕터에 들어간다). 챕터마다 최대 6장(`--max-scene-frames`). 20초쯤만 나오는 슬라이드처럼 일정 간격 후보 사이에 빠지는 장면을 잡는다. 끄려면 `--no-scenes`. 걸린 시간과 개수는 manifest의 `scene_detection`에, **버린 전환과 그 이유**(`same_picture` 같은 그림이 이미 있음·`near_time_same_shot` 3초 안 같은 구도·`chapter_edge` 영상 끝 1초·`chapter_cap` 챕터 상한·`outside_chapters` 챕터 밖, 어느 후보와 겹쳤는지, 해시·색 거리)는 `scene_detection.rejected`에 남는다. 화면에 있던 장면이 후보에 없으면 먼저 여기서 왜 빠졌는지 본다.

**특정 시각의 장면 하나를 더 넣을 때** (자막에서 "여기 보시면" 같은 말로 슬라이드가 있었다는 걸 알았는데 후보에 없을 때). 압축 자막 한 줄은 30~60초, `transcript.json` 한 줄도 약 14초라 시각을 눈으로 짐작하지 않는다. `find_moment.py`가 그 말이 나온 초를 찾아 `--at` 명령까지 보여 준다:

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/find_moment.py RUN_DIR "여기 보시면" [--chapter chapter-05]
#   11:14.0  word  chapter-05  …지금 여기 보시면 요거 이제 우리나라 표는…
#            → extract_frames.py RUN_DIR --at 675.0 --chapter chapter-05
uv run python .claude/skills/youtube-visual-summary/scripts/extract_frames.py RUN_DIR --at 675.0 --chapter chapter-05
uv run python .claude/skills/youtube-visual-summary/scripts/make_contact_sheets.py RUN_DIR
```

- 시각을 찾는 방법: 유튜브 자동 자막(`_work/captions/*.vtt`)은 단어마다 시각이 있어(`<00:11:14.279><c> 보시면</c>`) 그 말의 첫 단어 시각을 쓴다(`word`). 업로더 자막·음성 인식처럼 단어 시각이 없으면 `transcript.json` 세그먼트(`start`~`end`) 안에서 글자 위치 비율로 어림한다(`estimate` — 뽑은 그림을 꼭 확인).
- 제안 시각은 말한 시각 + 1초(`--settle`)다. 슬라이드는 보통 가리키는 말과 함께 뜬다. 뽑은 그림에 아직 없으면 몇 초 뒤로 한 번 더 뽑는다.
- `…-m001`(`source: manual`)로 manifest에 추가되고 나머지는 그대로다. `--chapter`를 빼면 시각으로 챕터를 찾는다. ffmpeg로 직접 뽑아 manifest를 손으로 고치지 않는다.

`fetch_frame_source.py`는 player client를 고정하지 않는다. yt-dlp 기본값 → `mweb` → `web_embedded,web_safari` 순으로 자동 재시도하고, 성공한 client를 `_work/frame-source.json`에 남긴다. 전부 실패하면 **먼저 `install.py`를 다시 돌려 yt-dlp를 올린다**(YouTube 변경에 몇 주 안에 뒤처진다) — 상세는 `references/troubleshooting.md`의 "Video Download 403".

챕터가 10~40초로 짧으면(용어·단계 하나씩 나눈 영상) `extract_frames.py --interval 2.5`로 고정 간격 조밀 추출을 한다 — 기본 간격(챕터 길이/15)으로는 3장뿐이다. 학습 보기(Phase 8)를 만들 run은 `fetch_frame_source.py --with-audio`로 받는다(소리 포함 1080p 한 파일로 프레임과 클립을 같이 처리).

텍스트 전용 run은 `selected-frames.json` 없이도 렌더링된다. 나중에 영상이 받아지면 Phase 5부터 이어서 돌린다.

### Phase 6: 프레임 선택 (Claude 직접 수행)

1. `references/frame-selection-rubric.md` 읽기 — 챕터당 장 수(기본 1장, 두 번째 장면을 고르는 조건과 상한), `caption` 쓰는 법
2. 컨택트 시트(`RUN_DIR/_work/contact-sheets/*-sheet-*.jpg`) 검사. 화면 글자(박힌 자막·슬라이드·이름 자막)로 Phase 4의 추정 교정을 확인하면 확정으로 바꾸고, 화면에서 읽은 숫자는 `verified_numbers`에 적는다
   **경계 검증 — 화면 주제 자막 바:** 강의·방송 화면 구석의 주제 자막 바(예: "뇌출혈의 종류 2. 지주막하출혈")가 바뀌는 장면을 찾는다. `chapter-plan.json`에 `start_rule`이 `split:`인 경계(업로더 챕터를 나눈 지점)가 있으면, 그 업로더 챕터 안에서 본 **바 변경을 모두** `--anchor`로 넘긴다. 바 변경 시각은 **새 바 글자가 처음 보이는 후보의 manifest `timestamp`**다 — 슬라이드만 바뀌고 바가 아직 이전 글자인 후보는 바 변경이 아니다:
   ```bash
   uv run python .claude/skills/youtube-visual-summary/scripts/plan_chapters.py RUN_DIR --level detailed --anchor 881.75 --anchor 972.25
   ```
   (어느 것을 쓸지는 스크립트가 정한다: 나누기 창 안의 바 변경 중 이상 지점에 가장 가까운 하나를 고르고, 그것이 지금 경계와 20초 넘게 다를 때만 그 근처의 가장 가까운 문장 시작으로 옮긴다. 창 밖 변경은 무시하고, 업로더 경계는 옮기지 않는다.) 경계가 바뀌었으면 `chapters.codex.json`의 두 챕터 `start`·`end`와 요점을 고치고 `extract_frames.py`·`make_contact_sheets.py`를 다시 돌린 뒤 두 챕터의 장면을 다시 고른다. 바가 없는 영상은 이 단계를 건너뛴다
3. `RUN_DIR/_work/selected-frames.json`에 **고른 `frame_id`와 판단만** 쓴다 — 시각·경로는 손으로 옮겨 적지 않는다:

```json
{
  "selections": [
    {"frame_id": "chapter-01-f003", "caption": "뇌경색과 뇌출혈 비율 원그래프", "reason": "요약에서 설명하는 차트가 보이고 읽기 가능함"},
    {"frame_id": "chapter-01-s002", "after_bullet": 3, "caption": "…", "reason": "…"}
  ]
}
```

4. `fill_selections.py`가 `_work/frames/manifest.json`에서 `chapter_id`·`timestamp`·`image_path`를 채우고 점검한다(없는 `frame_id`, 같은 장면 두 번, 범위 밖 `after_bullet`, `reason` 없음, 챕터 상한 초과는 FAIL — 파일을 고치지 않음. `caption` 없음·장면 없는 챕터는 WARN):

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fill_selections.py RUN_DIR --max-per-chapter 3   # 강의·발표 3, 화면 시연 6, short 1
```

필드: `frame_id`(필수), `reason`(필수 — 다른 후보보다 나은 이유, 내부 기록), `caption`(**모든 장면에 쓴다** — 독자가 그림 아래에서 읽는 설명이자 학습 보기 '장면 n' 하위 장면의 이름. 없으면 `reason`이 그림 아래에 그대로 나온다), `after_bullet`(0부터 세는 요점 번호 — 그 요점 바로 뒤에 그림. 없으면 챕터 맨 위. 한 챕터의 두 번째 장면부터는 붙인다). `image_path`는 `RUN_DIR/_work/` 기준 경로다.

**한 챕터에 여러 장면:** 같은 챕터의 `frame_id`를 여러 개 넣는다. 언제 두 번째 장면을 고르는지와 상한(강의·발표 3장, 화면 시연·튜토리얼 6장)은 rubric을 따른다. 챕터에 `prompt: {"title", "text"}`를 넣으면 복사 버튼이 달린 프롬프트 카드로 렌더된다. 화면 시연 영상에서 글자가 다 드러난 순간이 후보 사이에 있으면 `extract_frames.py RUN_DIR --interval 3`(챕터별 3초 간격)으로 다시 훑거나, `find_moment.py`로 시각을 찾아 `--at`으로 한 장씩 넣는다.

프레임 선택 기준:
- 시맨틱 매치 → 정보 가치(차트>얼굴) → 가독성 → 선명도 → 특이성
- 후보가 모두 부족하면 `--max-frames-per-chapter 16`으로 재추출

### Phase 6.5: 요약 점검

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/check_summary.py RUN_DIR
```

- **FAIL은 고치고 다시 돌린다**: 챕터 시각이 영상 밖, 챕터끼리 겹침, 2초 넘게 빈 구간, 이미지 없는 챕터(텍스트 전용 run은 검사 안 함), 없는 이미지 파일, `key_point`가 없는 챕터.
- 2026-11-02 전에 만든 run은 `key_point`가 원래 없거나 일부 장에만 있을 수 있다(그때까지의 run 120개 중 86개). 그런 run을 부분 재실행(장면만 다시 고르기 등)할 때는 `--allow-missing-key-point`를 붙여 WARN으로 낮춘다. 새 run에는 붙이지 않는다.
- **WARN은 확인한다**: 영상 앞뒤가 챕터에 안 들어감(인트로·아웃트로를 일부러 뺐으면 그대로 둔다), 자막에서 못 찾은 숫자(자막이 "십만"처럼 말로 적었거나 직접 계산한 값이면 그대로 두고, 잘못 옮긴 값이면 고친다. **화면(슬라이드·도표)에서 읽은 값이면 그 프레임을 다시 보고 맞을 때만 챕터의 `verified_numbers`에 적는다** — 그러면 경고에서 빠진다).

### Phase 7: 출력 렌더링

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/render_markdown.py RUN_DIR
uv run python .claude/skills/youtube-visual-summary/scripts/render_html.py RUN_DIR
```

`render_html.py`는 `assets/html-template.html`을 읽어 템플릿 변수를 치환한다.

최종 산출물:
- `RUN_DIR/summary.md`
- `RUN_DIR/summary.html`
- `RUN_DIR/images/` (선택된 프레임)

### Phase 8 (선택): 학습 보기

`study_view`일 때만. 각 섹션의 영상 구간(로컬 클립)과 설명을 나란히 놓는 `study.html`을 만든다. **먼저 `references/study-view.md`를 읽는다** — 스키마, 항목·장면 고르기, 영상 여러 개 통합 방식, 지켜야 할 규칙이 거기 있다.

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/fetch_frame_source.py RUN_DIR --with-audio  # 무음 소스면 다시 받기
# (선택) RUN_DIR/_work/study.json 작성 — 없으면 챕터 1개 = 항목 1개로 자동 구성
uv run python .claude/skills/youtube-visual-summary/scripts/cut_clips.py RUN_DIR
uv run python .claude/skills/youtube-visual-summary/scripts/render_study.py RUN_DIR
uv run python .claude/skills/youtube-visual-summary/scripts/check_study.py RUN_DIR
```

- 로컬 페이지에 유튜브 iframe을 넣지 않는다 — `file://`에서는 오류 153으로 재생되지 않는다. 구간 재생은 로컬 클립만 쓴다.
- `check_study.py`에 FAIL이 하나라도 있으면 전달하지 않는다(무음 클립, 빠진 이미지, 깨진 앵커, Phase 6에서 고른 장면이 학습 보기에 빠짐).
- `study.json` 없이 만들면 한 챕터에서 고른 장면이 여러 장일 때 첫 장면이 그 항목의 장면이 되고, 두 번째부터는 '함께 알아두기' 하위 장면으로 들어간다(플레이어 위 탭 '장면 1·장면 2…'으로 전환).

산출물: `RUN_DIR/study.html`, `RUN_DIR/images/study/`, `RUN_DIR/clips/`

### Phase 9: 정리 (원본 영상 지우기)

모든 산출물을 만들고 점검을 통과한 뒤 **자동으로** 돌린다. 사용자가 "영상은 남겨 줘"처럼 원본을 남겨 달라고 했으면 건너뛴다.

```bash
uv run python .claude/skills/youtube-visual-summary/scripts/clean_run.py RUN_DIR
```

- `_work/`의 원본 영상(1시간 1080p면 약 1.3GB — run 용량의 대부분)과 덜 받은 조각(`*.part`)만 지운다. 프레임·컨택트 시트·자막·JSON·`images/`·`clips/`는 남는다.
- **완성된 run에서만 지운다**: `check_summary.py` 통과, `study.html`이 있으면 `check_study.py` 통과, 고른 장면이 모두 `images/`에, 클립이 모두 `clips/`에 있을 때. 하나라도 아니면 이유를 출력하고 지우지 않는다(종료 코드 1). 지우기 전·후 용량을 출력하고, `--dry-run`은 지우지 않고 보여만 준다. 출력은 거절·dry run까지 모두 시각과 함께 `_work/clean_run.log`에 덧붙어 남는다(보고할 때 전·후 용량을 여기서 읽는다).
- 사용자에게 보고할 때 이렇게 알린다: "원본 영상(○GB)은 지웠습니다. 장면을 다시 고르거나 학습 보기를 나중에 추가하려면 `fetch_frame_source.py RUN_DIR`(학습 보기는 `--with-audio`)로 다시 받으면 됩니다."
- 이미 있는 `runs/`의 예전 실행 기록에는 사용자가 요청하지 않는 한 돌리지 않는다.

## 캡션 정책

우선순위: 수동 한국어 > 수동 영어 > 자동 생성 > 다른 언어. 자막이 없으면 STT 폴백(`stt_transcribe.py` — Apple Silicon은 mlx-whisper, 그 밖은 faster-whisper)으로 전사한다. STT도 불가하면 이유를 알리고 멈춘다(텍스트 전용도 전사가 있어야 만들 수 있다).

## 환경 정책

프로젝트 루트 `.venv` 사용. 시스템 Python 오염 방지. `install.py`가 uv로 관리하고(`setup_venv.py`·`env_check.py`는 하위 호환용 껍데기), 스크립트는 `uv run python`으로 실행한다. 관리자 권한(sudo)은 쓰지 않는다.

## 에러 핸들링

| 상황 | 대응 |
|------|------|
| 자막 없음 | STT 폴백(`stt_transcribe.py`)으로 전사(설치 안 됐으면 사용자 동의 후 `install.py --with-stt`); 사용자가 거부하거나 설치가 안 되면 이유를 알리고 멈춤 — 텍스트 전용도 전사가 필요하다 |
| 자막 일부 실패 (429) | 성공한 언어로 계속 진행, 실패 언어는 경고만 |
| 프레임 추출 실패 | 텍스트 전용으로 진행 |
| yt-dlp 실패 | 네트워크/권한 안내 |
| 비디오만 403 / Video unavailable | `install.py` 재실행(yt-dlp 업그레이드) → 자동 client 폴백 → `troubleshooting.md` |
| JS 런타임 없음 | `install.py` 재실행(.venv에 deno). Windows ARM은 `doctor.py`의 `hint`대로 node 설치 안내 |
| 스크립트 실행 에러 | `references/troubleshooting.md` 참조 |
| 학습 보기 클립 무음 / `frame source has no audio` | `fetch_frame_source.py RUN_DIR --with-audio` 후 `cut_clips.py --force` |
| 백그라운드 영상 받기 실패 (`frame-source.log`의 `exit=`가 0이 아님) | 로그 오류 확인 → 앞에서 한 번 재시도 → `install.py` 후 재시도 → 그래도 실패면 보고 (텍스트 전용으로 넘어가지 않음) |
| 후보에 필요한 장면이 없음 | `_work/frames/manifest.json`의 `scene_detection.rejected`에서 그 시각의 전환이 왜 빠졌는지 확인 → `find_moment.py RUN_DIR "말"`로 시각 찾기 → `extract_frames.py RUN_DIR --at 시각` 로 한 장 추가 → `make_contact_sheets.py` |
| `missing frame source video` (정리 후 다시 작업) | `clean_run.py`가 지운 것 — `fetch_frame_source.py RUN_DIR [--with-audio]` 로 다시 받기 |
| 학습 보기에서 유튜브 임베드 오류 153 | iframe을 쓰지 않는다 — `cut_clips.py`로 로컬 클립 생성 (`troubleshooting.md`) |

## 테스트 시나리오

### 정상 흐름

1. 사용자가 YouTube URL 제공
2. Phase 1-3: 환경 준비 → 메타데이터+자막 수집
3. Phase 4: `plan_chapters.py`로 경계 계산 → Claude가 트랜스크립트 분석 → chapters.codex.json 생성(경계는 plan 그대로)
4. Phase 5: 프레임 소스 다운로드 → 후보 프레임 추출 → contact sheet 생성
5. Phase 6: Claude가 contact sheet 검사 → selected-frames.json(frame_id·caption·reason) → `fill_selections.py`
6. Phase 6.5: `check_summary.py` OK (FAIL 0건)
7. Phase 7: summary.md + summary.html 렌더링
8. Phase 9: `clean_run.py`로 원본 영상 삭제(사용자가 남겨 달라고 하지 않았으면)
9. 결과: `runs/YYYY-MM-DD_HHMMSS_slug/` 에 전체 산출물 생성

### 학습 보기 흐름

1. 사용자가 "이 영상 섹션별로 영상이랑 같이 공부할 수 있게 만들어줘: [URL]" 입력 → `study_view: true`
2. Phase 1-4는 정상 흐름과 같다. 챕터 = 학습 항목이다: 강의·발표는 `summary-levels.md`의 챕터 수치 그대로(개념 하나 = 항목 하나, 보통 1~5분), 용어집·기능 소개·단계별 튜토리얼은 용어·단계 하나씩(10~40초)
3. Phase 3 직후 `fetch_frame_source.py --with-audio`를 백그라운드로 시작 → Phase 5: 완료 확인 → `extract_frames.py --interval 2.5`(챕터가 짧을 때) → contact sheet
4. Phase 6-7: 프레임 선택, summary.md/html
5. Phase 8: (필요하면 `study.json` 작성) → `cut_clips.py` → `render_study.py` → `check_study.py` OK
6. Phase 9: `clean_run.py`
7. 결과: `study.html` + `clips/` + `images/study/`

### 에러 흐름 (자막 없음)

1. Phase 3에서 `build_transcript.py` 실패 (`no VTT captions found`)
2. 사용자에게 STT 전사를 제안(설치 안 됐으면 약 1.5GB 설치가 필요하다고 함께 알림) → 동의하면 `stt_transcribe.py`로 `transcript.json`을 만들고 Phase 4부터 정상 흐름
3. STT를 쓸 수 없거나 사용자가 거부하면: 자막도 음성 인식도 없어 요약할 원문이 없다는 이유를 알리고 멈춘다
4. 결과: 산출물 없음 (텍스트 전용 모드로 넘어가지 않는다 — 텍스트 전용도 전사가 필요하다)
