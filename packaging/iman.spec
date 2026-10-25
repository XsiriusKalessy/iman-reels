# PyInstaller: app de escritorio de Imán (macOS .app y Windows).
# Uso: pyinstaller packaging/iman.spec   (con ffmpeg y ffprobe en packaging/bin/)
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parent
version = re.search(r'__version__ = "([^"]+)"', (root / "iman" / "__init__.py").read_text(encoding="utf-8")).group(1)
bin_dir = Path(SPECPATH) / "bin"
exe = ".exe" if sys.platform == "win32" else ""

datas = [
    (str(root / "iman" / "web"), "iman/web"),
    (str(root / "iman" / "assets"), "iman/assets"),
    *collect_data_files("faster_whisper"),  # modelo de detección de voz
    *collect_data_files("mediapipe"),
]
binaries = [
    *collect_dynamic_libs("ctranslate2"),
    *collect_dynamic_libs("mediapipe"),
    *[(str(bin_dir / f"{t}{exe}"), "bin") for t in ("ffmpeg", "ffprobe") if (bin_dir / f"{t}{exe}").exists()],
]
hidden = [*collect_submodules("uvicorn"), *collect_submodules("iman"), "multipart"]

a = Analysis([str(Path(SPECPATH) / "iman_desktop.py")], pathex=[str(root)], datas=datas, binaries=binaries,
             hiddenimports=hidden, excludes=["tkinter", "IPython"])
pyz = PYZ(a.pure)
icon_mac = Path(SPECPATH) / "iman.icns"
icon_win = Path(SPECPATH) / "iman.ico"
# Modo UTF-8: en Windows, Python escribe por defecto en cp1252 y un emoji rompía el montaje.
exe_ = EXE(pyz, a.scripts, [("X utf8", None, "OPTION")], exclude_binaries=True, name="Iman", console=False,
           icon=str(icon_win) if sys.platform == "win32" and icon_win.exists() else None)
coll = COLLECT(exe_, a.binaries, a.datas, name="Iman")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="Imán.app", bundle_identifier="com.imanreels.app",
                 icon=str(icon_mac) if icon_mac.exists() else None,
                 info_plist={"CFBundleShortVersionString": version.split("-")[0], "CFBundleVersion": version.split("-")[0],
                             "LSUIElement": False,
                             "NSHighResolutionCapable": True})
