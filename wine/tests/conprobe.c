#include <windows.h>
#include <stdio.h>
int main( void )
{
    CONSOLE_SCREEN_BUFFER_INFO info;
    GetConsoleScreenBufferInfo( GetStdHandle( STD_OUTPUT_HANDLE ), &info );
    printf( "SIZE=%dx%d WIN=%dx%d\n", info.dwSize.X, info.dwSize.Y,
            info.srWindow.Right - info.srWindow.Left + 1, info.srWindow.Bottom - info.srWindow.Top + 1 );
    return 0;
}
