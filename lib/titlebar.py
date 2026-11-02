#!/usr/bin/env python3
"""Delete 10x's title-bar window buttons: the window manager handles them.

10x draws its own title bar with minimise, maximise/restore and close
buttons. On Linux the compositor owns those actions (its decorations, keys
and gestures), so the buttons are removed from 10x's layout; the items that
sat left of them move right into the space. 10x looks for each UI file on
disk (relative to its install directory) before falling back to its packed
10x.data, so this writes an edited copy of the main window layout to
<install>/UI/10X.ui_proj_bin.

10x.exe gets one fix so it runs without the minimise button: its title-bar
layout reads the button's position (the left edge of the controls on the
right, which the menu must not run into) without checking the lookup found
it, unlike every other lookup of a window button. That read becomes a call
to a routine in int3 padding that checks first; with no button there is
nothing on the right to run into. The rest of 10x.exe is left as it is
(including any patches of the user's own).

The edits are redone whenever 10x.data or 10x.exe changes, so a newer layout
is never masked by a stale one. If anything about the package, layout or
executable looks unfamiliar, nothing is patched: the layout override is
removed and 10x shows its stock title bar.

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

# The executable fix (see the module docstring). Each use of the minimise
# button's name is `lea rdx, name`, then the element lookup by name:
#   checked:   mov rcx,[rcx+58h]; call find; mov rcx,rax; test rcx,rcx
#   unchecked: mov rcx,[rax]; mov rcx,[rcx+58h]; call find; mov rcx,rax;
#              jmp USE
# USE (also reached with rcx = 0 when the window isn't found):
#   mov rax,[r13+18h]; lea rdx,[rsp+70h]; mov r12d,[rcx+190h]
# and the last instruction becomes `call CHECKED_READ; nop`.
EXE = '10x.exe'
MINIMISE = 'WindowMinimiseButton'
LEA_RDX = re.compile(rb'(?=\x48\x8d\x15)')
CHECKED = re.compile(rb'\x48\x8b\x49\x58\xe8(.{4})\x48\x8b\xc8\x48\x85\xc9', re.S)
UNCHECKED = re.compile(rb'\x48\x8b\x08\x48\x8b\x49\x58\xe8(.{4})\x48\x8b\xc8\xe9(.{4})', re.S)
USE = bytes.fromhex('498b4518 488d542470')
READ = bytes.fromhex('448ba190010000')                  # mov r12d,[rcx+190h]
CHECKED_READ = (bytes.fromhex('41bcffffff7f')           # mov r12d,7fffffffh
                + bytes.fromhex('4885c9 7407')          # test rcx,rcx; je ret
                + READ + b'\xc3')
NOP2 = b'\x66\x90'

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
    # from the end of the file back so earlier offsets stay valid.
    cuts = []
    for (i, _, n, end, kids), parent in walk(tree):
        if n not in BUTTONS:
            continue
        if kids or parent is None:
            raise Unfamiliar(f'{n} at {i} is not a leaf of the title bar')
        cuts.append((i, end, parent[3] - 4))
    for i, end, count_at in sorted(cuts, reverse=True):
        del d[i:end]
        c, = struct.unpack_from('<I', d, count_at)
        struct.pack_into('<I', d, count_at, c - 1)

    out = bytes(d)
    left = list(walk(elements(out)))
    if any(n in BUTTONS for (_, _, n, _, _), _ in left) or len(left) != len(list(walk(tree))) - len(cuts):
        raise Unfamiliar('edited layout does not parse as expected')
    return out


class PE:
    """The sections of a 64-bit PE image, and file offset <-> RVA."""

    def __init__(self, exe):
        try:
            if exe[:2] != b'MZ':
                raise Unfamiliar(f'{EXE} is not a PE image')
            pe, = struct.unpack_from('<I', exe, 0x3c)
            if exe[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<H', exe, pe + 4)[0] != 0x8664:
                raise Unfamiliar(f'{EXE} is not an x64 PE image')
            nsec, = struct.unpack_from('<H', exe, pe + 6)
            optsize, = struct.unpack_from('<H', exe, pe + 20)
            opt = pe + 24
            if struct.unpack_from('<H', exe, opt)[0] != 0x20b:
                raise Unfamiliar(f'{EXE} is not PE32+')
            self.base, = struct.unpack_from('<Q', exe, opt + 24)
            # Data directory 3: the exception table (RUNTIME_FUNCTIONs).
            exc_rva, exc_size = struct.unpack_from('<II', exe, opt + 112 + 3 * 8)
            self.sections = {}
            for k in range(nsec):
                s = opt + optsize + 40 * k
                name = exe[s:s + 8].rstrip(b'\0').decode('ascii', 'replace')
                vsize, rva, rawsize, raw = struct.unpack_from('<IIII', exe, s + 8)
                self.sections[name] = (rva, raw, min(vsize, rawsize))
            for name in ('.text', '.rdata'):
                if name not in self.sections:
                    raise Unfamiliar(f'{EXE} has no {name}')
            exc = self.off(exc_rva)
            self.functions = sorted(
                f[:2] for f in struct.iter_unpack('<III', exe[exc:exc + exc_size - exc_size % 12]) if f[0])
        except struct.error as e:
            raise Unfamiliar(f'{EXE} headers: {e}')

    def off(self, rva):
        for srva, raw, size in self.sections.values():
            if srva <= rva < srva + size:
                return raw + rva - srva
        raise Unfamiliar(f'{EXE}: RVA {rva:#x} is outside the image')

    def rva(self, off):
        for srva, raw, size in self.sections.values():
            if raw <= off < raw + size:
                return srva + off - raw
        raise Unfamiliar(f'{EXE}: offset {off:#x} is outside the image')

    def span(self, name):
        rva, raw, size = self.sections[name]
        return raw, raw + size

    def in_function(self, rva, n):
        """Whether [rva, rva + n) overlaps any function's code."""
        return any(b < rva + n and rva < e for b, e in self.functions)


def patch_exe(exe):
    """10x.exe with the minimise button's position read checked. Returns exe
    itself when it already has the fix; raises Unfamiliar if it can't be
    placed exactly."""
    pe = PE(exe)
    t0, t1 = pe.span('.text')
    r0, r1 = pe.span('.rdata')
    va = lambda off: pe.base + pe.rva(off)
    rel = lambda at: struct.unpack_from('<i', exe, at)[0]

    name = (MINIMISE + '\0').encode('utf-16-le')
    names, i = [], exe.find(name, r0, r1)
    while i >= 0:
        names.append(i)
        i = exe.find(name, i + 1, r1)
    if len(names) != 1:
        raise Unfamiliar(f'{MINIMISE} found {len(names)} times in {EXE}, expected 1')
    name_rva = pe.rva(names[0])

    # Every use of the name, each a lookup that checks its result but one.
    checked, unchecked, finds = [], [], set()
    for m in LEA_RDX.finditer(exe, t0, t1 - 7):
        p = m.start()
        if pe.rva(p) + 7 + rel(p + 3) != name_rva:
            continue
        for shape, into in ((CHECKED, checked), (UNCHECKED, unchecked)):
            u = shape.match(exe, p + 7)
            if u:
                into.append(u)
                finds.add(pe.rva(u.start(1)) + 4 + rel(u.start(1)))
                break
        else:
            raise Unfamiliar(f'unfamiliar use of {MINIMISE} at {va(p):#x}')
    if len(unchecked) != 1 or not checked or len(finds) != 1:
        raise Unfamiliar(f'{MINIMISE}: {len(checked)} checked and {len(unchecked)} unchecked '
                         f'lookups through {len(finds)} functions, expected 1+, 1, 1')
    u, = unchecked
    use = u.end() + rel(u.start(2))
    if exe[use - 2:use] != b'\x33\xc9' or exe[use:use + len(USE)] != USE:
        raise Unfamiliar(f'unfamiliar use of the minimise button at {va(use):#x}')
    read = use + len(USE)

    if exe[read:read + len(READ)] != READ:
        # Already fixed: the call to CHECKED_READ, which must be intact.
        cave = read + 5 + rel(read + 1) if exe[read] == 0xe8 else -1
        if (exe[read + 5:read + 7] != NOP2 or not t0 <= cave <= t1 - len(CHECKED_READ)
                or exe[cave:cave + len(CHECKED_READ)] != CHECKED_READ):
            raise Unfamiliar(f'unfamiliar code at {va(read):#x}')
        return exe

    # CHECKED_READ goes in the first run of int3 padding (between
    # functions, never executed) that holds it.
    n = len(CHECKED_READ)
    for m in re.finditer(rb'\xcc{%d,}' % n, exe[t0:t1]):
        cave = t0 + m.start()
        if not pe.in_function(pe.rva(cave), n):
            break
    else:
        raise Unfamiliar(f'no {n} bytes of padding in {EXE} for the fix')
    out = bytearray(exe)
    out[cave:cave + n] = CHECKED_READ
    out[read:read + 5] = b'\xe8' + struct.pack('<i', cave - (read + 5))
    out[read + 5:read + 7] = NOP2
    return bytes(out)


def main():
    install, stamp_path = sys.argv[1:3]
    data_path = os.path.join(install, '10x.data')
    exe_path = os.path.join(install, EXE)
    target = os.path.join(install, *LAYOUT.split('/'))

    # Same format the launcher checks in bash: 10x.data and 10x.exe size and
    # mtime, this script's mtime (so an updated script redoes the edits).
    def current():
        d, e = os.stat(data_path), os.stat(exe_path)
        return (f'{d.st_size} {int(d.st_mtime)} {e.st_size} {int(e.st_mtime)} '
                f'{int(os.stat(__file__).st_mtime)}')
    stamp = current()
    try:
        prev = open(stamp_path).read()
    except OSError:
        prev = None
    if prev == stamp and os.path.exists(target):
        return 0
    if prev == 'stock ' + stamp:
        return 0  # Already fell back (and said so) for this 10x version.

    # Both edits or neither: the layout without the minimise button needs
    # the fixed executable.
    try:
        exe = open(exe_path, 'rb').read()
        new_exe = patch_exe(exe)
        new = patch(read_layout(data_path))
    except Unfamiliar as e:
        # Stock title bar beats a layout we don't understand.
        remove(target)
        write_stamp(stamp_path, 'stock ' + stamp)
        print(f'titlebar.py: {e}; using the stock title bar', file=sys.stderr)
        return 1

    if new_exe is not exe:
        write_file(exe_path, new_exe, os.stat(exe_path).st_mode)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    write_file(target, new)
    write_stamp(stamp_path, current())  # 10x.exe's mtime has moved
    return 0


def write_file(path, data, mode=None):
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


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
