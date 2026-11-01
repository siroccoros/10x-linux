/* Keep Wine's desktop process alive for the 10x prefix.
 *
 * Wine starts explorer.exe /desktop on demand and shuts it down once no user
 * program is left, so the first window of every launch would pay for starting
 * it again. Touching the desktop window and then waiting forever keeps it up,
 * the way Windows' desktop is always there. Prints "ready" once the desktop
 * is up. Started by `10x --prewarm`. */
#include <windows.h>

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmd, int show)
{
    DWORD written;

    GetDesktopWindow();
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), "ready\n", 6, &written, NULL);
    Sleep(INFINITE);
    return 0;
}
