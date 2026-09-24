# teakit logo pack

Concept: the classic optimum-design plot. Capital cost falls, operating cost rises, and the total-cost curve bottoms out at the optimum -- where a distillation column (with overhead condenser) sits. Process plant + cost optimisation in one mark.

| File | Use |
|---|---|
| `teakit.ico` | Windows exe icon (16, 24, 32, 48, 64, 128, 256 px). Small sizes use the simplified mark. |
| `favicon.ico` | Browser tab icon for the web app (16, 32, 48 px). |
| `teakit-icon.svg` | Master app icon, scalable. Use in the app header/about page. |
| `teakit-icon-small.svg` | Simplified mark for 16–32 px. |
| `teakit-lockup-light.svg` / `-dark.svg` | Icon + wordmark for light and dark themes. |
| `png/` | Pre-rendered PNGs, 16–1024 px, plus lockups. |

Colours: navy `#0F2F57`, teal `#0B7A75`, amber `#FFC24B`, orange `#FF8A3D`.

## PyInstaller
    pyinstaller --onefile --icon=teakit.ico -n teakit your_entry.py

## Web app (vanilla HTML)
    <link rel="icon" href="/static/favicon.ico" sizes="any">
    <link rel="icon" href="/static/teakit-icon.svg" type="image/svg+xml">
    <img src="/static/teakit-lockup-light.svg" alt="teakit" height="40">

Swap in the `-dark` lockup when the dark theme is active. The lockup text uses
the system font stack (Segoe UI on Windows), so no font files are needed —
consistent with zero dependencies / air-gapped machines.
