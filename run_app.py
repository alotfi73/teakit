#!/usr/bin/env python
"""
Debug launcher — run teakit straight from this source tree.
===========================================================

For development. It puts ``src`` on ``sys.path`` itself, so it works whether or
not teakit is pip-installed, and it always runs *this* checkout rather than a
copy that happens to be in site-packages. That distinction matters: a stale
non-editable install in site-packages silently shadows your edits.

    python run_app.py                 browser interface, opens automatically
    python run_app.py --desktop       native window (needs: pip install "teakit[desktop]")
    python run_app.py --debug         log every HTTP request
    python run_app.py --no-browser    just serve; open the URL yourself
    python run_app.py --check         print which teakit is being used, and exit

Edits to ``src/teakit/**`` take effect on restart. Edits to the interface
(``src/teakit/app/static/*``) take effect on a browser reload — the server sends
``Cache-Control: no-store``, so a plain refresh is enough.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")


def _use_local_source() -> None:
    """Make this checkout win over anything installed."""
    if os.path.isdir(SRC):
        sys.path.insert(0, SRC)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="run_app.py",
        description=__doc__.split("\n\n")[1] if "\n\n" in __doc__ else None)
    ap.add_argument("--desktop", action="store_true",
                    help="native window instead of the browser")
    ap.add_argument("--debug", action="store_true",
                    help="log HTTP requests; with --desktop, enable dev tools")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open a browser automatically")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--check", action="store_true",
                    help="report which teakit is in use and exit")
    args = ap.parse_args(argv)

    _use_local_source()

    try:
        import teakit
    except ImportError as exc:
        sys.stderr.write(
            f"Could not import teakit: {exc}\n"
            f"Looked in: {SRC}\n"
            f"If that directory is missing you are not in the project root.\n")
        return 2

    where = os.path.dirname(os.path.abspath(teakit.__file__))
    expected = os.path.join(SRC, "teakit")
    if args.check or args.debug:
        print(f"teakit {teakit.__version__}")
        print(f"  running from : {where}")
        print(f"  this checkout: {expected}")
        print(f"  {'OK — live source' if os.path.normcase(where) == os.path.normcase(expected) else 'WARNING — running an installed copy, not this checkout'}")
        print(f"  python       : {sys.version.split()[0]} ({sys.executable})")
    if args.check:
        return 0

    if args.desktop:
        from teakit.app.desktop import launch
        return launch(debug=args.debug, host=args.host, port=args.port)

    from teakit.app.server import serve
    serve(host=args.host, port=args.port,
          open_browser=not args.no_browser, verbose=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
