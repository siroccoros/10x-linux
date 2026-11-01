# 10x Editor on Linux: Wine with 10x's patches, its launcher, and the pinned
# pieces 10x-setup builds each user's prefix from. 10x itself is not included:
# 10x-setup installs it from your own 10xInstaller.exe.
pkgname=10x-linux
pkgver=1.0.565
pkgrel=1
pkgdesc="Run 10x Editor (Windows) natively on Wayland through a patched Wine"
arch=(x86_64)
url="https://github.com/nottzaid/10x-linux"
license=(LGPL-2.1-or-later)
options=(!lto !debug pestrip)

_winever=11.20
_dxvkver=3.1.1
_winetricksver=20260125
_selawikver=1.01
_carlitocommit=3a810cab78ebd6e2e4eed42af9e8453c4f9b850a  # 20230509

depends=(
  # Wine (as Arch's wine package)
  desktop-file-utils fontconfig freetype2 gettext glib2 glibc hicolor-icon-theme
  libgcc libpcap libunwind libx11 libxcursor libxext libxi libxkbcommon libxrandr
  systemd-libs wayland
  # loaded at run time by Wine, used by 10x
  gnutls libpulse vulkan-icd-loader
  # 10x-setup and the launcher
  cabextract python python-fonttools python-pillow systemd unzip
)
makedepends=(
  # as Arch's wine package, without what 10x never uses (network shares,
  # scanners, cameras, smart cards, databases, OpenCL, video capture)
  alsa-lib ffmpeg gnutls gst-plugins-base-libs libcups libpulse libxcomposite
  libxinerama libxxf86vm mesa mingw-w64-gcc perl sdl2 vulkan-headers
  vulkan-icd-loader
  wayland-protocols
)
optdepends=('libnotify: messages from the launcher on the desktop'
            'xdg-desktop-portal: the desktop'"'"'s own file dialogs in 10x')
source=("https://dl.winehq.org/wine/source/11.x/wine-$_winever.tar.xz"
        "winetricks-$_winetricksver::https://raw.githubusercontent.com/Winetricks/winetricks/$_winetricksver/src/winetricks"
        "https://github.com/doitsujin/dxvk/releases/download/v$_dxvkver/dxvk-$_dxvkver.tar.gz"
        "Selawik-$_selawikver.zip::https://github.com/microsoft/Selawik/releases/download/$_selawikver/Selawik_Release.zip"
        "carlito-$_carlitocommit.tar.gz::https://github.com/googlefonts/carlito/archive/$_carlitocommit.tar.gz")
noextract=("Selawik-$_selawikver.zip")
sha256sums=('eac8ca448f9c0087f963026b4dc276d1e2b7fbb64056edc093e59bbb7e56fe28'
            '431f82fc74000e6c864409f1d8fb495d696c03928808e3e8acffc45179312a7b'
            '40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608'
            '3f62c51e05e3b5a1e6241cf92a371f0be2ea1183aa87b30718bbd40832a8d423'
            'ff1fdae06e67136660c7d8135323631c7465c6b4d299d4281bb44eed2165091f')

prepare() {
  cd "wine-$_winever"
  for p in "$startdir"/wine/*.patch; do
    echo "Applying $(basename "$p")"
    patch -p1 -s < "$p"
  done
  mkdir -p "$srcdir/selawik"
  bsdtar -xf "$srcdir/Selawik-$_selawikver.zip" -C "$srcdir/selawik" '*.ttf'
}

build() {
  export CROSSCFLAGS="-O2 -pipe"
  mkdir -p wine-build
  cd wine-build
  "../wine-$_winever/configure" \
    --prefix=/opt/10x-linux/wine \
    --disable-tests \
    --enable-archs=x86_64,i386 \
    --enable-build-id
  make

  cd "$srcdir"
  x86_64-w64-mingw32-gcc -O2 -mwindows -o hold-desktop.exe "$startdir/lib/hold-desktop.c"
  local p=/usr/share/wayland-protocols/stable
  for x in "$p/xdg-shell/xdg-shell.xml" "$p/linux-dmabuf/linux-dmabuf-v1.xml"; do
    wayland-scanner client-header "$x" "$(basename "$x" .xml)-client-protocol.h"
    wayland-scanner private-code "$x" "$(basename "$x" .xml)-protocol.c"
  done
  cc $CPPFLAGS $CFLAGS -I. -o compositor-info "$startdir/lib/compositor-info.c" \
    xdg-shell-protocol.c linux-dmabuf-v1-protocol.c $LDFLAGS -lwayland-client
}

package() {
  cd wine-build
  make DESTDIR="$pkgdir" install

  cd "$srcdir"
  install -Dm755 "$startdir/bin/10x" "$startdir/bin/10x-setup" -t "$pkgdir/usr/bin"
  install -Dm755 compositor-info -t "$pkgdir/usr/lib/10x-linux"
  install -Dm644 "$startdir/data/10x-prewarm.service" -t "$pkgdir/usr/lib/systemd/user"

  local share="$pkgdir/usr/share/10x-linux"
  install -Dm644 hold-desktop.exe "$startdir/data/com.puredevsoftware.Editor10x.desktop" \
    "$startdir"/lib/{titlebar,make-fonts,extract-icon}.py -t "$share"
  install -Dm755 "winetricks-$_winetricksver" "$share/winetricks"
  install -Dm644 "dxvk-$_dxvkver"/x64/*.dll -t "$share/dxvk/x64"
  install -Dm644 "dxvk-$_dxvkver"/x32/*.dll -t "$share/dxvk/x32"
  install -Dm644 selawik/*.ttf -t "$share/fonts/selawik"
  install -Dm644 "carlito-$_carlitocommit"/fonts/ttf/*.ttf -t "$share/fonts/carlito"
}
