# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["gui_app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kakeibo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Kakeibo",
)

app = BUNDLE(
    collection,
    name="かんたん家計簿.app",
    # Pillowが高解像度PNGをmacOS用アイコンへ自動変換します。
    icon="assets/app_icon.png",
    bundle_identifier="jp.kakeibo.desktop",
    info_plist={
        "CFBundleDisplayName": "かんたん家計簿",
        "CFBundleName": "かんたん家計簿",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
