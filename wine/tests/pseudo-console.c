/* Drive a pseudo console the way 10x's terminal does, with Linux's bash in it.
 * Build: zig cc -target x86_64-windows-gnu -O2 pseudo-console.c -o pseudo-console.exe
 * (and conprobe.c -o conprobe.exe beside it). Run from that directory:
 *   WINEDESKTOPSTART=1 WINEPATH='Z:\usr\bin' wine pseudo-console.exe OUT.txt */
#include <windows.h>
#include <stdio.h>
#include <string.h>

static HANDLE out_read, in_write;
static char buf[1 << 20];
static volatile LONG len;
static FILE *log_file;
static int fails;

static DWORD WINAPI reader( void *arg )
{
    DWORD n;
    char tmp[4096];
    while (ReadFile( out_read, tmp, sizeof(tmp), &n, NULL ) && n)
    {
        if (len + n < sizeof(buf)) { memcpy( buf + len, tmp, n ); InterlockedAdd( &len, n ); }
    }
    return 0;
}

static void tx( const char *s ) { DWORD n; WriteFile( in_write, s, strlen( s ), &n, NULL ); }

/* wait until the output since START contains WANT */
static int expect( LONG start, const char *want, DWORD ms )
{
    DWORD t0 = GetTickCount();
    while (GetTickCount() - t0 < ms)
    {
        LONG l = len;
        buf[l] = 0;
        for (LONG i = start; i + (LONG)strlen( want ) <= l; i++)
            if (!memcmp( buf + i, want, strlen( want ) )) return 1;
        Sleep( 20 );
    }
    return 0;
}

static void check( const char *what, int ok )
{
    fprintf( log_file, "%s %s\n", ok ? "ok  " : "FAIL", what );
    if (!ok) fails++;
}

static HANDLE start( HPCON *pc, COORD size, const char *cmd )
{
    HANDLE in_read, out_write;
    STARTUPINFOEXA si = {{ sizeof(si) }};
    PROCESS_INFORMATION pi;
    SIZE_T attr_size;
    char cmdline[256];

    CreatePipe( &in_read, &in_write, NULL, 0 );
    CreatePipe( &out_read, &out_write, NULL, 0 );
    if (CreatePseudoConsole( size, in_read, out_write, 0, pc ) != S_OK) return NULL;
    CloseHandle( in_read );
    CloseHandle( out_write );
    CreateThread( NULL, 0, reader, NULL, 0, NULL );

    InitializeProcThreadAttributeList( NULL, 1, 0, &attr_size );
    si.lpAttributeList = HeapAlloc( GetProcessHeap(), 0, attr_size );
    InitializeProcThreadAttributeList( si.lpAttributeList, 1, 0, &attr_size );
    UpdateProcThreadAttribute( si.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE, *pc, sizeof(*pc), NULL, NULL );
    strcpy( cmdline, cmd );
    if (!CreateProcessA( NULL, cmdline, NULL, NULL, FALSE, EXTENDED_STARTUPINFO_PRESENT, NULL, NULL, &si.StartupInfo, &pi ))
    {
        fprintf( log_file, "CreateProcess %s failed %lu\n", cmd, GetLastError() );
        return NULL;
    }
    CloseHandle( pi.hThread );
    return pi.hProcess;
}

int main( int argc, char **argv )
{
    COORD size = { 80, 24 }, big = { 100, 30 };
    HANDLE process;
    HPCON pc;
    DWORD code;
    LONG mark;

    log_file = fopen( argv[1], "w" );
    setvbuf( log_file, NULL, _IONBF, 0 );

    /* 1: a session */
    process = start( &pc, size, "bash --norc --noprofile -i" );
    check( "bash starts in the pseudo console", process != NULL );
    if (!process) return 1;
    tx( "PS1='$ '\r" );
    mark = len; tx( "tty; echo T=$TERM\r" );
    check( "it has a pty and TERM", expect( mark, "/dev/pts/", 3000 ) && expect( mark, "T=xterm-256color", 3000 ) );
    mark = len; tx( "stty size\r" );
    check( "the pty has the pseudo console's size", expect( mark, "24 80", 3000 ) );
    ResizePseudoConsole( pc, big );
    Sleep( 200 );
    mark = len; tx( "stty size\r" );
    check( "ResizePseudoConsole resizes the pty", expect( mark, "30 100", 3000 ) );
    mark = len; tx( "trap 'echo GOTWINCH' WINCH\r" );
    Sleep( 200 );
    ResizePseudoConsole( pc, size );
    check( "a resize sends SIGWINCH", expect( mark, "GOTWINCH", 3000 ) );
    ResizePseudoConsole( pc, big );
    Sleep( 200 );
    mark = len; tx( "sleep 30\r" );
    Sleep( 300 );
    tx( "\x03" );
    check( "Ctrl+C interrupts the foreground job", expect( mark, "$ ", 3000 ) );
    mark = len; tx( "echo rc=$?\r" );
    check( "the job died of SIGINT (rc=130)", expect( mark, "rc=130", 3000 ) );
    mark = len; tx( "read -r line; echo got:$line\r" );
    Sleep( 500 );
    tx( "h\xc3\xa9llo w\xc3\xb6rld\r" );
    check( "UTF-8 input reaches the program", expect( mark, "got:h\xc3\xa9llo w\xc3\xb6rld", 3000 ) );
    mark = len; tx( "read -r line; echo got:$line\r" );
    tx( "plain ascii\r" );
    if (!expect( mark, "got:plain ascii", 3000 ))
    {
        tx( "\r" );
        check( "typeahead (ASCII) reaches bash, in the read or at the next prompt",
               expect( mark, "plain: command not found", 3000 ) || expect( mark, "got:plain ascii", 100 ) );
    }
    else check( "typeahead (ASCII) reaches the program", 1 );
    mark = len; tx( "read -r line; echo got:$line\r" );
    tx( "t\xc3\xa9st\r" );
    if (!expect( mark, "got:t\xc3\xa9st", 3000 ))
    {
        tx( "\r" );  /* bash's own race: native bash too may leave it for the next prompt */
        check( "typeahead (UTF-8) reaches bash, in the read or at the next prompt",
               expect( mark, "t\xc3\xa9st: command not found", 3000 ) || expect( mark, "got:t\xc3\xa9st", 100 ) );
    }
    else check( "typeahead (UTF-8) reaches the program", 1 );
    mark = len; tx( "head -c 3000000 /dev/zero | tr '\\0' y | fold -w 99; echo DONE\r" );
    check( "3 MB of output arrives", expect( mark, "DONE", 20000 ) );
    tx( "exit 7\r" );
    check( "the process handle signals when bash exits", WaitForSingleObject( process, 5000 ) == WAIT_OBJECT_0 );
    GetExitCodeProcess( process, &code );
    fprintf( log_file, "     exit code %lu\n", code );
    check( "its exit code is bash's", code == 7 );
    ClosePseudoConsole( pc );
    check( "ClosePseudoConsole returns", 1 );
    CloseHandle( process );

    /* 2: the terminal closes while the program runs: it gets SIGHUP, like closing a terminal window */
    len = 0;
    process = start( &pc, size, "bash --norc --noprofile -i" );
    tx( "echo started\r" );
    check( "second session starts", expect( 0, "started", 3000 ) );
    ClosePseudoConsole( pc );
    check( "closing the pseudo console ends the program", WaitForSingleObject( process, 5000 ) == WAIT_OBJECT_0 );
    GetExitCodeProcess( process, &code );
    fprintf( log_file, "     exit code %lu (129 = SIGHUP)\n", code );

    /* 3: a Windows program in the pseudo console, resized */
    len = 0;
    process = start( &pc, size, "cmd.exe /k echo cmdstarted" );
    check( "cmd.exe starts", expect( 0, "cmdstarted", 5000 ) );
    ResizePseudoConsole( pc, big );
    Sleep( 300 );
    mark = len; tx( "conprobe.exe\r" );
    check( "cmd.exe sees the new size", expect( mark, "SIZE=100x30", 5000 ) );
    tx( "exit\r" );
    check( "cmd.exe exits", WaitForSingleObject( process, 5000 ) == WAIT_OBJECT_0 );
    ClosePseudoConsole( pc );

    buf[len] = 0;
    fprintf( log_file, "%d failed\n", fails );
    return fails;
}
