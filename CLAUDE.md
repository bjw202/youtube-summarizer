## 하네스: YouTube 영상 요약

**목표:** YouTube 공개 영상의 자막 기반 비주얼 요약을 Markdown과 HTML로 생성

**트리거:** YouTube/유튜브 영상 요약 요청 시 `youtube-visual-summary` 스킬을 사용하라. 단순 질문은 직접 응답 가능.

**변경 이력:**

| 날짜 | 변경 내용 | 대상 | 사유 |
| --- | --- | --- | --- |
| 2026-06-04 | 자막 개별 다운로드 + 429 재시도 + 멱등성 강화 | `fetch_youtube.py` | 429 에러 시 전체 실패 문제, 재실행 시 처음부터 다시 시작 문제 |
| 2026-06-04 | JS 런타임(deno/node) 감지 + `--remote-components` 자동 추가 | `env_check.py`, `fetch_youtube.py` | yt-dlp EJS 챌린지 해결을 위해 런타임 필요 |
| 2026-06-04 | JS 런타임/429 트러블슈팅 추가 | `troubleshooting.md`, `SKILL.md` | 새 에러 시나리오 대응 가이드 |
| 2026-06-04 | 초기 구성 | 전체 | \- |
