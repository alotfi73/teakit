"""
teakit.app — The graphical application.
=======================================

A point-and-click interface for people who do not write Python, built entirely
on the standard library: :mod:`http.server` for transport, plain HTML, CSS and
JavaScript for the interface, no framework, no bundler, no CDN. It runs offline
on a laptop with no network, which is where cost estimating often happens.

    $ teakit app

Three layers, deliberately separated:

``api.py``     pure ``dict`` in, ``dict`` out. All the logic, no I/O.
``server.py``  a thin HTTP shim over ``api.dispatch``, plus a static file server.
``static/``    the interface.

Bind is loopback-only by default. It is a local tool, not a service: there is no
authentication, and you should not expose it.
"""

from __future__ import annotations

from . import api

__all__ = ["api", "serve"]


def serve(*a, **kw):
    """Launch the application. See :func:`teakit.app.server.serve`."""
    from .server import serve as _serve
    return _serve(*a, **kw)
