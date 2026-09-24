#!/usr/bin/env python
"""
Build the downloadable Windows application.
===========================================

Produces ``dist/teakit-<version>-windows/`` — a folder the user unzips and runs
by double-clicking ``teakit.exe``. No Python, no pip, no command line, no
visible source.

    python -m pip install ".[build]"
    python packaging/build_windows.py

Must be run **on Windows**: PyInstaller does not cross-compile, so a Windows
executable needs a Windows machine (or a windows runner in CI — see
``.github/workflows/release.yml``).

Add ``--zip`` to also produce the archive that goes on a GitHub release.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")

README = """teakit — techno-economic analysis
=================================

Double-click  teakit.exe  to start.

The program opens its own window. Everything runs on your own machine: there is
no account, no upload, and no network connection needed except for the optional
"Update" button on the exchange rate, which fetches the European Central Bank
reference rate for the day.

If the window does not appear
-----------------------------
Run  teakit-browser.bat  instead. That serves the identical program and opens it
in your normal web browser, which avoids needing the Microsoft WebView2 runtime.

If something goes wrong
-----------------------
Run  teakit-debug.bat . It runs the same program with a console window attached
so you can see the error, and writes teakit-error.log next to the program.

Licence
-------
teakit is free for any noncommercial purpose under the PolyForm Noncommercial
License 1.0.0 - see LICENSE.txt in this folder. Commercial use, including paid
consulting or engineering work, needs a separate licence from the author.

Basis of the estimates
----------------------
Capital cost follows DOE/NETL-2002/1169 and NETL-PUB-22580. Cash flow follows
NREL/TP-5100-47764. Costs are computed in US dollars on a US Gulf Coast basis
and escalated by CEPCI; a non-USD reporting currency is a conversion applied to
the finished number, not a local-content estimate.
"""

BROWSER_BAT = """@echo off
rem The same program, opened in your web browser instead of its own window.
start "" "%~dp0teakit.exe" --browser
"""

DEBUG_BAT = """@echo off
rem Runs teakit with a console attached so errors are visible.
echo Starting teakit in debug mode. Close this window to stop it.
echo.
"%~dp0teakit.exe" --debug --browser
echo.
echo teakit exited with code %ERRORLEVEL%.
pause
"""


def _version() -> str:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import teakit
    return teakit.__version__


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", action="store_true",
                    help="also produce a .zip for a GitHub release")
    ap.add_argument("--clean", action="store_true",
                    help="remove build/ and dist/ first")
    args = ap.parse_args(argv)

    if sys.platform != "win32":
        sys.stderr.write(
            "This builds a Windows .exe and PyInstaller does not cross-compile,\n"
            "so it has to run on Windows. For macOS and Linux users, ship the\n"
            "browser application instead:  python packaging/build_portable.py\n")
        return 2

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.stderr.write('PyInstaller is missing. Run:\n'
                         '  python -m pip install ".[build]"\n')
        return 2

    if args.clean:
        for d in (BUILD, DIST):
            shutil.rmtree(d, ignore_errors=True)

    version = _version()
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm",
           "--distpath", DIST, "--workpath", BUILD,
           os.path.join(HERE, "teakit.spec")]
    print("  " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    staged = os.path.join(DIST, "teakit")
    final = os.path.join(DIST, f"teakit-{version}-windows")
    if not os.path.isdir(staged):
        sys.stderr.write(f"expected PyInstaller output at {staged}\n")
        return 1
    shutil.rmtree(final, ignore_errors=True)
    os.rename(staged, final)

    for name, text in (("README.txt", README),
                       ("teakit-browser.bat", BROWSER_BAT),
                       ("teakit-debug.bat", DEBUG_BAT)):
        with open(os.path.join(final, name), "w", encoding="utf-8",
                  newline="\r\n") as fh:
            fh.write(text)

    # PolyForm requires that whoever gets a copy also gets the terms, and
    # .txt is what opens on a double-click on Windows.
    shutil.copyfile(os.path.join(ROOT, "LICENSE"),
                    os.path.join(final, "LICENSE.txt"))

    print(f"\nBuilt {final}")
    if args.zip:
        archive = shutil.make_archive(final, "zip", DIST,
                                      os.path.basename(final))
        print(f"Packed {archive}")
    print("\nSanity check before publishing: unzip somewhere else, double-click\n"
          "teakit.exe, load a demo project and run it. A missing data file only\n"
          "shows up at runtime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
