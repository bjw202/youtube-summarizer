import os, sys, shutil, glob, re, markdown

RUN_DIR = sys.argv[1]
WORK = os.path.join(RUN_DIR, "_work")
IMG = os.path.join(RUN_DIR, "images")
os.makedirs(IMG, exist_ok=True)

# 1. 각 챕터 대표 프레임 복사 (중간 timestamp 프레임)
frames_root = os.path.join(WORK, "frames")
chapter_img = {}
for ch in range(1, 14):
    chdir = os.path.join(frames_root, f"chapter-{ch:02d}")
    files = sorted(glob.glob(os.path.join(chdir, "*.jpg")))
    if not files:
        continue
    mid = files[len(files) // 2]
    dst = os.path.join(IMG, f"ch-{ch:02d}.jpg")
    shutil.copy(mid, dst)
    chapter_img[ch] = f"images/ch-{ch:02d}.jpg"

# 2. report.md 에서 이미 삽입된 표식이 있으면 원본에서 다시 시작(멱등)
md_path = os.path.join(RUN_DIR, "report.md")
md = open(md_path, encoding="utf-8").read()
# 이전 삽입 흔적 제거 (재실행 대비)
md = re.sub(r"\n!\[[^\]]*\]\(images/ch-\d+\.jpg\)\n<div align=\"center\"><sub>▲.*?</sub></div>", "", md)

lines = md.split("\n")
out = []
for l in lines:
    out.append(l)
    m = re.match(r"^### (\d+)장\.\s*(.+)", l)
    if m:
        ch = int(m.group(1))
        title = m.group(2).strip().split("(")[0].strip()
        if ch in chapter_img:
            rel = chapter_img[ch]
            out.append("")
            out.append(f"![{title}]({rel})")
            out.append(f'<div align="center"><sub>▲ {title} — 본 영상 해당 구간 화면</sub></div>')
open(md_path, "w", encoding="utf-8").write("\n".join(out))

# 3. HTML 생성 (img CSS 포함)
CSS = """
:root { --fg:#1a1a1a; --bg:#ffffff; --muted:#5b6470; --accent:#2b6cb0; --bgsoft:#f6f8fa; --border:#d9dee3; --quote:#4a5568; }
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Apple SD Gothic Neo", "Segoe UI", Roboto, "Noto Sans KR", sans-serif; color: var(--fg); background: var(--bg); margin: 0; line-height: 1.75; font-size: 17px; word-break: keep-all; overflow-wrap: anywhere; }
.wrap { max-width: 880px; margin: 0 auto; padding: 56px 28px 120px; }
h1 { font-size: 2.0rem; line-height: 1.35; margin: 0 0 8px; letter-spacing: -0.01em; }
h2 { font-size: 1.5rem; margin: 56px 0 14px; padding-bottom: 10px; border-bottom: 2px solid var(--border); letter-spacing: -0.01em; }
h3 { font-size: 1.2rem; margin: 34px 0 10px; }
h4 { font-size: 1.05rem; margin: 24px 0 8px; color: #2d3748; }
p { margin: 12px 0; }
a { color: var(--accent); text-decoration: none; word-break: break-all; }
a:hover { text-decoration: underline; }
hr { border: none; border-top: 1px solid var(--border); margin: 44px 0; }
strong { color: #1a202c; }
ul, ol { padding-left: 24px; margin: 12px 0; }
li { margin: 6px 0; }
code { background: var(--bgsoft); padding: 2px 6px; border-radius: 5px; font-size: 0.9em; font-family: "SF Mono", ui-monospace, Menlo, monospace; }
blockquote { margin: 18px 0; padding: 14px 20px; background: #eef4fb; border-left: 4px solid var(--accent); border-radius: 0 8px 8px 0; color: var(--quote); }
blockquote p { margin: 6px 0; }
table { border-collapse: collapse; width: 100%; margin: 20px 0; font-size: 0.96rem; display: block; overflow-x: auto; }
th, td { border: 1px solid var(--border); padding: 10px 14px; text-align: left; vertical-align: top; }
th { background: var(--bgsoft); font-weight: 700; }
tr:nth-child(even) td { background: #fbfcfd; }
img { max-width: 94%; height: auto; border-radius: 10px; margin: 18px auto 4px; display: block; box-shadow: 0 3px 14px rgba(0,0,0,0.10); border: 1px solid var(--border); }
.foot { margin-top: 60px; padding-top: 20px; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.88rem; }
@media (max-width: 640px) { body { font-size: 16px; } .wrap { padding: 32px 18px 80px; } h1 { font-size: 1.6rem; } h2 { font-size: 1.3rem; } }
"""

body = markdown.markdown("\n".join(out), extensions=["extra", "tables", "toc", "sane_lists", "md_in_html"])
doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>전자는 왜 멈추지 않는가 — 상세 정리</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<div class="foot">날것 그대로의 물리 「왜 전자는 절대 에너지가 떨어지지 않는가?」 영상 상세 정리 · 2026-06-29</div>
</div>
</body>
</html>"""
open(os.path.join(RUN_DIR, "report.html"), "w", encoding="utf-8").write(doc)
print(f"삽입 완료: {len(chapter_img)}개 챕터 이미지 → images/ 복사 및 report.md/html 반영")
