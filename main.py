"""Desktop application entry point."""

import ctypes
import os

from desktop.lifecycle import run_desktop


_instance_mutex: int | None = None


def _acquire_single_instance() -> bool:
    """Prevent multiple desktop instances from contending for the same database."""
    global _instance_mutex
    if os.name != "nt":
        return True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.SetLastError(0)
    _instance_mutex = kernel32.CreateMutexW(None, True, "Local\\URLDownloader.Desktop")
    if not _instance_mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.WinDLL("user32", use_last_error=True).MessageBoxW(
            None,
            "URL 下载器已经在运行。请切换到已打开的窗口。",
            "URL 下载器",
            0x40,
        )
        return False
    return True


def main() -> None:
    if not _acquire_single_instance():
        return
    run_desktop()


if __name__ == "__main__":
    main()
