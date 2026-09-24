# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the downloadable Windows application.

Build with::

    python packaging/build_windows.py

which is a thin wrapper around ``pyinstaller packaging/teakit.spec``.

Two things in here are load-bearing:

1. ``datas``. teakit finds its CSVs and its interface with
   ``os.path.dirname(__file__)``, so the frozen build has to reproduce the
   package layout exactly — ``teakit/data`` and ``teakit/app/static``. Get the
   destination path wrong and the application starts, then 404s on its own
   stylesheet.
2. ``console=False``. A GUI build must not flash a console window. The trade is
   that a crash before the window opens is silent, which is what
   ``teakit-debug.bat`` in the distribution folder is for — it runs the same
   executable with a console attached.
"""

import importlib.util
import os

# SPECPATH is injected by PyInstaller and points at this file's directory.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))          # noqa: F821
SRC = os.path.join(ROOT, "src")

# The Windows icon — the same file the interface serves as its mark, so the
# two cannot drift apart. PyInstaller fails the build on a missing icon file,
# so a checkout without the artwork falls back to the default instead.
ICON = os.path.join(SRC, "teakit", "app", "static", "teakit.ico")
if not os.path.isfile(ICON):
    print("teakit.spec: teakit.ico not found — building with PyInstaller's "
          "default icon.")
    ICON = None


# pywebview supplies the native window. Only ask PyInstaller to bundle its
# backends if it is actually installed — otherwise every build without the
# `build` extra prints "Hidden import not found" errors for modules that were
# never going to be there. Without it the frozen app still works; launcher.py
# falls back to the browser interface.
_HAS_WEBVIEW = importlib.util.find_spec("webview") is not None
_WEBVIEW_IMPORTS = [
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
] if _HAS_WEBVIEW else []
if not _HAS_WEBVIEW:
    print("teakit.spec: pywebview not installed — building the browser-only "
          "application. Install '.[build]' for the native window.")

a = Analysis(                                                  # noqa: F821
    [os.path.join(SPECPATH, "launcher.py")],                   # noqa: F821
    pathex=[SRC],
    binaries=[],
    datas=[
        # (source on disk, destination inside the bundle)
        (os.path.join(SRC, "teakit", "data"), os.path.join("teakit", "data")),
        (os.path.join(SRC, "teakit", "app", "static"),
         os.path.join("teakit", "app", "static")),
    ],
    hiddenimports=[
        "teakit.app.api",
        "teakit.app.server",
        "teakit.app.desktop",
        "teakit.examples",
        # webview picks its backend at runtime, so the import graph misses it.
        *_WEBVIEW_IMPORTS,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # matplotlib is an optional extra used only by ChartSpec.to_matplotlib().
    # The interface renders SVG itself, so excluding it saves ~40 MB.
    excludes=["matplotlib", "numpy", "pytest", "tkinter", "PIL"],
    noarchive=False,
)

pyz = PYZ(a.pure)                                              # noqa: F821

exe = EXE(                                                     # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="teakit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no console window for the GUI build
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(                                                # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="teakit",
)
