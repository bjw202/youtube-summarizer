#!/usr/bin/env python3
"""Check page templates against references/design.md.

Templates must take colors and font sizes from assets/base.css tokens. This
flags raw color literals and px font sizes written directly in a template's
own CSS (the {{BASE_CSS}} slot itself is not scanned), and any var(--token)
that neither base.css nor the template defines.

usage: check_design.py [template ...]   (default: every assets/*-template.html)
exit 1 when any template breaks the rules.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
VAR_USE_RE = re.compile(r"var\((--[\w-]+)")
VAR_DEF_RE = re.compile(r"(--[\w-]+)\s*:")
RULES = [
    ("color literal", re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")),
    ("px font size", re.compile(r"font(?:-size)?\s*:[^;{}]*\b\d+(?:\.\d+)?px")),
]


def check(path: Path) -> list[str]:
    problems = []
    text = path.read_text(encoding="utf-8")
    defined = set(VAR_DEF_RE.findall((ASSETS / "base.css").read_text(encoding="utf-8")))
    defined |= set(VAR_DEF_RE.findall(text))
    for name in sorted(set(VAR_USE_RE.findall(text)) - defined):
        problems.append(f"{path.name}: undefined token: {name}")
    for block in STYLE_RE.findall(text):
        if "{{BASE_CSS}}" not in block:
            problems.append(f"{path.name}: <style> does not include {{{{BASE_CSS}}}}")
        own = block.replace("{{BASE_CSS}}", "")
        for lineno, line in enumerate(own.splitlines(), 1):
            for name, rule in RULES:
                if rule.search(line):
                    problems.append(f"{path.name}: {name}: {line.strip()[:90]}")
    return problems


def main() -> int:
    targets = [Path(p) for p in sys.argv[1:]] or sorted(ASSETS.glob("*-template.html"))
    failed = False
    for path in targets:
        problems = check(path)
        if problems:
            failed = True
            print(f"FAIL {path.name} ({len(problems)})")
            for p in problems[:12]:
                print("  " + p)
            if len(problems) > 12:
                print(f"  … {len(problems) - 12} more")
        else:
            print(f"OK   {path.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
