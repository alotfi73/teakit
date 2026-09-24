# Distributing teakit

teakit ships in three shapes from one source tree. They are the same program:
the same `teakit.app.api` calculation layer behind the same HTML interface. Only
the window differs.

| Shape | For | Needs |
|---|---|---|
| **Windows app** — `teakit-<v>-windows.zip` | Windows users who should never see a command line | nothing |
| **Portable app** — `teakit-<v>-portable.tar.gz` | macOS and Linux users, same audience | Python 3.10+ (macOS and Linux already have it) |
| **Library** — `pip install teakit` | anyone scripting against it with NumPy, pandas, whatever | Python 3.10+ |

---

## 1. The library

This is the plain package. It has **no runtime dependencies**, which is enforced
by CI, so it drops into any environment without argument.

```bash
pip install teakit                 # from PyPI
pip install "teakit[plots]"        # + matplotlib, for ChartSpec.to_matplotlib()
pip install "teakit[desktop]"      # + pywebview, for the native window
pip install git+https://github.com/<you>/teakit    # straight from GitHub
```

Because there are no pinned dependencies, users combine it freely:

```python
import numpy as np
import pandas as pd
import teakit as tea

p = tea.demo("methanol")

# Sweep the discount rate with NumPy and collect with pandas.
rates = np.linspace(0.06, 0.18, 25)
rows = []
for r in rates:
    p.finance.discount_rate = float(r)
    rows.append({"discount_rate": r, "lcop": p.run().unit_cost})
df = pd.DataFrame(rows)

# Report in euros at a rate you control.
p.currency = "EUR"
p.exchange_rate = tea.fetch_rates().rates["EUR"]   # or set it by hand
print(p.run().report())
```

To publish it:

```bash
python -m build
python -m twine upload dist/*
```

Or just push a `v*` tag — [`.github/workflows/release.yml`](../.github/workflows/release.yml)
builds the wheel and the sdist alongside both applications.

---

## 2. The Windows app

A PyInstaller `onedir` build. The user unzips a folder and double-clicks
`teakit.exe`; there is no Python to install and no source on show.

```bash
python -m pip install ".[build]"
python packaging/build_windows.py --zip --clean
# -> dist/teakit-2.0.0-windows/  and  dist/teakit-2.0.0-windows.zip
```

**This must run on Windows.** PyInstaller does not cross-compile.

The folder contains:

```
teakit.exe             the application
teakit-browser.bat     same program, opened in the system browser instead
teakit-debug.bat       same program, with a console so errors are visible
README.txt             what to double-click
LICENSE.txt            the terms, which have to travel with the program
_internal/             the frozen runtime, the data files, the interface
```

Two details in [`packaging/teakit.spec`](../packaging/teakit.spec) are
load-bearing and worth not breaking:

- **`datas` paths.** teakit finds its CSVs and its interface with
  `os.path.dirname(__file__)`, so the bundle has to reproduce the package
  layout — `teakit/data` and `teakit/app/static`. Get this wrong and the app
  starts, then 404s on its own stylesheet. The CI smoke test runs a real study
  through the built exe precisely to catch this.
- **`console=False`.** No console flash on a GUI launch. The cost is that an
  early crash is invisible, which is what `teakit-debug.bat` and the
  `teakit-error.log` written by [`packaging/launcher.py`](../packaging/launcher.py)
  are for.

The launcher prefers the native WebView2 window and falls back to the browser if
the WebView2 runtime is missing, so the app works on a bare Windows install
rather than failing silently.

### Signing

The build is unsigned, so Windows SmartScreen will warn on first run
("Windows protected your PC" → *More info* → *Run anyway*). Removing that
warning needs a code-signing certificate from a CA — an annual cost, tied to a
verified organisation. If you get one, sign in CI with `signtool` after the
PyInstaller step. Until then, say so plainly in the release notes; users trust a
documented warning more than an undocumented one.

---

## 3. The portable app (macOS, Linux)

A folder with the package inside and a double-clickable launcher. The interface
opens in the user's normal browser.

```bash
python packaging/build_portable.py --zip
# -> dist/teakit-2.0.0-portable/  + .zip and .tar.gz
```

Buildable from **any** OS for any OS, because it is not compiled — it uses the
Python already on the machine. That is the trade against a real macOS `.app`,
which would have to be built on a Mac.

```
Launch teakit.command      macOS: double-click this
launch-teakit.sh           Linux
launch-teakit.bat          Windows, in the browser
launch-teakit-window.bat   Windows, in its own window if pywebview is installed
teakit-app.py              what the launchers run
lib/teakit/                the package
LICENSE, README.txt        the terms and the instructions
```

`launch-teakit-window.bat` asks for the native window and falls back to the
browser if pywebview is not installed, so it always starts something.

**Ship the `.tar.gz` for macOS.** `zip` does not preserve the executable bit, and
`Launch teakit.command` has to stay executable to be double-clickable.

macOS also quarantines downloaded launchers. The bundled `README.txt` tells the
user to right-click → Open, or to run
`xattr -d com.apple.quarantine "Launch teakit.command"` once. A real `.app`
signed and notarised with an Apple Developer account (US$99/year) is the only
way to avoid that entirely; it would need to be built on macOS, most simply on a
`macos-latest` CI runner.

---

## Releasing

```bash
# bump the version in src/teakit/__init__.py first
git tag v2.1.0
git push --tags
```

The release workflow builds all four artifacts, smoke-tests both applications by
running a real study through them, and attaches everything to the GitHub
release. Run it from the Actions tab (`workflow_dispatch`) to test the build
without cutting a release.

## Developing

Run the app straight from the checkout, with no build step:

```bash
python run_app.py            # browser
python run_app.py --desktop  # native window
python run_app.py --debug    # log every request; check which teakit is loaded
python run_app.py --check    # print which teakit is loaded, then exit
```

`--check` exists because of a genuinely confusing failure mode: a **non-editable**
install in `site-packages` silently shadows your checkout, and every edit you
make appears to do nothing. If `--check` does not report your working directory,
fix it with:

```bash
pip uninstall -y teakit && pip install -e .
```

Interface files (`src/teakit/app/static/*`) need only a browser reload — the
server sends `Cache-Control: no-store`. Python changes need a restart.
