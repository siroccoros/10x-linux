#!/usr/bin/env python3
"""Delete 10x's title-bar window buttons: the window manager handles them.

10x draws its own title bar with minimise, maximise/restore and close
buttons. On Linux the compositor owns those actions (its decorations, keys
and gestures), so the buttons are removed from 10x's layout (all but one,
which 10x needs, and which is hidden instead); the items that sat left of
them move right into the space. 10x looks for each UI file on
disk (relative to its install directory) before falling back to its packed
10x.data, so this writes an edited copy of the main window layout to
<install>/UI/10X.ui_proj_bin. 10x.exe itself is never modified.

The edit is regenerated from the installed 10x.data whenever 10x updates,
so a newer layout is never masked by a stale one. If anything about the
package or layout looks unfamiliar, the override is removed instead and 10x
shows its stock title bar.

10x.data ("puredev_package"): 16-byte magic, then everything XORed with a
repeating 8-byte key:
    u32 count
    count x (u32 nchars incl. NUL, UTF-16LE name)
    6 bytes (zero)
    count x (u64 file offset, u64 size, u64 FILETIME)

10X.ui_proj_bin ("uiprojbin", version 4): a root record, then its element
tree in pre-order. Each element's record:
    u32 type, u32 nchars incl. NUL, UTF-16LE name, i32 x, y, w, h,
    properties (by type), u32 number of children
and its children's records follow it. Title-bar elements are anchored to the
right edge, x measured from it.

Usage: titlebar.py <10x install dir> <stamp file>   (no-op when already current)
"""
import os
import re
import struct
import sys

MAGIC = b'puredev_package\0'
KNOWN_KEY = bytes.fromhex('47bc8d47f33bae15')
LAYOUT = 'UI/10X.ui_proj_bin'
# Candidate element headers: u32 type, u32 nchars incl. NUL; names are
# identifiers, sometimes with spaces ("TabbedPanel Main Panel", menu
# separators are "object").
HEADER = re.compile(rb'(?=[\x01-\x40]\0\0\0[\x02-\x40]\0\0\0)')
NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_ ]{1,60}')

# Restore is maximise's other state, in the same place.
BUTTONS = ('WindowMinimiseButton', 'WindowMaximiseButton',
           'WindowRestoreButton', 'WindowCloseButton')
# 10x needs this one in the main window's title bar to start.
KEEP = 'WindowMinimiseButton'
# Right-anchored title-bar items that sit left of the buttons; they move
# right into the space the buttons leave. Each must occur exactly once.
SHIFT = ('SearchButton', 'WorkspaceTreeButton', 'UpdateButton',
         'LicenseExpiredButton', 'ProgressBarPanel')


class Unfamiliar(Exception):
    pass


def xor(data, key):
    n = len(data)
    reps = key * (n // len(key) + 1)
    x = int.from_bytes(data, 'little') ^ int.from_bytes(reps[:n], 'little')
    return x.to_bytes(n, 'little')


def parse_package(body):
    """Return {name: (offset, size)} or raise Unfamiliar."""
    try:
        count, = struct.unpack_from('<I', body, 0)
        if not 0 < count < 100000:
            raise Unfamiliar(f'implausible file count {count}')
        p, names = 4, []
        for _ in range(count):
            l, = struct.unpack_from('<I', body, p)
            if not 0 < l < 1024:
                raise Unfamiliar('implausible name length')
            raw = body[p + 4:p + 4 + 2 * l]
            if raw[-2:] != b'\0\0':
                raise Unfamiliar('name not NUL-terminated')
            names.append(raw[:-2].decode('utf-16-le'))
            p += 4 + 2 * l
        if body[p:p + 6] != bytes(6):
            raise Unfamiliar('unexpected bytes after name table')
        p += 6
        files = {}
        for i, name in enumerate(names):
            off, size, _ = struct.unpack_from('<QQQ', body, p + 24 * i)
            if off < len(MAGIC) or off - len(MAGIC) + size > len(body):
                raise Unfamiliar(f'{name}: entry out of bounds')
            files[name] = (off - len(MAGIC), size)
        return files
    except (struct.error, UnicodeDecodeError) as e:
        raise Unfamiliar(f'package table: {e}')


def derive_key(enc):
    """Recover the key from the name table if 10x ever changes it."""
    sample = enc[:8192]
    key = bytearray(8)
    for lane in range(1, 8, 2):  # UTF-16 high bytes and u32 length tails: 0
        lb = sample[lane::8]
        key[lane] = max(range(256), key=lb.count)
    ok = set(b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-')
    for lane in range(0, 8, 2):
        lb = sample[lane::8]
        key[lane] = max(range(256), key=lambda k: sum((b ^ k) in ok for b in lb))
    return bytes(key)


def read_layout(data_path):
    raw = open(data_path, 'rb').read()
    if raw[:16] != MAGIC:
        raise Unfamiliar('10x.data magic changed')
    enc = raw[16:]
    for key in (KNOWN_KEY, None):
        key = key or derive_key(enc)
        body = xor(enc, key)
        try:
            files = parse_package(body)
        except Unfamiliar:
            continue
        if LAYOUT not in files:
            raise Unfamiliar(f'{LAYOUT} not in package')
        off, size = files[LAYOUT]
        return body[off:off + size]
    raise Unfamiliar('could not decode 10x.data')


def elements(layout):
    """The element tree: [(offset, type, name, end, children)] for the root's
    children, where [offset, end) is the element's own record. Raises
    Unfamiliar unless every record is accounted for, which no false header
    match survives."""
    heads = []
    for m in HEADER.finditer(layout):
        i = m.start()
        t, n = struct.unpack_from('<II', layout, i)
        raw = layout[i + 8:i + 8 + 2 * n]
        if len(raw) < 2 * n or raw[-2:] != b'\0\0' or len(layout) < i + 8 + 2 * n + 16:
            continue
        try:
            name = raw[:-2].decode('utf-16-le')
        except UnicodeDecodeError:
            continue
        if not NAME.fullmatch(name) or name.lower().endswith('png'):
            continue
        if all(-20000 < v < 20000 for v in struct.unpack_from('<iiii', layout, i + 8 + 2 * n)):
            heads.append((i, t, name))
    if not heads:
        raise Unfamiliar('no elements')
    ends = [h[0] for h in heads[1:]] + [len(layout)]
    count = lambda end: struct.unpack_from('<I', layout, end - 4)[0]

    k = 0
    def node():
        nonlocal k
        i, t, name = heads[k]
        end = ends[k]
        k += 1
        kids = []
        for _ in range(count(end)):
            if k == len(heads):
                raise Unfamiliar(f'{name}: fewer elements than it says it holds')
            kids.append(node())
        return i, t, name, end, kids

    roots = [node() for _ in range(count(heads[0][0]))]
    if k != len(heads):
        raise Unfamiliar(f'{len(heads) - k} elements outside the tree')
    return roots


def walk(nodes, parent=None):
    for nd in nodes:
        yield nd, parent
        yield from walk(nd[4], nd)


def find_elements(tree, name):
    """Geometry offsets of every element called `name`."""
    return [i + 8 + 2 * (len(name) + 1) for (i, _, n, _, _), _ in walk(tree) if n == name]


def patch(layout):
    if layout[:9] != b'uiprojbin' or layout[9:13] != struct.pack('<I', 4):
        raise Unfamiliar('layout format/version changed')
    d = bytearray(layout)
    geo = lambda g: struct.unpack_from('<iiii', d, g)
    tree = elements(d)

    buttons = {n: find_elements(tree, n) for n in BUTTONS}
    for n, gs in buttons.items():
        if not gs:
            raise Unfamiliar(f'{n} not found')
        for g in gs:
            x, y, w, h = geo(g)
            if not (0 <= x <= 200 and 0 <= y <= 4 and 0 < w <= 80 and 0 < h <= 60):
                raise Unfamiliar(f'{n} has unexpected geometry {x, y, w, h}')
    # The items left of the buttons move right by the strip the buttons
    # took, from the right edge to the far edge of the leftmost one.
    strip = max(geo(g)[0] + geo(g)[2] for gs in buttons.values() for g in gs)

    moved = {n: find_elements(tree, n) for n in SHIFT}
    for n, gs in moved.items():
        if len(gs) != 1:
            raise Unfamiliar(f'{n} found {len(gs)} times, expected 1')
        x, y, w, h = geo(gs[0])
        if not (strip <= x <= 1000 and 0 <= y <= 4):
            raise Unfamiliar(f'{n} has unexpected geometry {x, y, w, h}')
    for (g,) in moved.values():
        x, = struct.unpack_from('<i', d, g)
        struct.pack_into('<i', d, g, x - strip)

    # Cut each button's record and take it off its parent's child count,
    # from the end of the file back so earlier offsets stay valid. The main
    # window's minimise button is the exception: 10x won't start without it,
    # so it stays, far outside the window with no size (not drawn, not
    # clickable).
    main_bars = [nd for root in tree for nd in root[4]]
    cuts = []
    for (i, _, n, end, kids), parent in walk(tree):
        if n not in BUTTONS:
            continue
        if kids or parent is None:
            raise Unfamiliar(f'{n} at {i} is not a leaf of the title bar')
        if n == KEEP and parent in main_bars:
            struct.pack_into('<iiii', d, i + 8 + 2 * (len(n) + 1), -10000, 0, 0, 0)
        else:
            cuts.append((i, end, parent[3] - 4))
    if len(cuts) == sum(map(len, buttons.values())):
        raise Unfamiliar(f'no {KEEP} in the main title bar')
    for i, end, count_at in sorted(cuts, reverse=True):
        del d[i:end]
        c, = struct.unpack_from('<I', d, count_at)
        struct.pack_into('<I', d, count_at, c - 1)

    out = bytes(d)
    left = {n for (_, _, n, _, _), _ in walk(elements(out))}
    if left & set(BUTTONS) != {KEEP} or len(list(walk(elements(out)))) != len(list(walk(tree))) - len(cuts):
        raise Unfamiliar('edited layout does not parse as expected')
    return out


def main():
    install, stamp_path = sys.argv[1:3]
    data_path = os.path.join(install, '10x.data')
    target = os.path.join(install, *LAYOUT.split('/'))

    # Same format the launcher checks in bash: 10x.data size and mtime, this
    # script's mtime (so an updated script regenerates the layout).
    st = os.stat(data_path)
    stamp = f'{st.st_size} {int(st.st_mtime)} {int(os.stat(__file__).st_mtime)}'
    try:
        prev = open(stamp_path).read()
    except OSError:
        prev = None
    if prev == stamp and os.path.exists(target):
        return 0
    if prev == 'stock ' + stamp:
        return 0  # Already fell back (and said so) for this 10x version.

    try:
        new = patch(read_layout(data_path))
    except Unfamiliar as e:
        # Stock title bar beats a layout we don't understand.
        remove(target)
        write_stamp(stamp_path, 'stock ' + stamp)
        print(f'titlebar.py: {e}; using the stock title bar', file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(new)
    os.replace(tmp, target)
    write_stamp(stamp_path, stamp)
    return 0


def remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def write_stamp(path, text):
    with open(path + '.tmp', 'w') as f:
        f.write(text)
    os.replace(path + '.tmp', path)


if __name__ == '__main__':
    sys.exit(main())
