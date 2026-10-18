"""Tick checklist items by unique substring.  Usage: python scripts/tick.py "substr" "substr" ...

Fails loudly if a substring matches zero or multiple unchecked lines, so the
checklist can never be ticked by accident.
"""
from __future__ import annotations

import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "docs" / "DEVELOPMENT_CHECKLIST.md"


def main(keys: list[str]) -> int:
    lines = PATH.read_text(encoding="utf-8").splitlines()
    bad = 0
    for k in keys:
        hits = [i for i, l in enumerate(lines) if l.lstrip().startswith("- [ ]") and k in l]
        if len(hits) != 1:
            print(f"!! {len(hits)} matches for: {k!r}")
            bad += 1
            continue
        lines[hits[0]] = lines[hits[0]].replace("- [ ]", "- [x]", 1)
        print(f"ok  {lines[hits[0]].strip()[:100]}")
    PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if args and args[0] == "--file":
        args = [l for l in Path(args[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    sys.exit(main(args))
