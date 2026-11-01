"""Install a PE file's main icon into an icon theme.

Usage: extract-icon.py PE THEME_DIR NAME
writes THEME_DIR/<n>x<n>/apps/NAME.png for each size the icon has.
"""
import io, os, struct, sys
from PIL import Image

def rva_to_off(sections, rva):
    for va, vsize, raw, rsize in sections:
        if va <= rva < va + max(vsize, rsize):
            return rva - va + raw
    raise ValueError(hex(rva))

def main(pe_path, theme_dir, icon_name):
    d = open(pe_path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec, = struct.unpack_from("<H", d, pe + 6)
    optsz, = struct.unpack_from("<H", d, pe + 20)
    opt = pe + 24
    magic, = struct.unpack_from("<H", d, opt)
    dd = opt + (112 if magic == 0x20B else 96)
    res_rva, _ = struct.unpack_from("<II", d, dd + 2 * 8)
    sections = []
    for i in range(nsec):
        s = opt + optsz + 40 * i
        vsize, va, rsize, raw = struct.unpack_from("<IIII", d, s + 8)
        sections.append((va, vsize, raw, rsize))
    base = rva_to_off(sections, res_rva)

    def entries(off):
        named, ids = struct.unpack_from("<HH", d, off + 12)
        for i in range(named + ids):
            name, target = struct.unpack_from("<II", d, off + 16 + 8 * i)
            yield name, target

    def subdir(target):
        return base + (target & 0x7FFFFFFF)

    def first_data(target):
        while target & 0x80000000:
            target = next(entries(subdir(target)))[1]
        rva, size = struct.unpack_from("<II", d, base + target)
        o = rva_to_off(sections, rva)
        return d[o:o + size]

    types = dict(entries(base))
    icons = {}
    for name, target in entries(subdir(types[3])):
        icons[name] = first_data(target)
    group = first_data(next(entries(subdir(types[14])))[1])

    _, _, count = struct.unpack_from("<HHH", group, 0)
    out_entries, blobs = [], []
    offset = 6 + 16 * count
    for i in range(count):
        w, h, cc, r, planes, bpp, size, icon_id = struct.unpack_from("<BBBBHHIH", group, 6 + 14 * i)
        blob = icons[icon_id]
        out_entries.append(struct.pack("<BBBBHHII", w, h, cc, r, planes, bpp, len(blob), offset))
        blobs.append(blob)
        offset += len(blob)
    ico = Image.open(io.BytesIO(struct.pack("<HHH", 0, 1, count) + b"".join(out_entries) + b"".join(blobs)))
    for w, h in sorted(ico.ico.sizes()):
        if w != h:
            continue
        out = os.path.join(theme_dir, f"{w}x{h}", "apps")
        os.makedirs(out, exist_ok=True)
        ico.ico.getimage((w, h)).save(os.path.join(out, f"{icon_name}.png"))


main(*sys.argv[1:4])
