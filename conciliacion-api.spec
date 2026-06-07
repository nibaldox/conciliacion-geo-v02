# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Python sidecar binary.

Build:
    pyinstaller --clean --noconfirm conciliacion-api.spec

Produces:
    Windows: dist/conciliacion-api.exe
    Linux:   dist/conciliacion-api
"""

block_cipher = None

datas = [
    ('web/dist', 'web/dist'),
]

hiddenimports = [
    'scipy.integrate._quadpack',
    'scipy.integrate._odepack',
    'scipy.optimize._minpack',
    'shapely.geometry',
    'trimesh',
    'pandas',
    'openpyxl',
    'ezdxf',
]

excludes = [
    'tkinter',
    'pytest',
    'matplotlib.tests',
    'IPython',
    'notebook',
    'PyQt5',
    'PySide2',
]

a = Analysis(
    ['entry_api.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='conciliacion-api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
