"""
Entry point for the frozen Windows application.

Kept separate from :mod:`teakit.app.desktop` because a frozen build has needs a
source checkout does not: it must survive a missing WebView2 runtime, and it
must not die silently when something goes wrong before a window exists.

The order of preference is:

1. the native window (pywebview over WebView2), which is what a Windows user
   double-clicking ``teakit.exe`` expects;
2. failing that, the browser interface — identical program, system browser —
   so a machine without the WebView2 runtime still works rather than doing
   nothing at all.
"""

from __future__ import annotations

import os
import sys
import traceback

# Frozen builds get no console, so an early traceback would vanish. Keep one on
# disk next to the executable instead.
LOG_NAME = "teakit-error.log"


def _log_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _report(exc: BaseException) -> None:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        with open(os.path.join(_log_dir(), LOG_NAME), "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass
    sys.stderr.write(text)
    # A GUI build has no console, so say something the user can actually see.
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "teakit could not start.\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            f"Details were written to {LOG_NAME} next to the program.",
            "teakit", 0x10)
    except Exception:                                          # noqa: BLE001
        pass


def main() -> int:
    try:
        from teakit.app import desktop, server
    except Exception as exc:                                   # noqa: BLE001
        _report(exc)
        return 1

    want_browser = "--browser" in sys.argv
    debug = "--debug" in sys.argv

    if not want_browser:
        try:
            import webview  # noqa: F401
        except ImportError:
            want_browser = True

    try:
        if want_browser:
            server.serve(host="127.0.0.1", port=8765,
                         open_browser=True, verbose=debug)
            return 0
        return desktop.launch(debug=debug)
    except Exception as exc:                                   # noqa: BLE001
        _report(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
