"""Build Windows-named font stand-ins for the 10x Wine prefix.

10x loads UI fonts itself by scanning C:\\windows\\Fonts for a matching family
name, so a substitution rule isn't enough: the TTF must call itself "Segoe UI".
Selawik is Microsoft's open, metric-compatible Segoe UI; Carlito is metric-
compatible with Calibri.
"""
import sys
from fontTools.ttLib import TTFont

src_selawik, src_carlito, out = sys.argv[1:4]

# (source, out file, family, subfamily, typographic family, typographic subfamily)
jobs = [
    (f"{src_selawik}/selawk.ttf",   "segoeui.ttf",   "Segoe UI",           "Regular", "Segoe UI", "Regular"),
    (f"{src_selawik}/selawkb.ttf",  "segoeuib.ttf",  "Segoe UI",           "Bold",    "Segoe UI", "Bold"),
    (f"{src_selawik}/selawkl.ttf",  "segoeuil.ttf",  "Segoe UI Light",     "Regular", "Segoe UI", "Light"),
    (f"{src_selawik}/selawksl.ttf", "segoeuisl.ttf", "Segoe UI Semilight", "Regular", "Segoe UI", "Semilight"),
    (f"{src_selawik}/selawksb.ttf", "seguisb.ttf",   "Segoe UI Semibold",  "Regular", "Segoe UI", "Semibold"),
    (f"{src_carlito}/Carlito-Regular.ttf", "calibril.ttf", "Calibri Light", "Regular", "Calibri", "Light"),
]

for src, dst, fam, sub, tfam, tsub in jobs:
    f = TTFont(src)
    name = f["name"]
    full = tfam if tsub == "Regular" else f"{tfam} {tsub}"
    ps = full.replace(" ", "") if tsub == "Regular" else f"{tfam.replace(' ', '')}-{tsub}"
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22):
            name.removeNames(nameID=rec.nameID)
    for nid, val in ((1, fam), (2, sub), (3, f"{full};10x-linux"), (4, full), (6, ps), (16, tfam), (17, tsub)):
        name.setName(val, nid, 3, 1, 0x409)
        name.setName(val, nid, 1, 0, 0)
    f.save(f"{out}/{dst}")
    print(dst, "->", full)
