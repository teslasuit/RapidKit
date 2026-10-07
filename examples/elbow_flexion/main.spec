# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Elbow Flexion FES example — single-file build.

Build from the repo root (or this folder) with::

    pyinstaller examples/elbow_flexion/main.spec --noconfirm --clean

Notes
-----
* Onefile build: binaries, datas and the pure-Python zip are inlined in the
  ``EXE`` stage, so ``COLLECT`` is intentionally omitted.
* The entry point ``main.py`` spawns a second process via
  ``multiprocessing`` and re-imports ``examples.elbow_flexion.backend_mainloop``
  in that subprocess, so both the example package *and* every framework
  package must be embedded as hidden imports (not just the ones pulled in
  by the main-process GUI).
* ``teslasuit_api.dll`` is resolved at runtime via the
  ``TESLASUIT_API_LIB_PATH`` env var / system ``PATH`` — it is **not**
  bundled.  The end-user machine must still have the Teslasuit runtime
  installed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# ─── Paths ──────────────────────────────────────────────────────────────────
# SPECPATH is injected by PyInstaller and points to this file's directory.
SPEC_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_DIR.parents[1]  # …/rapidkit

# Make absolute imports like ``from rapidkit…`` and
# ``from examples.elbow_flexion…`` resolvable during Analysis *and*
# at runtime when the frozen bootloader builds ``sys.path``.
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Hidden imports (framework + example + 3rd-party) ───────────────────────
hiddenimports: list[str] = []

# Every module under the in-repo framework and the example package.
for pkg in (
    "rapidkit",
    "teslasuit_sdk",
    "examples.elbow_flexion",
):
    hiddenimports += collect_submodules(pkg)

# 3rd-party libs that use dynamic / lazy imports which PyInstaller's
# static analysis can miss.
for pkg in (
    "PyQt5",
    "pyqtgraph",
    "pylsl",
    "numpy",
):
    hiddenimports += collect_submodules(pkg)

# multiprocessing spawns a fresh interpreter on Windows; make sure its
# helper modules survive the freeze.
hiddenimports += [
    "multiprocessing",
    "multiprocessing.spawn",
    "multiprocessing.popen_spawn_win32",
    "multiprocessing.resource_tracker",
    "multiprocessing.synchronize",
    "multiprocessing.heap",
]

# ─── Data files (JSON configs, Qt/pyqtgraph resources, etc.) ────────────────
datas: list[tuple[str, str]] = []

# Ship ``rapidkit/config/*.json`` (muscle map lives here).
datas += collect_data_files("rapidkit", includes=["config/*.json",
                                                        "config/*"])

# Pull any package data pyqtgraph / pylsl carry alongside their code.
datas += collect_data_files("pyqtgraph")
datas += collect_data_files("pylsl")

# ─── Dynamic libraries ──────────────────────────────────────────────────────
binaries: list[tuple[str, str]] = []

# pylsl ships ``liblsl.dll`` next to its Python files — bundle it so the
# frozen app works on machines without a separate LSL install.
binaries += collect_dynamic_libs("pylsl")

# ─── Analysis / PYZ / EXE ───────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_ROOT), str(SPEC_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim obvious dead weight; none of these are imported by the
        # example or the framework.
        "tkinter",
        "PySide2",
        "PySide6",
        "PyQt6",
        "IPython",
        "jupyter",
        "pytest",
        "sphinx",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ElbowFlexionFES",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # Qt plugins can break when UPX-compressed.
        "Qt5*.dll",
        "vcruntime140*.dll",
        "msvcp140*.dll",
    ],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
