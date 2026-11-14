"""
Build LabFlow's self-hosted Urdu webfonts and the static TTFs used by WeasyPrint.

Sources (Google Fonts, SIL Open Font License 1.1):
  * Noto Sans Arabic   - UI workhorse (variable wght 100-900)
  * Noto Naskh Arabic  - reading / PDF body (variable wght 400-700)
  * Noto Nastaliq Urdu - display only, >=18px (variable wght 400-700)

NO browser ever receives a raw variable TTF: every woff2 below is a static
instance, subset to Arabic + Latin + digits + the punctuation LabFlow prints.
The PDF worker receives full static TTFs (no subsetting, so no glyph can be
lost on an unusual patient name).

Run:  python scripts/fonts/build_fonts.py
"""

from __future__ import annotations

import pathlib
import shutil

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
VENDOR = ROOT / "scripts" / "fonts" / "vendor"
WEB_OUT = ROOT / "frontend" / "public" / "fonts"
PDF_OUT = ROOT / "backend" / "apps" / "reports" / "pdf" / "fonts"

# Arabic (0600-06FF), Arabic Supplement (0750-077F), Arabic Extended-A/B
# (08A0-08FF), Arabic Presentation Forms (FB50-FDFF, FE70-FEFF), Latin basic,
# Latin-1 punctuation, general punctuation, arrows and currency signs.
UNICODES = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+0300-036F,U+0600-06FF,U+0750-077F,U+0870-08FF,U+2000-206F,"
    "U+20A0-20CF,U+2100-214F,U+2190-21FF,U+2200-22FF,U+25A0-25FF,"
    "U+FB50-FDFF,U+FE70-FEFF"
)

FAMILIES = [
    # (source VF, output stem, weights, axis limits)
    ("NotoSansArabic-VF.ttf", "noto-sans-arabic", [400, 500, 600, 700, 800], None),
    ("NotoNaskhArabic-VF.ttf", "noto-naskh-arabic", [400, 700], None),
    ("NotoNastaliqUrdu-VF.ttf", "noto-nastaliq-urdu", [400, 700], None),
]


def instance_and_subset(src: pathlib.Path, stem: str, weight: int) -> TTFont:
    font = TTFont(src)
    # Pin every variable axis: wdth stays at its default (100).
    locations = {"wght": weight}
    if "wdth" in {a.axisTag for a in font["fvar"].axes}:
        locations["wdth"] = 100
    static = instantiateVariableFont(font, locations, updateFontNames=True)

    options = subset.Options()
    options.flavor = "woff2"
    options.desubroutinize = False
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables += ["DSIG"]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=subset.parse_unicodes(UNICODES))
    subsetter.subset(static)
    return static


def build_web() -> None:
    WEB_OUT.mkdir(parents=True, exist_ok=True)
    for src_name, stem, weights, _ in FAMILIES:
        for weight in weights:
            out = instance_and_subset(VENDOR / src_name, stem, weight)
            path = WEB_OUT / f"{stem}-{weight}.woff2"
            out.flavor = "woff2"
            out.save(path)
            print(f"web  {path.name:34s} {path.stat().st_size / 1024:7.1f} KiB")


def build_pdf() -> None:
    PDF_OUT.mkdir(parents=True, exist_ok=True)
    # Full static TTFs for the PDF worker: Naskh Regular/Bold + Nastaliq Regular.
    pdf_families = [
        ("NotoNaskhArabic-VF.ttf", "NotoNaskhArabic", [400, 700]),
        ("NotoNastaliqUrdu-VF.ttf", "NotoNastaliqUrdu", [400]),
    ]
    for src_name, stem, weights in pdf_families:
        for weight in weights:
            font = TTFont(VENDOR / src_name)
            locations = {"wght": weight}
            if "wdth" in {a.axisTag for a in font["fvar"].axes}:
                locations["wdth"] = 100
            static = instantiateVariableFont(font, locations, updateFontNames=True)
            suffix = "Regular" if weight == 400 else "Bold"
            path = PDF_OUT / f"{stem}-{suffix}.ttf"
            static.save(path)
            print(f"pdf  {path.name:34s} {path.stat().st_size / 1024:7.1f} KiB")

    for src_name, dest in [
        ("OFL-NotoSansArabic.txt", WEB_OUT / "OFL-NotoSansArabic.txt"),
        ("OFL-NotoNaskhArabic.txt", WEB_OUT / "OFL-NotoNaskhArabic.txt"),
        ("OFL-NotoNastaliqUrdu.txt", WEB_OUT / "OFL-NotoNastaliqUrdu.txt"),
        ("OFL-NotoNaskhArabic.txt", PDF_OUT / "OFL-NotoNaskhArabic.txt"),
        ("OFL-NotoNastaliqUrdu.txt", PDF_OUT / "OFL-NotoNastaliqUrdu.txt"),
    ]:
        shutil.copyfile(VENDOR / src_name, dest)


if __name__ == "__main__":
    build_web()
    build_pdf()
