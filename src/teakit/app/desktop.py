"""
teakit.app.desktop — the same interface, in a native window.
============================================================

The Windows application and the browser application are the *same* program.
This module only swaps the window: it starts the ordinary
:mod:`teakit.app.server` on loopback and points an embedded WebView2 (Windows),
WebKit (macOS) or WebKitGTK (Linux) view at it, instead of the system browser.
Nothing about the calculation, the interface or the API changes, so a bug fixed
in one is fixed in both.

Run it any of these ways::

    teakit-desktop                  # console script, after pip install
    teakit app --desktop            # via the main CLI
    python -m teakit.app.desktop    # module form
    python src/teakit/app/desktop.py    # straight at the file, for debugging

The last one is why this file has the ``sys.path`` shim at the bottom: running a
file *inside* a package as a top-level script leaves Python with no parent
package, and ``from . import server`` then fails with "attempted relative import
with no known parent package". The shim puts ``src`` on the path and re-enters
through the package so the relative imports resolve.

Requires the ``desktop`` extra::

    pip install "teakit[desktop]"
"""

from __future__ import annotations

import os
import sys
import threading

__all__ = ["main", "launch"]

WINDOW_TITLE = "teakit — techno-economic analysis"

# Windows groups taskbar buttons by AppUserModelID. Without one the button
# inherits the identity of whatever started the process — python.exe, from a
# source checkout — and shows its icon instead of ours.
APP_ID = "teakit.desktop"

# Below this the rail, the sheet and the title block stop fitting side by side.
MIN_SIZE = (1024, 680)


def _claim_taskbar_identity(app_id: str = APP_ID) -> None:
    """Windows only, and cosmetic: never let it stop the window opening."""
    if sys.platform != "win32":
        return
    try:
        import ctypes  # noqa: PLC0415
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:  # noqa: BLE001
        pass


def _window_geometry(width: int, height: int) -> tuple[int, int, int, int]:
    """
    Clamp a window to the work area and centre it in it: ``x, y, width, height``.

    pywebview sizes in logical (96-dpi) units, so the work area has to be scaled
    before the two are compared — on a 200% display the default would otherwise
    open taller than the screen. Position matters as much as size, because
    pywebview offsets from the corner rather than centring.

    Only the opening geometry. The window stays resizable.
    """
    if sys.platform != "win32":
        return 0, 0, width, height
    try:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415
        user32 = ctypes.windll.user32
        area = wintypes.RECT()
        # SPI_GETWORKAREA: the desktop minus the taskbar.
        if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
            return 0, 0, width, height
        try:
            scale = (user32.GetDpiForSystem() or 96) / 96   # Windows 10 1607+
        except AttributeError:
            scale = 1.0
        left, top = int(area.left / scale), int(area.top / scale)
        avail_w = int((area.right - area.left) / scale)
        avail_h = int((area.bottom - area.top) / scale)
        width = max(MIN_SIZE[0], min(width, avail_w - 24))
        height = max(MIN_SIZE[1], min(height, avail_h - 24))
        return (left + max(0, (avail_w - width) // 2),
                top + max(0, (avail_h - height) // 2),
                width, height)
    except Exception:  # noqa: BLE001
        return 0, 0, width, height


def launch(width: int = 1440, height: int = 920, debug: bool = False,
           host: str = "127.0.0.1", port: int = 8765) -> int:
    """
    Open the interface in a native window and block until it is closed.

    ``debug=True`` enables the WebView developer tools (right-click → Inspect),
    which is the only practical way to debug the JavaScript side in a native
    window.
    """
    try:
        import webview  # noqa: PLC0415
    except ImportError:
        sys.stderr.write(
            "The desktop window needs pywebview, which is not installed.\n"
            "  pip install \"teakit[desktop]\"\n"
            "Or use the browser interface instead, which needs nothing extra:\n"
            "  teakit app\n")
        return 2

    from .. import __version__  # noqa: PLC0415
    from . import server  # noqa: PLC0415

    _claim_taskbar_identity()

    port = server._free_port(host, port)
    srv = server.make_server(host, port, verbose=debug)
    thread = threading.Thread(target=srv.serve_forever, daemon=True,
                              name="teakit-http")
    thread.start()
    if debug:
        print(f"teakit {__version__} — desktop window on http://{host}:{port}/")
    try:
        # Fitted to the screen, then left alone: the user resizes from here.
        x, y, w, h = _window_geometry(width, height)
        webview.create_window(WINDOW_TITLE, f"http://{host}:{port}/",
                              x=x, y=y, width=w, height=h,
                              min_size=MIN_SIZE, text_select=True)
        # Title bar, taskbar and Alt-Tab. Without this pywebview falls back to
        # the icon of whatever launched it — python.exe from a source
        # checkout, which is not this program. The frozen build is stamped
        # with the same file (see packaging/teakit.spec).
        icon = os.path.join(server.STATIC_DIR, "teakit.ico")
        webview.start(debug=debug,
                      icon=icon if os.path.isfile(icon) else None)
    finally:
        srv.shutdown()
        srv.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point. ``teakit-desktop --debug`` for dev tools."""
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(
        prog="teakit-desktop",
        description="teakit in a native desktop window.")
    ap.add_argument("--debug", action="store_true",
                    help="enable the WebView developer tools and HTTP logging")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=920)
    ap.add_argument("--port", type=int, default=8765,
                    help="starting port; the first free one at or after it is used")
    args = ap.parse_args(argv)
    return launch(width=args.width, height=args.height, debug=args.debug,
                  port=args.port)


if __name__ == "__main__":  # pragma: no cover
    if __package__ in (None, ""):
        # Started as a plain file, e.g. `python desktop.py`. There is no parent
        # package, so the relative imports above cannot resolve. Put the source
        # root on sys.path and re-enter through the proper module name.
        _here = os.path.dirname(os.path.abspath(__file__))
        _src = os.path.abspath(os.path.join(_here, "..", ".."))
        if _src not in sys.path:
            sys.path.insert(0, _src)
        from teakit.app.desktop import main as _main  # noqa: PLC0415
        sys.exit(_main())
    sys.exit(main())
