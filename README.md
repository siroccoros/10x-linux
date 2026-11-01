# 10x-linux

[10x](https://10xeditor.com) (Windows) on Linux as a native Wayland app: Wine 11.20 patched for 10x, Direct3D through DXVK, per-monitor scaling, the desktop's own file dialogs, clipboard and file drops, Linux programs in 10x's terminal.

Needs Arch Linux (or a derivative), a Wayland desktop, a Vulkan driver, and the installer of 10x 1.0.565 (`10xInstaller.exe` from [puredevsoftware.com](https://www.puredevsoftware.com)).

```sh
git clone https://github.com/nottzaid/10x-linux
cd 10x-linux
makepkg -si
10x-setup ~/Downloads/10xInstaller.exe
```

Then open 10x from your app launcher, or run `10x [files...]`.

Everything is pinned: Wine and the other downloads by sha256 in `PKGBUILD`, your installer and the `10x.exe` it installs in `bin/10x-setup`. The Wine patches are in `wine/`.
