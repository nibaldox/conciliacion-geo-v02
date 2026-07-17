# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Python sidecar binary.

Build:
    pyinstaller --clean --noconfirm conciliacion-api.spec

Produces:
    Windows: dist/conciliacion-api.exe
    Linux:   dist/conciliacion-api
"""

import os

block_cipher = None

# Source directories copied into the frozen bundle as-is. PyInstaller's
# static analyzer still needs `hiddenimports` for dynamic imports below.
datas = [
    ("core", "core"),
    ("api", "api"),
    ("web/dist", "web/dist"),
]

# Optional: a seed SQLite DB. The sidecar creates this at runtime if it does
# not exist, but shipping an existing DB lets users keep sessions across
# portable installs.
if os.path.exists("data/conciliacion.db"):
    datas.append(("data/conciliacion.db", "data"))

# Fixtures used by some frozen test runs / diagnostics.
if os.path.exists("tests/conftest.py"):
    datas.append(("tests/conftest.py", "tests"))

# Explicit hiddenimports for modules that PyInstaller's static analysis cannot
# reach (dynamic imports, optional subpackages, lazy C extensions, etc.).
hiddenimports = [
    # API layer
    "api.routers",
    "api.routers.ai",
    "api.routers.blast",
    "api.routers.export",
    "api.routers.meshes",
    "api.routers.process",
    "api.routers.sections",
    "api.routers.settings",
    "api.database",
    "api.schemas",
    # Core domain
    "core",
    "core.ai_v2",
    "core.ai_v2.builder",
    "core.ai_v2.cache",
    "core.ai_v2.config",
    "core.ai_v2.errors",
    "core.ai_v2.models",
    "core.ai_v2.providers",
    "core.ai_v2.providers.base",
    "core.ai_v2.providers.openai_compat",
    "core.ai_v2.providers.registry",
    "core.ai_v2.prompts",
    "core.ai_v2.sanitization",
    "core.ai_v2.service",
    "core.alert_system",
    "core.backbreak_prediction",
    "core.bench_classify",
    "core.bench_hazards",
    "core.blast_achievement",
    "core.blast_advisor",
    "core.blast_attribution",
    "core.blast_correlation",
    "core.blast_metrics",
    "core.blast_model",
    "core.breaklines",
    "core.calculo_tronadura",
    "core.column_utils",
    "core.compliance_status",
    "core.config",
    "core.drill_compliance",
    "core.drill_hardness",
    "core.drill_hardness_processor",
    "core.excel_writer",
    "core.explosive_properties",
    "core.geology",
    "core.geom_utils",
    "core.mesh_handler",
    "core.param_extractor",
    "core.profile_compliance",
    "core.profile_extract",
    "core.profile_simplify",
    "core.report_generator",
    "core.section_cutter",
    "core.stability_analysis",
    # Scientific / third-party deps with lazy extensions
    "scipy.integrate._quadpack",
    "scipy.integrate._odepack",
    "scipy.optimize._minpack",
    "shapely.geometry",
    "trimesh",
    "fast_simplification",
    "pandas",
    "openpyxl",
    "ezdxf",
]

excludes = [
    "tkinter",
    "pytest",
    "matplotlib.tests",
    "IPython",
    "notebook",
    "PyQt5",
    "PySide2",
]

a = Analysis(
    ["entry_api.py"],
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
    name="conciliacion-api",
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
