# Run with 10x's Python inside the prefix (pyhost.exe -u -I -S <this file> [N]): Linux programs
# started from Windows ones get process handles, exit codes and connected pipes.
import sys; sys.path.insert(0, r"C:\Program Files\PureDevSoftware\10x\Lib\Dlls")
import subprocess, ctypes, time, os
k = ctypes.WinDLL("kernel32")
f = k.wine_get_dos_file_name; f.argtypes = [ctypes.c_char_p]; f.restype = ctypes.c_void_p
def dos(path):
    p = f(path.encode()); s = ctypes.wstring_at(p); k.HeapFree(k.GetProcessHeap(), 0, ctypes.c_void_p(p)); return s
ENV = dos("/usr/bin/env")
fails = 0
def check(name, cond, info=""):
    global fails
    print(("ok  " if cond else "FAIL"), name, info if not cond else "")
    fails += not cond
def run(args, **kw): return subprocess.run([ENV] + args, **kw)

r = run(["echo", "hello from linux"], capture_output=True, timeout=10)
check("capture stdout", r.returncode == 0 and r.stdout == b"hello from linux\n", repr(r))
r = run(["sh", "-c", "exit 42"], timeout=10); check("exit code 42", r.returncode == 42, r.returncode)
r = run(["sh", "-c", "kill -TERM $$"], timeout=10); check("killed by SIGTERM -> 143", r.returncode == 143, r.returncode)
r = run(["sh", "-c", "echo out; echo err >&2"], capture_output=True, timeout=10)
check("stdout/stderr separate", (r.stdout, r.stderr) == (b"out\n", b"err\n"), repr(r))
r = run(["sh", "-c", "echo out; echo err >&2"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
check("stderr merged", r.stdout == b"out\nerr\n", repr(r))
data = os.urandom(1 << 20)
t = time.time(); r = run(["cat"], input=data, capture_output=True, timeout=30)
check("1 MiB through cat", r.stdout == data and r.returncode == 0, (len(r.stdout), r.returncode)); print("    %.0f ms" % ((time.time() - t) * 1000))
r = run(["sh", "-c", "read a; echo got:$a"], input=b"line\n", capture_output=True, timeout=10)
check("stdin line", r.stdout == b"got:line\n", repr(r))
r = run(["head", "-c", "10"], input=data, capture_output=True, timeout=10)
check("program closes stdin early", r.stdout == data[:10] and r.returncode == 0, (len(r.stdout), r.returncode))
r = run(["true"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
check("devnull", r.returncode == 0, r.returncode)
p = subprocess.Popen([ENV, "sleep", "0.3"]); t = time.time()
check("pid", p.pid > 0, p.pid); check("running", p.poll() is None, p.poll())
rc = p.wait(5); dt = time.time() - t
check("wait ~0.3 s", rc == 0 and 0.25 < dt < 0.6, (rc, dt))
p = subprocess.Popen([ENV, "sh", "-c", "echo $$; exec sleep 30"], stdout=subprocess.PIPE)
lpid = int(p.stdout.readline()); p.terminate(); rc = p.wait(5); time.sleep(0.05)
check("terminate -> exit 1, process gone", rc == 1 and not os.path.exists("Z:\\proc\\%d\\stat" % lpid), (rc, lpid))
try:
    run(["sleep", "5"], timeout=0.5); check("timeout raises", False)
except subprocess.TimeoutExpired: check("timeout raises", True)
t = time.time()
for i in range(200):
    r = run(["printf", "%d", str(i)], capture_output=True)
    if r.stdout != str(i).encode() or r.returncode: check("loop %d" % i, False, repr(r)); break
else: check("200 runs", True)
print("    %.1f ms per run" % ((time.time() - t) * 5))
sys.stdout.flush()
os._exit(1 if fails else 0)
