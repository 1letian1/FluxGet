# Build with: uv run --locked -- python -m PyInstaller URLDownloader-portable.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve()
FRONTEND_DIST = ROOT / "frontend" / "dist"
if not (FRONTEND_DIST / "index.html").is_file():
    raise SystemExit("frontend/dist/index.html is missing; run the frontend production build first")

pythonnet_datas, pythonnet_binaries, pythonnet_hiddenimports = collect_all("pythonnet")
clr_loader_datas, clr_loader_binaries, clr_loader_hiddenimports = collect_all("clr_loader")

datas = [
    (str(FRONTEND_DIST), "frontend/dist"),
    *collect_data_files("webview"),
    *pythonnet_datas,
    *clr_loader_datas,
]
binaries = [*pythonnet_binaries, *clr_loader_binaries]
hiddenimports = [
    *collect_submodules("backend"),
    *collect_submodules("desktop"),
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "webview.platforms.mshtml",
    *pythonnet_hiddenimports,
    *clr_loader_hiddenimports,
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="URLDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="URLDownloader-portable",
)
