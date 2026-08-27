# -*- mode: python ; coding: utf-8 -*-
# Playwright browser runtime is installed by build.ps1 alongside the onedir app.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
hiddenimports = collect_submodules("zhihu_app")
analysis = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root / "src"), str(root / "vendor" / "mediacrawler")],
    binaries=[],
    datas=[(str(root / "vendor" / "mediacrawler" / "libs"), "vendor/mediacrawler/libs")],
    hiddenimports=hiddenimports,
    hookspath=[], runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="知乎采集器", console=False)
coll = COLLECT(exe, analysis.binaries, analysis.datas, name="知乎采集器")
