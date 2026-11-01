#!/usr/bin/env python3
"""Hide 10x's title-bar buttons for window actions the compositor lacks.

10x draws its own title bar. Toolkits show a minimise or maximise button
only when the Wayland compositor offers that action (xdg_toplevel
wm_capabilities); a button the compositor can't honour desyncs 10x from its
window (e.g. "minimised" with no minimised state). The launcher passes the
actions to hide. 10x looks for each UI file on disk (relative to its
install directory) before falling back to its packed 10x.data, so this
writes an edited copy of the main window layout to
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

10X.ui_proj_bin ("uiprojbin", version 4) element header:
    u32 type, u32 nchars incl. NUL, UTF-16LE name, i32 x, y, w, h
Title-bar elements are anchored to the right edge, x measured from it.

Usage: titlebar.py <10x install dir> <stamp file> [minimize] [maximize]
(no-op when already current)
"""
import os
import struct
import sys

MAGIC = b'puredev_package\0'
KNOWN_KEY = bytes.fromhex('47bc8d47f33bae15')
LAYOUT = 'UI/10X.ui_proj_bin'

# The buttons for each action; restore is maximise's other state, in the
# same place. Close is always available.
ACTIONS = {
    'minimize': ('WindowMinimiseButton',),
    'maximize': ('WindowMaximiseButton', 'WindowRestoreButton'),
}
BUTTONS = ('WindowMinimiseButton', 'WindowMaximiseButton',
           'WindowRestoreButton', 'WindowCloseButton')
# Right-anchored title-bar items that sit left of the buttons; they move
# right into the space hidden buttons leave. Each must occur exactly once.
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


def find_elements(layout, name):
    """Geometry offsets of every element header called `name`."""
    pat = struct.pack('<I', len(name) + 1) + (name + '\0').encode('utf-16-le')
    out, i = [], layout.find(pat)
    while i >= 0:
        if i >= 4:
            t, = struct.unpack_from('<I', layout, i - 4)
            if 1 <= t <= 64:
                out.append(i + len(pat))
        i = layout.find(pat, i + 1)
    return out


def patch(layout, hide):
    if layout[:9] != b'uiprojbin' or layout[9:13] != struct.pack('<I', 4):
        raise Unfamiliar('layout format/version changed')
    d = bytearray(layout)
    geo = lambda g: struct.unpack_from('<iiii', d, g)

    buttons = {n: find_elements(d, n) for n in BUTTONS}
    for n, gs in buttons.items():
        if not gs:
            raise Unfamiliar(f'{n} not found')
        for g in gs:
            x, y, w, h = geo(g)
            if not (0 <= x <= 200 and 0 <= y <= 4 and 0 < w <= 80 and 0 < h <= 60):
                raise Unfamiliar(f'{n} has unexpected geometry {x, y, w, h}')
    # Button slots from the right edge: (x, far edge). Each hidden slot
    # frees its width plus the gap to the slot on its right.
    slots = sorted({(geo(g)[0], geo(g)[0] + geo(g)[2]) for gs in buttons.values() for g in gs})
    hidden_names = {n for a in hide for n in ACTIONS[a]}
    hidden = {(geo(g)[0], geo(g)[0] + geo(g)[2]) for n in hidden_names for g in buttons[n]}
    freed = []
    for i, (x, far) in enumerate(slots):
        if (x, far) in hidden:
            freed.append((far, far - (slots[i - 1][1] if i else 0)))
    strip = slots[-1][1]

    def shift(x):
        return sum(width for far, width in freed if far <= x)

    moved = {n: find_elements(d, n) for n in SHIFT}
    for n, gs in moved.items():
        if len(gs) != 1:
            raise Unfamiliar(f'{n} found {len(gs)} times, expected 1')
        x, y, w, h = geo(gs[0])
        if not (strip <= x <= 1000 and 0 <= y <= 4):
            raise Unfamiliar(f'{n} has unexpected geometry {x, y, w, h}')

    for n, gs in buttons.items():
        for g in gs:
            if n in hidden_names:
                # Far outside the window with no size: not drawn, not clickable.
                struct.pack_into('<iiii', d, g, -10000, 0, 0, 0)
            else:
                x, = struct.unpack_from('<i', d, g)
                struct.pack_into('<i', d, g, x - shift(x))
    for (g,) in moved.values():
        x, = struct.unpack_from('<i', d, g)
        struct.pack_into('<i', d, g, x - shift(x))
    return bytes(d)


def main():
    install, stamp_path = sys.argv[1:3]
    hide = sorted(set(sys.argv[3:]))
    if any(a not in ACTIONS for a in hide):
        print(f'titlebar.py: actions are {", ".join(ACTIONS)}', file=sys.stderr)
        return 2
    data_path = os.path.join(install, '10x.data')
    target = os.path.join(install, *LAYOUT.split('/'))

    # Same format the launcher checks in bash: 10x.data size and mtime, this
    # script's mtime (so an updated script regenerates the layout), the
    # hidden actions.
    st = os.stat(data_path)
    stamp = f'{st.st_size} {int(st.st_mtime)} {int(os.stat(__file__).st_mtime)} {" ".join(hide)}'.rstrip()
    try:
        prev = open(stamp_path).read()
    except OSError:
        prev = None
    if prev == stamp and (os.path.exists(target) or not hide):
        return 0
    if prev == 'stock ' + stamp:
        return 0  # Already fell back (and said so) for this 10x version.

    if not hide:
        remove(target)
        write_stamp(stamp_path, stamp)
        return 0
    try:
        new = patch(read_layout(data_path), hide)
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
