"""
teakit.app.workspace — where the application puts the files it produces.
========================================================================

Every artefact teakit makes — the HTML report, the Excel workbook, the CSVs,
the saved project — can go to a folder on disk instead of the browser's
download tray. This module owns that folder: where it is, whether it can be
written to, what is already in it, and how to put a new file there.

It is the only part of :mod:`teakit.app` that touches the filesystem outside
``static/``. :mod:`teakit.app.api` stays a pure dict-in/dict-out layer and
delegates the I/O here, so the calculation side is still testable with plain
function calls.

The folder
----------
By default it is ``reports/`` beside the application itself:

* a frozen build      -> ``<folder holding the .exe>/reports``
* a source checkout   -> ``<repository root>/reports``
* an installed wheel  -> ``~/teakit/reports``

which is what "the report folder in the app folder" means in each case. If that
location cannot be written to — a read-only install, Program Files without
elevation — it falls back to ``~/teakit/reports``, because failing to save a
report is worse than saving it somewhere slightly unexpected.

The user's own choice wins over all of it and is remembered between sessions in
``~/.teakit/config.json``.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

__all__ = [
    "config_file", "app_root", "default_dir", "get_dir", "set_dir",
    "reset_dir", "info", "listing", "save", "reveal", "pick_dir",
    "ALLOWED_SUFFIXES",
]

#: Files teakit is willing to write. A report folder is not a general-purpose
#: sink: refusing every other suffix means a bug or a crafted filename cannot
#: drop a ``.bat`` or a ``.dll`` next to the user's estimates.
ALLOWED_SUFFIXES = frozenset({
    ".html", ".htm", ".md", ".txt", ".csv", ".json", ".xlsx", ".svg", ".png",
})

CONFIG_DIR = Path.home() / ".teakit"
CONFIG_NAME = "config.json"
FOLDER_NAME = "reports"


# ============================================================================
# configuration
# ============================================================================
def config_file() -> Path:
    """Path of the small JSON file holding the user's folder choice."""
    return CONFIG_DIR / CONFIG_NAME


def _read_config() -> dict:
    try:
        with open(config_file(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_config(data: dict) -> bool:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(config_file(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return True
    except OSError:
        return False


# ============================================================================
# locating the default folder
# ============================================================================
def app_root() -> Path:
    """
    The folder a user would call "where teakit lives".

    For a frozen build that is the directory holding the executable. For a
    source checkout it is the repository root, found by walking up from this
    file for a ``pyproject.toml``. Otherwise there is no meaningful application
    folder and ``~/teakit`` stands in.
    """
    if getattr(sys, "frozen", False):                      # PyInstaller & co.
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.home() / "teakit"


def _writable(path: Path) -> bool:
    """Can we actually create files here? Tested by doing it, not by guessing."""
    probe = path / f".teakit-write-test-{os.getpid()}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        try:
            probe.unlink()
        except OSError:
            pass
        return False


def default_dir() -> Path:
    """``reports/`` beside the application, or under the home directory."""
    candidate = app_root() / FOLDER_NAME
    if _writable(candidate):
        return candidate
    return Path.home() / "teakit" / FOLDER_NAME


def get_dir() -> Path:
    """The folder in force: the user's choice if they made one, else the default."""
    chosen = _read_config().get("reports_dir")
    if chosen:
        try:
            return Path(chosen).expanduser()
        except (OSError, ValueError):
            pass
    return default_dir()


def set_dir(path: str | os.PathLike) -> Path:
    """
    Point the report folder at ``path``, creating it if need be.

    Raises ``ValueError`` when the path cannot be used, so the interface can
    say why rather than silently writing somewhere else.
    """
    text = str(path).strip().strip('"').strip("'")
    if not text:
        raise ValueError("Give a folder path.")
    target = Path(text).expanduser()
    if target.exists() and not target.is_dir():
        raise ValueError(f"{target} is a file, not a folder.")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"Cannot create {target}: {exc}") from exc
    target = target.resolve()
    if not _writable(target):
        raise ValueError(f"{target} cannot be written to.")
    cfg = _read_config()
    cfg["reports_dir"] = str(target)
    if not _write_config(cfg):
        raise ValueError(
            f"Files will go to {target} for this session, but the choice could "
            f"not be remembered — {config_file()} is not writable.")
    return target


def reset_dir() -> Path:
    """Forget the user's choice and go back to the folder beside the app."""
    cfg = _read_config()
    cfg.pop("reports_dir", None)
    _write_config(cfg)
    return default_dir()


# ============================================================================
# the contents of the folder
# ============================================================================
def listing(limit: int = 200) -> list[dict]:
    """What is in the folder now, newest first."""
    folder = get_dir()
    out: list[dict] = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return out
    for entry in entries:
        try:
            if not entry.is_file() or entry.name.startswith("."):
                continue
            st = entry.stat()
        except OSError:
            continue
        out.append({
            "name": entry.name,
            "bytes": st.st_size,
            "modified": time.strftime("%Y-%m-%d %H:%M",
                                      time.localtime(st.st_mtime)),
            "modified_epoch": st.st_mtime,
            "path": str(entry),
        })
    out.sort(key=lambda r: r["modified_epoch"], reverse=True)
    return out[:limit]


def info() -> dict:
    """Everything the interface needs to describe the folder, in one call."""
    folder = get_dir()
    default = default_dir()
    return {
        "dir": str(folder),
        "default_dir": str(default),
        "is_default": os.path.normcase(str(folder)) == os.path.normcase(str(default)),
        "exists": folder.is_dir(),
        "writable": _writable(folder),
        "app_root": str(app_root()),
        "config_file": str(config_file()),
        "can_pick": _picker_available(),
        "files": listing(),
    }


# ============================================================================
# writing a file
# ============================================================================
def _safe_name(filename: str) -> str:
    """
    Reduce whatever came in to a bare, sane filename inside the report folder.

    Any directory component is dropped rather than honoured: the export layer
    supplies a name, not a destination, and a name that traverses upwards is a
    bug or an attack either way.
    """
    name = os.path.basename(str(filename or "").replace("\\", "/")).strip()
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "-", name).strip(". ")
    if not name:
        raise ValueError("The file has no usable name.")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(
            f"teakit does not write {suffix or 'extensionless'} files to the "
            f"report folder. Allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}.")
    return name


def _unique(folder: Path, name: str) -> Path:
    """``report.html``, then ``report-2.html`` — never silently overwrite."""
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = Path(name).stem, Path(name).suffix
    for n in range(2, 1000):
        candidate = folder / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError(f"Too many files already named like {name}.")


def save(filename: str, content: str, encoding: str = "text",
         overwrite: bool = False) -> dict:
    """
    Write one exported artefact into the report folder.

    ``encoding`` is ``"base64"`` for the binary formats (the workbook) and
    ``"text"`` for everything else — the same contract
    :func:`teakit.app.api.export` returns.
    """
    folder = get_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"Cannot create the report folder {folder}: {exc}") from exc
    name = _safe_name(filename)
    target = folder / name if overwrite else _unique(folder, name)
    try:
        if encoding == "base64":
            with open(target, "wb") as fh:
                fh.write(base64.b64decode(content))
        else:
            with open(target, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
    except OSError as exc:
        raise ValueError(f"Could not write {target}: {exc}") from exc
    except (ValueError, TypeError) as exc:                 # unreadable base64
        raise ValueError(f"The file content was not readable: {exc}") from exc
    return {
        "path": str(target),
        "name": target.name,
        "dir": str(folder),
        "bytes": target.stat().st_size,
        "renamed": target.name != name,
    }


# ============================================================================
# talking to the desktop
# ============================================================================
def reveal(path: str | os.PathLike | None = None) -> str:
    """
    Open the report folder — or the folder holding ``path`` — in the system
    file manager. Returns the path that was opened.
    """
    target = Path(path).expanduser() if path else get_dir()
    if target.is_file():
        folder = target.parent
    else:
        folder = target
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Cannot create {folder}: {exc}") from exc
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(folder))                      # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])        # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(folder)])    # noqa: S603,S607
    except OSError as exc:
        raise ValueError(f"Could not open {folder}: {exc}") from exc
    return str(folder)


# The chooser runs in a child interpreter on purpose. Tk insists on owning the
# main thread, and this process's main thread belongs to the HTTP server — so
# calling tkinter in-process either deadlocks or crashes depending on the
# platform. A subprocess sidesteps the question entirely, and when it is not
# available the interface still lets the path be typed.
_PICKER_SRC = (
    "import sys\n"
    "try:\n"
    "    import tkinter\n"
    "    from tkinter import filedialog\n"
    "except Exception:\n"
    "    sys.exit(3)\n"
    "root = tkinter.Tk()\n"
    "root.withdraw()\n"
    "root.attributes('-topmost', True)\n"
    "try:\n"
    "    path = filedialog.askdirectory(\n"
    "        title='teakit - choose the report folder',\n"
    "        initialdir=(sys.argv[1] if len(sys.argv) > 1 else None),\n"
    "        mustexist=False)\n"
    "finally:\n"
    "    root.destroy()\n"
    "if path:\n"
    "    sys.stdout.write(path)\n"
)


def _picker_available() -> bool:
    try:
        import tkinter  # noqa: F401,PLC0415
    except Exception:                                      # noqa: BLE001
        return False
    return True


def pick_dir(initial: str | os.PathLike | None = None,
             timeout: float = 180.0) -> str | None:
    """
    Show a native folder chooser and return the folder, or ``None`` if the user
    cancelled. Raises ``ValueError`` when no chooser is available.
    """
    if not _picker_available():
        raise ValueError(
            "This Python build has no tkinter, so there is no folder chooser. "
            "Type or paste the path instead.")
    start = str(Path(initial).expanduser()) if initial else str(get_dir())
    kwargs: dict = {}
    if sys.platform.startswith("win"):
        # Otherwise a console window flashes up behind the dialog.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(                             # noqa: S603
            [sys.executable, "-c", _PICKER_SRC, start],
            capture_output=True, text=True, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("The folder chooser timed out.") from exc
    except OSError as exc:
        raise ValueError(f"Could not start the folder chooser: {exc}") from exc
    if proc.returncode == 3:
        raise ValueError(
            "This Python build has no tkinter, so there is no folder chooser. "
            "Type or paste the path instead.")
    picked = (proc.stdout or "").strip()
    return picked or None
