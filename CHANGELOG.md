# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/).
Versioning is [semantic](https://semver.org/).

## [Unreleased]

### Added

**An Excel workbook export** (`teakit.excel`, `teakit.xlsx`) — the whole
estimate as a sectioned, colour-coded workbook: Cover, Basis, Equipment,
Capital, Operating cost, Products, Cash flow, Results and Method, each on its
own coloured tab, with native Excel charts and data bars.

The parts of it that are arithmetic are **live formulas**, so changing an
equipment size, a contingency or a utility price in Excel moves the estimate.
The parts that are not — the DCF price solve, the MACRS schedule, the per-item
distributive installation build-up — are marked as stamped values rather than
faked, because a workbook that quietly disagrees with the engine is worse than
one that says where it stops. Three cell conventions, stated on the cover:
amber is an input, plain is computed, grey italic is stamped.

`teakit.xlsx` is a small OOXML writer built on `zipfile` alone, so the zero
runtime dependencies are unchanged. Available from the interface, from
`api.export(format="xlsx")` (base64-encoded, since the API is JSON), and from
the CLI as `teakit run project.json --format xlsx -o estimate.xlsx`.

**A method appendix** (`teakit.methods.explain`) — the equations actually used
on a run, with that run's own numbers substituted, the symbols tabulated, and
the arithmetic step by step, so a reviewer can reproduce the result with a
calculator. Only the methods selected are set out in full; the alternatives are
named so it is clear a choice was made. It appears at the end of the HTML and
Markdown reports, on the workbook's Method sheet, in the new Info section, and
through `api.explain`.

**Explanations on every option** (`teakit.methods.OPTION_HELP`) — one sentence
per dropdown choice, owned by the library so the interface, the reports and the
workbook cannot drift apart. The interface hangs them on each `<option>` as a
tooltip and prints the selected one under the control. Dropdown labels are
capitalised and spelled out the way a report would write them, with acronyms,
unit symbols and identifiers left alone, and the DOE/NETL distributive-factor
keys turned into sentences (`gas_gt400F_gt150psig` became
`Gas, above 400 °F and 150 psig`).

**A fourth costing method, `crf`** — annualised capital over production:

    LC = (CRF x TOC + fixed O&M + variable O&M - byproducts) / annual production

with `CRF = i(1+i)^N / [(1+i)^N - 1]` at the discount rate over the plant life.
It is the textbook annuity form and the NREL ATB convention, and it fills the
gap between `simple` (no cost of capital at all) and `fcr` (tax-aware, charged
against as-spent capital): it charges the cost of capital but no tax, against
TOC in constant dollars. On the methanol demo the four methods give 254.76,
257.34, 241.71 and 197.83 — quote which one you used. The method appendix sets
out the equations with the run's own numbers, as it does for the others.

**Replacement parts** (`teakit.project.EquipmentConsumable`) — the things an
item wears out and has swapped: electrodes in a plasma reactor, a catalyst
charge, membranes, filter elements, a mill liner. They are neither a utility
nor capital, and had nowhere to go.

Each carries a quantity, a unit cost and a replacement interval in years, and
is annualised over that interval — a set of six electrodes at $42,000 each on
an 18-month cycle is $168,000/yr before the capacity factor. Spares are
excluded from the count, as with utilities: a spare is not running and is not
wearing anything out. `scales_with_rate` chooses whether the schedule is driven
by run time (the default: a plant at 80% replaces 80% as often) or by the
calendar. They appear on the item, in the operating cost under that item's tag,
in a **Replacement parts** section of both reports, in the workbook, and in the
equipment CSV.

**Equipment can be categorised by type, not only by plant section.** A new
`category` on each item, defaulting to the family of its catalogue key — the
three blowers in a list are all "blower" without anyone typing anything — with
a `type_shares` rollup, a **Equipment cost by type** chart in the standard set
and in the chart builder, and the category on every equipment row and CSV.
Plant section answers where the money went; this answers what it was spent on.

**One price per utility, for the whole study**
(`teakit.project.Project.utility_price_book`). A tariff is a property of the
project, not of the machine drawing on it. Prices now resolve in one order —
a price set for the study, then the plant-level line of that name, then the
shipped catalogue — and every equipment line is charged through it, so a change
of tariff moves every item at once. Editing the price in any of the three
places it is shown moves all of them.

**Standard units per utility** (`teakit.defaults.UNIT_SETS`). Electrical energy
offers Wh/kWh/MWh/GWh, fuel MMBtu/GJ/MJ/therm, mass tonne/kg/lb, volume
m3/L/gal/ft3, normalised gas volume Nm3/scf — with "Other…" for anything else
and whatever a loaded project already holds kept at the top, so no file loses
its unit. A stream still stores a *quantity* unit because that is what a price
is per; what the interface now also prints is the rate as an engineer says it,
so 5,200 kWh per operating hour is shown as **5,200 kW**.

**Generation as well as consumption.** A negative rate on a utility line is a
turbine, an expander or a waste-heat set putting power back: it nets against
everything else drawing on that utility, is marked *generates* in the roll-up,
and shows as a credit. (An export you are actually paid for is still better
modelled as a byproduct on the Products panel, where it carries its own price —
the option help says so.)

**An equipment item now carries what it is and what it consumes**
(`teakit.project.EquipmentParameter`, `teakit.project.EquipmentUtility`). One
object per unit operation holds its name, its cost model, the size that drives
that cost, any number of named process parameters — duty, inlet flow,
temperature, pressure, area — and the utilities it draws when it runs.

Consumption is entered on the item that incurs it and priced into the
operating cost from there, tagged with that item, so the electricity bill can
be traced to the machines that cause it instead of arriving as one
unattributable plant total. The Operating cost panel shows the roll-up grouped
by utility, each line linking back to its item, with plant-level lines kept
separately underneath for what genuinely does not belong to one machine.

**Both panels edit the same lines.** The roll-up is not a read-only view: a
rate, price, unit, basis or flag changed there is changed on the item, because
both are rendered against the same objects. Only the utility's *name* is fixed
to the equipment panel, since it decides the unit, the price and the category
together and those three belong side by side. Neither view repaints the other
while you type — the cost cells carry a key and are updated in place — so the
caret stays where you put it.

Three details that are decisions, not defaults:

* **Spares never consume.** A 2+1 pump set is three pumps in the capital and
  two pumps drawing power. `quantity` multiplies a per-unit rate; `spare` does
  not.
* **Prices come from the utility catalogue by name**, so a change of tariff
  moves every item at once and no price is typed twice. A price entered on a
  line overrides it for that line alone.
* **A rate with no price is reported, not silently zero.** The run warns, the
  panel marks the line, and the estimate says so rather than quietly costing
  it at nothing.

Everything downstream follows: the HTML and Markdown reports gain an equipment
schedule with names and parameters and a utility-attribution table; the Excel
workbook's variable-cost block includes the derived lines — it was previously
short by the whole equipment utility bill and disagreed with the estimate it
came from; `equipment.csv` gains the name, the parameters and the item's annual
consumption; and a new **Utilities CSV** export gives one priced row per line.
Parameters and utility rates are addressable by dotted path
(`equipment.K-101.duty.value`, `equipment.K-101.electricity.rate`) so
sensitivity can sweep them like anything else.

Projects saved before this load unchanged — the two lists are simply absent —
and the three demo studies now use it. The methanol demo's answer is
unchanged to four decimals: its 8,500 kW, 2,400 m³/h and 90 m³/h are the same
totals, attributed rather than lumped.

**A report folder** (`teakit.app.workspace`) — exports go to a folder on disk
that the application names on screen, rather than only to the browser's
download tray. It is `reports/` beside the application: next to `teakit.exe` in
a packaged build, at the repository root in a checkout, and under `~/teakit` for
an installed wheel, falling back to the home directory when the first choice is
read-only. **Report folder & files** in the title block shows the path, changes
it — typed, or through a native folder chooser — opens it in the file manager,
and lists what is already in it. The choice is remembered in
`~/.teakit/config.json`.

Handing files to the browser instead is still available, now as a deliberate
setting rather than as the only behaviour, and a folder that has been deleted or
filled up falls back to a download rather than losing the file. Names never
collide: a second `report.html` is written as `report-2.html`. The folder takes
only the suffixes teakit produces, and a filename is reduced to its base name
before use, so nothing can be written outside it.

**A Guide & method section** in the interface — a manual covering what the
application computes and in what order, how accurate it is, the capital ladder,
the allocation rules, and the one basis rule that matters; a searchable
reference of every option; and the current run's calculations.

**Currency conversion** (`teakit.currency`) — the cost engine still works in USD
throughout, but a result can now be reported in any of the ten labelled
currencies. `ProjectResult.convert_currency()` restates every monetary field and
deliberately leaves every dimensionless one alone: ratios, physical output,
headcount, IRR, the TASC/TOC factor and the fixed-charge rate do not move.
`Project.exchange_rate` and `.exchange_rate_source` are stored in the project
file, so an old study reproduces on the rate it was quoted at.

Three ways to get a rate, in the order you should prefer them: one you set for
the project; `fetch_rates()`, which pulls the ECB reference rates published
through frankfurter.app; or the bundled offline table. The fetch fails closed
and never raises, results are cached per user, and teakit warns when the rate in
use is more than a month old. The rate and its provenance appear in the basis of
every report.

**A native desktop window** (`teakit.app.desktop`) — `teakit app --desktop`,
`teakit-desktop`, or `python -m teakit.app.desktop`. Same server, same
interface, embedded in a WebView instead of the system browser. Needs the new
`desktop` extra; without it the browser interface is unaffected.

**Packaging for non-technical users** — `packaging/build_windows.py` produces a
PyInstaller folder whose `teakit.exe` needs nothing installed;
`packaging/build_portable.py` produces a browser bundle with double-clickable
launchers for macOS, Linux and Windows. A release workflow builds both, runs a
real study through each before publishing, and attaches them to the GitHub
release alongside the wheel. See [docs/distribution.md](docs/distribution.md).

**`run_app.py`** — runs the app straight from a checkout with no install.
`--check` reports which copy of teakit is actually being imported, which is the
fastest way to diagnose a stale non-editable install shadowing your edits.

**The teakit mark** — the optimum-design curve with a column sitting at its
minimum. It appears beside the wordmark on the step rail (and alone when the
rail is collapsed), as the browser tab icon, on the native window's title bar
and taskbar button, and stamped into `teakit.exe`. The artwork lives in
`teakit-logo/`; the files the program actually uses are copies in
`src/teakit/app/static/`, so every way of shipping it — wheel, portable bundle,
frozen build — carries them without a special case, and `teakit.spec` stamps
the executable from that same `teakit.ico`. The desktop window declares an
explicit Windows AppUserModelID, without which the taskbar button inherits the
identity of whatever launched the process and shows the Python icon even though
the title bar is correct.

**Author, licence and citation, in the application** — `teakit.CITATION` and
`teakit.citation()` hold the references; the Info section prints them under
"Credits and citation", and both report formats carry them in the footer. The
HTML report states the DOI as `doi:10.1016/...` rather than a link, because that
report has to stay entirely self-contained. `CITATION.cff` names the article as
the preferred citation.

### Changed

**A native-window launcher in the portable bundle.**
`launch-teakit-window.bat` runs the interface in its own application window
rather than a browser tab, if `pywebview` is installed; without it, it falls
back to the browser, so it always starts something.

**The desktop window opens fitted to the screen.** It was created at a fixed
1440x920, which is larger than the desktop on a 2880x1800 panel at 200% scaling
— pywebview sizes in logical units, so that display is a 1440x900 desktop and
the window opened with its bottom edge, and the Run button, behind the taskbar.
It is now clamped to the work area and centred in it, and stays resizable from
there. `--width` and `--height` still work; they are clamped the same way,
because nothing is gained by opening larger than the screen.

**Relicensed from MIT to the
[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).**
teakit stays free for any noncommercial purpose — academic research, teaching,
personal study, public-sector work — including the right to change it and pass
it on. Commercial use is no longer granted by the licence and needs separate
terms from the author. This is a source-available licence, not an open-source
one, and `pyproject.toml` now classifies it that way rather than claiming OSI
approval. The Windows build ships `LICENSE.txt` alongside the executable,
because PolyForm requires that whoever receives a copy also receives the terms;
the portable build already did.

**The equipment list is now editable item by item.** Every row opens into a
parameter panel showing what each parameter is, its unit, the catalogue default
beside your value, and a reset — per parameter and for the whole item. It also
shows the correlation's fitted range, fit quality and source, warns when a size
is outside that range, and spells out how that item's cost was reached. Items
can be duplicated. A user-defined correlation now takes its scaled-parameter
unit from you, and that unit is carried into the report and the workbook.

**The parameter explanations moved out of the rows and into one guide.** Every
open row used to print the same paragraph under every field, so a list of ten
items repeated the same forty sentences down the page. There is now a
**Parameter guide** button on the equipment toolbar and inside every open row,
opening one reference covering how an item can be priced and what each parameter
does; each control keeps its own sentence as a tooltip. The sentences still come
from `teakit.methods.OPTION_HELP`, so nothing has been duplicated.

A summary table under the list rolls the equipment up by plant section and by
cost basis. It keeps purchased cost and already-installed cost in separate
columns, because they enter the capital cascade at different rungs and adding
them together silently inflates BEC by the installation factor.

### Fixed

**The portable `.tar.gz` now ships executable launchers.** Windows has no
executable bit, so `os.chmod` there is a no-op and a bundle built on Windows
shipped a `Launch teakit.command` macOS would not open on a double-click and a
`launch-teakit.sh` Linux refused to run. The mode is now set in the archive
rather than on disk, so the bundle is the same whichever platform builds it.
Ownership is zeroed at the same time, so the builder's username no longer
travels with the download.

- Switching currency relabelled the interface but left every figure in USD,
  including the equipment costs. Currency now re-runs the estimate.
- The equipment table crushed its columns until the Cost column was pushed off
  the right-hand edge, and long correlation names were cut without any way to
  read them. The table now uses a fixed column budget so every field fits, and
  clipped text carries a tooltip.
- Table figures were abbreviated (`12.7M`) with no way to see the exact value.
  Tables now show full grouped numbers, with the exact figure on hover.
- Number-input spinners hid the digits in narrow table cells.
- `python src/teakit/app/desktop.py` failed with "attempted relative import with
  no known parent package". It now works run directly, as a module, or through
  either console script.
- Input price columns are labelled `USD/unit` rather than `$/unit`, so they
  cannot be mistaken for the reporting currency.
- **"Reset all parameters to default" never became active.** It read a narrower
  list of parameters than the panel could edit, and it was rendered once when
  the row opened while every later edit repainted only the row above it. One
  function now decides what counts as changed — for the button, the row's
  "edited" badge and the pill beside each parameter — and the button is kept in
  step as you type. It also resets quantity, spares and material, which it
  previously left alone despite its label.
- **Annual costs on the Operating cost panel did not follow the operating
  hours or the capacity factor.** They were read out of the last run, so
  changing either left every figure on the panel stale until something
  unrelated forced a repaint — toggling a checkbox would do it, which is how
  the staleness was noticed. Every annual figure is now computed in the browser
  from the same formula the engine uses, and moves the moment the hours, the
  capacity factor or a price moves.
- **The equipment's utility prices ignored the project's own.** An equipment
  line was priced from the shipped catalogue, so setting electricity to
  $0.20/kWh on the Operating cost panel left every compressor and pump still
  charged the catalogue's $0.081 — two prices for one utility inside one
  estimate. See the price book above.
- **Exported files carry a date and time stamp** —
  `plant-report-20260829-1432.html`. An estimate gets revised, and two exports
  an hour apart are two different answers; the stamp orders them in the folder
  instead of leaving the second to become a silent "-2".
- **An operating-time preset silently reset the capacity factor to 100%.**
  Every preset carries `capacity_factor = 1.00`, and applying one assigned it
  along with the hours — so picking "Continuous, 7,446 h/yr" on a study running
  at 95% quietly moved it to 100% and changed the estimate with no indication
  that anything but the hours had been touched. A preset now sets the hours,
  which is what it is about, leaves the capacity factor alone, and says in the
  toast what it did and did not change.

  The confusion underneath it is now addressed on screen as well. The
  percentage in a preset's name is the **stream factor** — the operating hours
  as a share of the 8,760-hour calendar year — and it is already expressed in
  those hours; it is not the capacity factor, and putting the same derate in
  both would count it twice. A derived line under the two fields restates them
  as a stream factor and as equivalent full-load hours (hours x capacity
  factor, the number that actually multiplies an hourly rate), attributes the
  hours to the preset that set them, and warns if the hours exceed the year.
- **Native dropdowns, spinners and scrollbars followed the operating system's
  colour scheme rather than the sheet's**, so on a machine set to dark mode a
  `<datalist>` popup opened black over a vellum page. The document now declares
  `color-scheme` alongside its own palette, in both themes.
- **Choosing a utility on an equipment item was a free-text box with
  suggestions, and it fought back.** Once a name was typed the suggestion list
  filtered down to it, so the other options could not be reached without
  clearing the field first; and every keystroke repainted the equipment table,
  which destroyed the box being typed into — a backspace lost the caret and
  sent the page to the top. It is a proper dropdown now, grouped by category
  and priced in the option text, with **Something else…** for a utility of your
  own. Text is never a repaint trigger: a keystroke updates the cost cells in
  place, and only a discrete choice rebuilds anything.
- **Switching a line to a different utility kept the old unit** — electricity's
  kWh survived a change to steam — and kept any price typed against the utility
  it was no longer for. Picking from the catalogue now brings the unit, the
  category and the catalogue price with it, which is the point of picking from
  a catalogue.
- **The rate basis said only "per" and gave no way to find out what it meant.**
  It is labelled *Rate basis*, and the control and each of its options carry
  the explanation on hover; *Scales* is likewise now *Follows CF*. The
  plant-level table matches.
- **The Excel workbook left the equipment's utility consumption out of the
  operating cost.** Its variable-cost block read the project's own stream
  lists, which do not contain the lines derived from the equipment, so a
  workbook exported from a study using them was short by that amount and did
  not reconcile with the report beside it.
- **The installed-price checkbox filled its row and squeezed the text beside it
  into a tall, narrow column.** The parameter panel is rendered inside the
  equipment table, so `table.t input` outranked the panel's own single-class
  rules and applied `width:100%` to the checkbox — and stripped the border and
  padding from every parameter input. Those rules are now scoped to
  `.eq-detail`, and the flag is one row: a 16 px box and the sentence across the
  rest of the width.

## [2.0.0] — 2026-08-18

The library gains everything between an equipment list and a levelised cost,
and a graphical application to drive it.

### Added

**Operating cost** (`teakit.opex`) — variable lines (feedstock, catalysts,
utilities, waste) and factored fixed costs, under three named conventions:
NREL, Peters & Timmerhaus and NETL. Labour from either an explicit staffing plan
or an operators-per-shift rule, with the Turton operator correlation and
`turton_com()` as an independent cross-check. The model has nowhere to put
depreciation or interest, by construction.

**Products** (`teakit.products`) — a primary product whose price is solved for,
plus co-products and byproducts, under four allocation methods: byproduct
credit, market value, mass and energy. `credit_sensitivity()` reports how
leveraged a result is on the byproduct price.

**Project orchestration** (`teakit.project`) — the whole pipeline in one
serialisable object, with every input addressable by dotted path
(`p["opex.utilities.electricity.price"]`) and `parameters()` generating the
input list rather than hard-coding it. Three costing methods, and
`method_comparison()` to show the spread between them.

**Sensitivity** (`teakit.sensitivity`) — tornado, one-way sweep, two-way grid,
Monte Carlo (triangular, PERT, uniform, normal, lognormal) and breakeven, over
any parameter. Default ranges reflect how well each class of input is usually
known rather than a uniform band on everything.

**Charts** (`teakit.charts`) — nine chart types as `ChartSpec` objects rendering
to SVG from the standard library, to `dict` for the application's JavaScript, or
to matplotlib if it happens to be installed.

**Reports** (`teakit.report`) — text, Markdown, CSV, and a standalone HTML
report with the figures inline and no external resources at all.

**Defaults** (`teakit.defaults`) — location factors, EIA utility prices, BLS
wage data, tax and finance presets. Every entry carries a source and a vintage.

**The graphical application** (`teakit app`) — nine numbered steps in the order
an estimate is built, a drawing title block that marks the result *superseded*
when inputs change, light and dark themes, and full export. Standard-library
HTTP server, vanilla JavaScript, no framework, no CDN, works offline.

**CLI** — `equipment`, `catalogue`, `escalate`, `capital`, `levelized`, `dcf`,
`run`, `sensitivity`, `demo`, `app`.

**Demos** — three complete studies: natural-gas methanol, PEM electrolysis, and
cellulosic ethanol on the NREL nth-plant basis.

### Fixed

- `purchased_cost(quiet=True)` suppressed the unreliable-fit note as well as the
  Python warning. Since `Project` always costs quietly, a weak correlation could
  reach a finished report unflagged. The note is now always recorded; `quiet`
  only silences the warning.
- `Project.run()` wrote the computed capital back onto its own operating-cost
  configuration. Every sensitivity sweep re-runs the same object, so capital
  from one trial leaked into the next. Evaluation now uses a copy.
- Sensitivity routines assigned continuous values to integer parameters, so
  plant life, construction years and MACRS period failed every trial and
  silently disappeared from tornado charts. Assignment is now type-aware.
- `suggest_params()` offered parameters with no resolvable base value, which
  aborted an entire Monte Carlo run. Unsampleable paths are now filtered, and
  `monte_carlo()` skips rather than raises.
- The NETL nominal ATWACC preset read 6.46%; the published figure is 6.54%.

### Changed

- Renamed from `tea` to `teakit` for PyPI. `import teakit as tea` is the
  documented alias.
- `src/` layout, `pyproject.toml`, `pytest`, GitHub Actions across four Python
  versions and three operating systems.
- `equipment.material_factor()` is now public.

## [1.0.0]

Initial library: `indices`, `equipment`, `equipment_data`, `capital`,
`levelized`, `dcf`, `plant_sections`. 42 equipment correlations regressed from
DOE/NETL-2002/1169 Appendix B; the NETL capital cascade; CRF/FCR levelised
costs; after-tax discounted cash flow with MACRS.
