# Run with 10x's Python inside the prefix (pyhost.exe -u -I -S <this file> [N]): Linux programs
# started from Windows ones get process handles, exit codes and connected pipes.
import sys; sys.path.insert(0, r"C:\Program Files\PureDevSoftware\10x\Lib\Dlls")
import subprocess, ctypes, time, os
from ctypes import wintypes as w
k = ctypes.WinDLL("kernel32", use_last_error=True)
f = k.wine_get_dos_file_name; f.argtypes = [ctypes.c_char_p]; f.restype = ctypes.c_void_p
def dos(path):
    p = f(path.encode()); s = ctypes.wstring_at(p); k.HeapFree(k.GetProcessHeap(), 0, ctypes.c_void_p(p)); return s
ENV = dos("/usr/bin/env")
k.OpenProcess.restype = w.HANDLE; k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k.GetProcessId.argtypes = [w.HANDLE]; k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
k.WaitForMultipleObjects.argtypes = [w.DWORD, ctypes.POINTER(w.HANDLE), w.BOOL, w.DWORD]
k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; k.CloseHandle.argtypes = [w.HANDLE]
fails = 0
def check(name, cond, info=""):
    global fails
    print(("ok  " if cond else "FAIL"), name, info if not cond else ""); fails += not cond

p = subprocess.Popen([ENV, "yes"], stdout=subprocess.PIPE)
p.stdout.read(100000); p.stdout.close(); rc = p.wait(5)
check("reader closes -> SIGPIPE 141", rc == 141, rc)
p1 = subprocess.Popen([ENV, "seq", "100000"], stdout=subprocess.PIPE)
p2 = subprocess.Popen([ENV, "wc", "-l"], stdin=p1.stdout, stdout=subprocess.PIPE)
p1.stdout.close(); out = p2.communicate(timeout=10)[0]; p1.wait(5)
check("linux | linux through a Windows pipe", out.strip() == b"100000" and p1.returncode == 0, (out, p1.returncode))
r = subprocess.run(["cmd", "/c", "echo win& exit 7"], capture_output=True, timeout=20)
check("Windows child unchanged", r.returncode == 7 and r.stdout.strip() == b"win", repr(r))
p = subprocess.Popen([ENV, "sleep", "0.2"])
check("GetProcessId", k.GetProcessId(int(p._handle)) == p.pid, (k.GetProcessId(int(p._handle)), p.pid))
h = k.OpenProcess(0x101000, False, p.pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
check("OpenProcess by id", bool(h), ctypes.get_last_error())
code = w.DWORD(); k.GetExitCodeProcess(h, ctypes.byref(code)); check("STILL_ACTIVE", code.value == 259, code.value)
check("wait on opened handle", k.WaitForSingleObject(h, 5000) == 0)
k.GetExitCodeProcess(h, ctypes.byref(code)); check("exit code via opened handle", code.value == 0, code.value); k.CloseHandle(h); p.wait()
ps = [subprocess.Popen([ENV, "sleep", s]) for s in ("0.3", "0.1", "0.2")]
arr = (w.HANDLE * 3)(*[int(x._handle) for x in ps]); t = time.time()
first = k.WaitForMultipleObjects(3, arr, False, 5000); dt1 = time.time() - t
all_ = k.WaitForMultipleObjects(3, arr, True, 5000); dt2 = time.time() - t
check("WaitForMultipleObjects any/all", first == 1 and all_ == 0 and dt1 < 0.2 and 0.25 < dt2 < 0.5, (first, all_, dt1, dt2))
for x in ps: x.wait()
n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
t = time.time()
for i in range(n):
    r = subprocess.run([ENV, "sh", "-c", "cat; echo $1 >&2", "x", str(i)], input=b"in", capture_output=True)
    if (r.stdout, r.stderr, r.returncode) != (b"in", str(i).encode() + b"\n", 0): check("loop %d" % i, False, repr(r)); break
if n: print("    %d runs, %.1f ms each" % (n, (time.time() - t) * 1000 / n))
sys.stdout.flush(); os._exit(1 if fails else 0)
