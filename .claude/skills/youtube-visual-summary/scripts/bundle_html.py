#!/usr/bin/env python3
"""Inline every local image into summary.html so the page is a single portable file."""
from __future__ import annotations

import argparse
import base64
import io
import mimetypes
import re
from pathlib import Path

from common import HarnessError

try:
    from PIL import Image
except ImportError:  # Pillow is a recommended, not required, dependency
    Image = None


SRC_PATTERN = re.compile(r'src="(?!data:)([^"]+)"')


def encode_image(path: Path, max_width: int, quality: int) -> str:
    """Return a data: URI for path, recompressing when Pillow is available."""
    if Image is not None and path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if max_width and img.width > max_width:
                height = round(img.height * max_width / img.width)
                img = img.resize((max_width, height), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            payload = buffer.getvalue()
        return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle summary.html into a single self-contained file.")
    parser.add_argument("run_dir")
    parser.add_argument("--max-width", type=int, default=1280, help="downscale wider images (0 disables)")
    parser.add_argument("--quality", type=int, default=82, help="JPEG quality for recompression")
    parser.add_argument("--output", default="summary.standalone.html")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    source = run_dir / "summary.html"
    if not source.exists():
        raise HarnessError(f"summary.html not found: {source}")

    html = source.read_text(encoding="utf-8")
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        rel = match.group(1)
        target = (run_dir / rel).resolve()
        if not target.exists():
            missing.append(rel)
            return match.group(0)
        return f'src="{encode_image(target, args.max_width, args.quality)}"'

    bundled, count = SRC_PATTERN.subn(replace, html)
    if missing:
        raise HarnessError("missing image(s): " + ", ".join(missing))

    out = run_dir / args.output
    out.write_text(bundled, encoding="utf-8")
    size_mb = out.stat().st_size / 1_048_576
    print(f"[bundle_html] inlined {count} image(s) -> {size_mb:.1f} MB")
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
