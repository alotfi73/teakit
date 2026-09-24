#!/usr/bin/env python
"""
Build the portable browser application (macOS, Linux, and Windows too).
=======================================================================

Produces ``dist/teakit-<version>-portable/`` — a folder the user unzips and
starts by double-clicking a launcher. The interface opens in their normal web
browser. No pip, no command line, no visible source to deal with.

    python packaging/build_portable.py --zip

Unlike the Windows build this one is **not** a compiled binary: it carries the
Python package and relies on the Python already present on the machine (macOS
and Linux ship one; 3.10 or newer is required). That is the trade for being
buildable from any operating system for any operating system — PyInstaller
cannot cross-compile, so a real macOS .app would have to be built on a Mac.

teakit has no runtime dependencies, so there is nothing to install: the
launcher puts the bundled package on ``sys.path`` and starts the local server.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")

# --- macOS: a .command file is double-clickable from Finder -----------------
COMMAND_SH = """#!/bin/sh
# Double-click this file to start teakit.
# It opens in your web browser. Close this window to stop the program.
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PY="$candidate"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "teakit needs Python 3.10 or newer, and could not find it."
    echo
    echo "On macOS, install it from https://www.python.org/downloads/"
    echo "or with Homebrew:  brew install python"
    echo
    echo "Press Return to close."
    read -r _
    exit 1
fi

exec "$PY" teakit-app.py "$@"
"""

WINDOWS_BAT = """@echo off
rem Double-click to start teakit in your web browser.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo teakit needs Python 3.10 or newer, and could not find it.
  echo Install it from https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)
python teakit-app.py %*
if errorlevel 1 pause
"""

WINDOWS_WINDOW_BAT = """@echo off
rem Double-click to start teakit in its own window instead of a browser tab.
rem Needs pywebview:  python -m pip install pywebview
rem Without it this falls back to the browser, so it always starts something.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo teakit needs Python 3.10 or newer, and could not find it.
  echo Install it from https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)
python teakit-app.py --window %*
if errorlevel 1 pause
"""

APP_PY = '''#!/usr/bin/env python
"""Start teakit from this folder. No installation required."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

if sys.version_info < (3, 10):
    sys.stderr.write(
        "teakit needs Python 3.10 or newer; this is %s.\\n"
        % ".".join(str(n) for n in sys.version_info[:3]))
    raise SystemExit(1)

from teakit.app.server import serve       # noqa: E402

if __name__ == "__main__":
    if "--window" in sys.argv:
        # A native window if pywebview is installed. launch() says how to
        # install it and returns non-zero if it is missing; the browser
        # interface needs nothing, so falling through to it beats exiting
        # with nothing on screen.
        from teakit.app.desktop import launch
        if launch(debug="--debug" in sys.argv) == 0:
            raise SystemExit(0)
        sys.stderr.write("Starting the browser interface instead.\\n")
    serve(host="127.0.0.1", port=8765,
          open_browser="--no-browser" not in sys.argv,
          verbose="--debug" in sys.argv)
'''

README = """teakit — techno-economic analysis
=================================

macOS      double-click  "Launch teakit.command"
Linux      run           ./launch-teakit.sh
Windows    double-click  launch-teakit.bat

The interface opens in your web browser. On Windows, launch-teakit-window.bat
opens it in its own application window instead, if pywebview is installed
(python -m pip install pywebview); without it you get the browser either way. Everything runs on your own machine:
there is no account and no upload. A terminal window stays open while the
program is running — closing it stops the program.

Requires Python 3.10 or newer, which macOS and most Linux systems already have.
Windows users are usually better served by the packaged .exe build, which needs
nothing installed at all.

First run on macOS
------------------
macOS may refuse to open a downloaded launcher. Either right-click the file and
choose Open (then confirm), or run this once in Terminal:

    xattr -d com.apple.quarantine "Launch teakit.command"

Licence
-------
teakit is free for any noncommercial purpose under the PolyForm Noncommercial
License 1.0.0 - see LICENSE in this folder. Commercial use, including paid
consulting or engineering work, needs a separate licence from the author.

Basis of the estimates
----------------------
Capital cost follows DOE/NETL-2002/1169 and NETL-PUB-22580. Cash flow follows
NREL/TP-5100-47764. Costs are computed in US dollars on a US Gulf Coast basis
and escalated by CEPCI; a non-USD reporting currency is a conversion applied to
the finished number, not a local-content estimate.
"""


#: Launchers that have to arrive executable on macOS and Linux.
EXECUTABLE = ("Launch teakit.command", "launch-teakit.sh")


def _tar_gz(folder: str) -> str:
    """
    Pack ``folder`` with the shell launchers marked executable.

    Windows has no executable bit, so ``os.chmod`` there is a no-op and an
    archive built from it ships a ``.command`` that macOS will not open on a
    double-click and a ``.sh`` that Linux refuses to run. Setting the mode in
    the archive rather than on disk makes the bundle identical whichever
    platform builds it. Ownership is zeroed for the same reason, and so the
    builder's username does not travel with the download.
    """
    base = os.path.basename(folder)
    out = f"{folder}.tar.gz"

    def normalise(info: tarfile.TarInfo) -> tarfile.TarInfo:
        rel = info.name[len(base) + 1:]
        info.mode = 0o755 if info.isdir() or rel in EXECUTABLE else 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info

    with tarfile.open(out, "w:gz") as tf:
        tf.add(folder, arcname=base, filter=normalise)
    return out


def _version() -> str:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import teakit
    return teakit.__version__


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", action="store_true")
    args = ap.parse_args(argv)

    version = _version()
    final = os.path.join(DIST, f"teakit-{version}-portable")
    shutil.rmtree(final, ignore_errors=True)
    os.makedirs(os.path.join(final, "lib"), exist_ok=True)

    # The package itself, minus caches and tests.
    shutil.copytree(
        os.path.join(ROOT, "src", "teakit"),
        os.path.join(final, "lib", "teakit"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))

    for name in ("LICENSE", "README.md", "CHANGELOG.md"):
        src = os.path.join(ROOT, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(final, name))

    def write(name, text, newline="\n", mode=None):
        path = os.path.join(final, name)
        with open(path, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(text)
        if mode is not None:
            os.chmod(path, mode)

    write("teakit-app.py", APP_PY)
    write("Launch teakit.command", COMMAND_SH, mode=0o755)
    write("launch-teakit.sh", COMMAND_SH, mode=0o755)
    write("launch-teakit.bat", WINDOWS_BAT, newline="\r\n")
    write("launch-teakit-window.bat", WINDOWS_WINDOW_BAT, newline="\r\n")
    write("README.txt", README, newline="\r\n")

    print(f"Built {final}")
    if args.zip:
        # zip cannot carry an executable bit at all; on macOS the .command
        # launcher must have one, so ship the tar.gz there.
        archive = shutil.make_archive(final, "zip", DIST, os.path.basename(final))
        print(f"Packed {archive}")
        tar = _tar_gz(final)
        print(f"Packed {tar}  (executable launchers — prefer this for macOS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
