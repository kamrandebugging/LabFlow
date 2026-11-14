"""Font verification (research §10): required Urdu glyphs + Latin digits + budget.

Run: python scripts/fonts/verify_fonts.py
Exits non-zero if any shipped font misses a required glyph or the webfont
budget is exceeded.
"""

from __future__ import annotations

import pathlib
import sys

from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "frontend" / "public" / "fonts"
PDF = ROOT / "backend" / "apps" / "reports" / "pdf" / "fonts"

REQUIRED = "پچژگٹڈڑںےھی" + "0123456789" + "٠١٢٣٤٥٦٧٨٩"
BUDGET_KIB = 900


def check(path: pathlib.Path) -> int:
    font = TTFont(path)
    cmap = font.getBestCmap()
    missing = [ch for ch in REQUIRED if ord(ch) not in cmap]
    if missing:
        print(f"FAIL {path.name}: missing {''.join(missing)!r}")
        return 1
    print(f"ok   {path.name:34s} {path.stat().st_size / 1024:7.1f} KiB")
    return 0


def main() -> int:
    failures = 0
    web = sorted(WEB.glob("*.woff2"))
    if not web:
        print("no webfonts found — run scripts/fonts/build_fonts.py")
        return 1
    for path in web:
        failures += check(path)
    for path in sorted(PDF.glob("*.ttf")):
        failures += check(path)

    total = sum(p.stat().st_size for p in web) / 1024
    print(f"webfont total: {total:.1f} KiB (budget {BUDGET_KIB} KiB)")
    if total > BUDGET_KIB:
        failures += 1

    for family in ("NotoSansArabic", "NotoNaskhArabic", "NotoNastaliqUrdu"):
        if not (WEB / f"OFL-{family}.txt").exists():
            print(f"FAIL missing OFL-{family}.txt")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
