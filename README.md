# teakit

**Techno-economic analysis of chemical process plants.** Capital cost, operating
cost, levelised product cost and discounted cash flow, built on published U.S.
government methodology, with every correlation and formula carrying its citation
in the docstring of the function that uses it.

Two things ship in this repository:

1. **A Python library** — `pip install teakit`, `import teakit as tea`. Twelve
   modules, no runtime dependencies, 100+ doctests.
2. **A graphical application** — `teakit app`. Point-and-click, for people who do
   not write Python. Also no dependencies: standard-library HTTP server, plain
   HTML/CSS/JavaScript, no framework, no CDN. It runs offline.

Free for noncommercial use under the
[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0);
commercial use needs a licence from the author. See
[Author and licence](#author-and-licence).

```
                                                        ┌─ report.py   text / md / html / csv
equipment.py ──▶ capital.py ──▶ levelized.py ──┐        ├─ charts.py   SVG, no plotting library
     ▲               ▲              dcf.py ────┼─▶ project.py ──▶ sensitivity.py
equipment_data.py  indices.py   opex.py ───────┘        └─ app/       the graphical interface
  42 correlations   CEPCI      products.py
```

---

## Install

### The application — nothing to install, no code to see

Download from the [latest release](../../releases/latest):

| Your machine | Download | How to start it |
|---|---|---|
| **Windows** | `teakit-<version>-windows.zip` | unzip, double-click `teakit.exe` |
| **macOS** | `teakit-<version>-portable.tar.gz` | unzip, double-click `Launch teakit.command` |
| **Linux** | `teakit-<version>-portable.tar.gz` | unzip, run `./launch-teakit.sh` |

The Windows build carries its own Python and needs nothing on the machine. The
portable build opens in your normal web browser and uses the Python that macOS
and Linux already ship (3.10 or newer). Both are the same program.

> On first run Windows may warn that the publisher is unknown, and macOS may
> refuse to open the launcher — both are because the builds are unsigned. The
> bundled `README.txt` says how to get past it. See
> [docs/distribution.md](docs/distribution.md).

### The library — for your own scripts

```bash
pip install teakit
```

Python 3.10+. Nothing else. teakit has **no runtime dependencies**, so it sits
alongside NumPy, pandas, SciPy or anything else without version arguments.

```bash
pip install "teakit[plots]"      # + matplotlib, for publication-styled figures
pip install "teakit[desktop]"    # + pywebview, to run the app in a native window
```

---

## Quick start — the library

Everything in one object:

```python
import teakit as tea

p = tea.Project(name="Methanol from natural gas", dollar_year=2025,
                location="USGC", method="dcf")

# 1. the equipment list
p.equipment = [
    tea.EquipmentItem("K-101", kind="compressor_centrifugal_150psia",
                      size=14_000, material="ss304"),
    tea.EquipmentItem("E-101", kind="hx_shell_tube", size=12_000, material="ss316"),
    tea.EquipmentItem("P-101", kind="pump", size=1_400, quantity=3, spare=1),
    # technology-defining equipment is never in a generic catalogue:
    tea.EquipmentItem("F-101", mode="direct", direct_cost=48e6, base_year=2022,
                      cost_is_installed=True, note="reformer, licensor price"),
]

# 2. what it spends every year
p.opex.raw_materials = [tea.Stream("natural gas", 1_150, "MMBtu", 4.39)]
p.opex.utilities     = [tea.Stream("electricity", 8_500, "kWh", 0.081,
                                   category="utility")]
p.opex.labor         = tea.LaborModel(operators_per_shift=5)
p.opex.operating_hours, p.opex.capacity_factor = 8_000, 0.95

# 3. what it sells
p.products.products = [
    tea.Product("methanol", 330_000, "tonne", role="primary"),
    tea.Product("export steam", 120_000, "tonne", price=18.0, role="byproduct"),
]

# 4. how it is financed
p.apply_finance_preset("NREL nth-plant")

r = p.run()
print(r.report())
print(f"{r.unit_cost:,.2f} $/tonne methanol")
```

Sensitivity, in two lines:

```python
t = tea.tornado(p)                      # picks the parameters that usually matter
print(t.report())
tea.charts.tornado_chart(t).save_svg("tornado.svg")
```

A standalone report with the figures embedded:

```python
tea.report.save_html(p, r, "methanol-tea.html")
```

Or use the pieces directly, which is what you want when checking one number:

```python
tea.purchased_cost("hx_shell_tube", 5_000, year=2025).report()
tea.fcr(0.0473, 30, 0.2574, 20)                      # NETL fixed charge rate
tea.escalate(1_000_000, 1998, 2025)                  # CEPCI
tea.installed_cost_loh(62_000, "gas_gt400F_lt150psig", "heat exchanger")
```

Try it without typing an equipment list:

```python
p = tea.demo("biorefinery")     # or "methanol", "electrolysis"
print(p.run().report())
```

---

## Quick start — the application

```bash
teakit app                 # in your browser
teakit app --desktop       # in a native window (needs teakit[desktop])
teakit app --debug         # log every request
```

Or, from a source checkout, with no install at all:

```bash
python run_app.py
python run_app.py --check  # which teakit am I actually running?
```

Opens on `http://127.0.0.1:8765`. Nine numbered steps in the order a real
estimate is built, plus a guide:

| | | |
|---|---|---|
| **01 Project** | dollar-year, location, currency, costing method | |
| **02 Equipment** | catalogue search, parameter overrides, custom correlations, vendor prices | |
| **03 Capital** | installation method, contingencies, owner's costs | |
| **04 Operating cost** | feeds, utilities, waste, labour, factored fixed costs | |
| **05 Products** | primary product, co-products, byproducts, allocation rule | |
| **06 Finance** | published presets, discount rate, tax, depreciation, debt | |
| **07 Results** | the cascade, the cost sheet, the cash flow, all three methods side by side | |
| **08 Charts** | eight standard figures plus a build-your-own plot | |
| **09 Sensitivity** | tornado, sweep, Monte Carlo, breakeven | |
| **Guide & method** | the manual, every option explained, and this run's own calculations | |

Every dropdown option carries a one-sentence explanation — on the option as a
tooltip, and under the control once selected. They come from
`teakit.methods.OPTION_HELP`, so the interface, the reports and the workbook
cannot drift apart.

Each equipment row opens into a parameter panel: what every parameter is, its
unit, the catalogue default beside your value, and a reset — per parameter or
for the whole item — along with the correlation's fitted range, fit quality and
source. A summary under the list rolls the equipment up by plant section and by
cost basis, keeping purchased and already-installed costs in separate columns.

Open any row and the item is one object: what it is called, the correlation
pricing it, the size that drives that cost, whatever process parameters you
want recorded against it — duty, inlet flow, temperature, pressure — and the
utilities it draws when it runs. Consumption entered here is priced into the
operating cost under that item's tag, so the electricity bill is attributable
to the machines that cause it rather than arriving as one plant total. The
Operating cost panel shows the roll-up by utility, each line linking back to
its item, with plant-level lines kept separately for what does not belong to
one machine.

It also carries the parts it wears out — electrodes, catalyst, membranes,
liners — each with a replacement interval, annualised over it and added to the
operating cost. A set of six electrodes at $42,000 on an 18-month cycle is
$168,000/yr.

Spares are bought but do not run: a 2+1 pump set is three pumps in the capital
and two drawing power, and teakit multiplies both consumption and wear by the
duty count only. There is **one price per utility for the whole study** — a
tariff belongs to the project, not to the machine drawing on it — so changing
it anywhere changes it everywhere. A negative rate is generation: a turbine or
an expander nets against everything else on that utility.

Equipment rolls up two ways: by **plant section**, which says where the money
went, and by **type**, which says what it was spent on — three blowers of
different sizes as one line.

The persistent panel on the right is a drawing **title block**: the levelised
cost, the basis it was computed on, and a revision number. Change any input and
the stamp reads *superseded* until you re-run — so the number on screen is never
silently out of date with the inputs beside it.

Everything exports: an **Excel workbook**, the project as JSON (re-openable,
and runnable from the CLI), the report as HTML or Markdown, the equipment list
and cash flow as CSV, and any figure as SVG.

They are written to a folder the application names on screen, under the export
buttons, not just into the browser's download tray. By default that folder is
`reports/` beside the application — next to `teakit.exe` in a packaged build, at
the repository root in a checkout, under `~/teakit` for an installed wheel.
**Report folder & files** changes it, by typing a path or through a native
folder chooser, opens it in the file manager, and lists what is already in it;
the choice is remembered in `~/.teakit/config.json`. Anything you put in that
folder yourself is listed alongside — it is an ordinary folder, not a store
teakit manages. Handing files to the browser instead is one click away in the
same dialog.

The workbook is the one to hand to someone else. Nine coloured tabs — Cover,
Basis, Equipment, Capital, Operating cost, Products, Cash flow, Results,
Method — with native Excel charts, and **live formulas** wherever the step is
arithmetic: change an equipment size or a contingency in Excel and the estimate
moves. Where it is not arithmetic — the DCF price solve, the MACRS schedule,
the per-item installation build-up — cells are marked as stamped values rather
than faked, so the workbook never quietly disagrees with the engine. Amber
cells are inputs, plain cells are computed, grey italic cells are stamped.

The last sheet, and the last section of every HTML and Markdown report, is the
**method appendix**: the equations actually used on that run, with that run's
numbers substituted and the arithmetic set out step by step, so a reviewer can
reproduce the answer with a calculator.

There is no authentication and there never will be. It binds to loopback. It is
a desktop tool, not a service.

---

## Reporting in another currency

The cost engine works in **USD** throughout — every correlation is from
DOE/NETL-2002/1169, every index is a US series, every default tariff is a US
tariff. Choosing another currency converts the *finished* result. Inputs stay in
USD, which is why the input tables are labelled `USD/unit`.

In the application, pick a currency on **01 Project**. The rate box next to it is
yours to edit; **Update** fetches the day's European Central Bank reference rate
if the machine is online. Changing either re-runs the estimate, so the equipment
list, the cascade, the cash flow and the title block all move together.

From the library:

```python
import teakit as tea

p = tea.demo("methanol")
p.currency = "EUR"
p.exchange_rate = 0.877                    # a rate agreed for the project
p.exchange_rate_source = "board rate, FY26 plan"
r = p.run()                                # every figure now in EUR
```

Or fetch one, with an offline fallback that never raises:

```python
table = tea.fetch_rates()                  # None if there is no network
p.exchange_rate = (table or tea.currency.RateTable()).rates["EUR"]
```

The rate and its provenance are stored in the project file and printed in the
basis of every report, so a study reproduces years later on the rate it was
quoted at rather than on today's. teakit warns when the rate in use is more than
a month old.

> A converted estimate is still a **US-basis** estimate. Local content, labour,
> freight and duty move independently of the exchange rate and usually dominate
> it — set the location factor for that. See limitation 6 below.

---

## Quick start — the command line

```bash
teakit equipment hx_shell_tube 5000 --year 2025 --material ss316
teakit catalogue --exponents
teakit escalate 1000000 1998 2025
teakit capital 250e6 --project-contingency 0.25
teakit levelized --rate 0.0473 --years 30 --tax-rate 0.2574 --depreciation-years 20

teakit demo biorefinery -o study.json
teakit run study.json --compare-methods
teakit run study.json --format html -o report.html
teakit run study.json --format xlsx -o estimate.xlsx
teakit sensitivity study.json --kind tornado --svg tornado.svg
```

---

## What the library does

### Equipment cost

42 single-parameter power-law correlations plus 6 two-parameter column
correlations, regressed from Appendix B of DOE/NETL-2002/1169. Each carries its
fitted exponent, R², relative RMSE, point count, validity range and a
reliability flag.

```python
tea.describe("compressor_centrifugal_150psia")
tea.catalogue("pump")
tea.exponent_table()          # fitted vs literature range, as a cross-check
```

Three things the module does that a bare power law does not:

* **Refuses to extrapolate** outside the fitted range unless you say so.
* **Splits oversize duties into parallel trains** rather than running the power
  law past the largest shop-fabricable unit — where cost becomes linear, and
  where quiet extrapolation is one of the commonest ways to under-estimate a
  large plant by a factor of two.
* **Records everything** in `CostResult.report()`: base size, base cost,
  exponent, index ratio, material factor, location factor. Paste it into an
  appendix.

### Capital cost

The full NETL ladder, with each level's definition in the docstring:

```
BEC  →  EPCC  →  TPC  →  TOC  →  TASC
```

`BEC`, `EPCC`, `TPC` and `TOC` are overnight costs in base-year dollars. `TASC`
is not — it is mixed current-year dollars including escalation and interest
during construction. **Always ask which one a published number is.** Multiplying
an FCR by a TOC understates the capital charge by 9% for a 3-year real build and
24–29% in nominal terms.

Three routes from purchased to installed cost: DOE/NETL distributive factors per
item, a Lang factor for the whole plant, or your own factor.

### Operating cost

Variable (feeds, catalysts, utilities, waste) and fixed (labour, maintenance,
insurance, overhead), split the way an operator would rather than the way an
accountant would. Three fixed-cost conventions — NREL, Peters & Timmerhaus and
NETL — each a coherent set, selectable by name and cited in the output.

**There is nowhere in this model to put depreciation or interest.** That is
deliberate and structural: they belong to the costing method, and putting them
in OPEX as well is the commonest single error in a first TEA.
`tea.turton_com()` gives an independent one-line cross-check; if it disagrees
with your line-by-line build-up by more than ~20%, one of them is wrong.

### Products and allocation

One primary product whose price is solved for, plus co-products and byproducts.
Four allocation methods — byproduct credit, market value, mass, energy — because
the choice can move the headline number by a factor of two, and a levelised cost
reported without naming the method is not reproducible.

`ProductSlate.credit_sensitivity()` reports how leveraged the answer is on the
byproduct price. Above about 1.5 you are publishing a price forecast wearing a
process-economics hat.

### Three costing methods, and why they disagree

```python
p.method_comparison()
# {'dcf': 2.282, 'fcr': 2.181, 'simple': 1.902}
```

| method | what it does | when |
|---|---|---|
| `dcf` | full after-tax cash flow, price solved at NPV = 0 | the NREL/H2A convention; most rigorous |
| `fcr` | fixed charge rate × TASC + annual O&M | the NETL convention; transparent and fast |
| `simple` | capital ÷ life, no cost of capital at all | screening only — understates by 30–50% |

The spread between them is the most informative diagnostic in a TEA. The error
is not picking one; it is mixing them — applying an FCR to a TOC, or charging
depreciation inside OPEX and again through the discount rate.

### Sensitivity

Every input is addressable by a dotted path, so nothing is hard-coded to a
particular study shape:

```python
p["finance.discount_rate"] = 0.12
p["opex.utilities.electricity.price"] = 0.095
p["equipment.K-101.size"] = 15_000
```

which gives you `tornado`, `sweep`, `two_way`, `monte_carlo` and `breakeven`
over anything. Default low/high ranges reflect how well each *class* of input is
usually known, rather than a uniform ±20% on everything — which is the commonest
way to produce a misleading tornado.

`breakeven` inverts the model: *what feedstock price do I need for a $2.00/kg
product?*

### Charts, without a plotting library

A chart is a `ChartSpec` — data plus labels plus a type — rendered three ways
from the same object: `.svg()` from the standard library, `.to_dict()` for the
application's JavaScript, and `.to_matplotlib()` if you happen to have
matplotlib. The interactive chart and the exported figure cannot disagree,
because they are the same numbers.

Nine types: bar, stacked bar, donut, waterfall, line, tornado, histogram,
scatter, heatmap.

---

## Sources

Everything here is traceable to a public document. The links are live.

### Capital methodology — U.S. Department of Energy

| Document | What it gives |
|---|---|
| NETL, *QGESS: Cost Estimation Methodology for NETL Assessments of Power Plant Performance*, [NETL-PUB-22580](https://www.netl.doe.gov/projects/files/QGESSCostEstMethodforNETLAssessmentsofPowerPlantPerformance_022621.pdf), Feb 2021 | The capital ladder BEC→EPCC→TPC→TOC→TASC, contingency and owner's-cost guidance, the finance structure, and Eqs. 1–15 for WACC, ATWACC, CRF, FCR, COE, TASC/TOC and LCOE |
| Loh, Lyons & White, *Process Equipment Cost Estimation, Final Report*, [DOE/NETL-2002/1169](https://www.osti.gov/servlets/purl/797810), Jan 2002 | Cost curves for 31 equipment types, installation bulk factors (Tables 2–5), setting-labour factors (Table 6), alloy factors (Table 7). **All 42 correlations are regressed from its Appendix B** |
| NETL, *QGESS: Capital Cost Scaling Methodology*, Rev. 4a, [OSTI](https://www.osti.gov/biblio/1893821) | 273 account-level scaling exponents for PC, IGCC and NGCC plant sections |

### Cash flow and minimum selling price — NREL and DOE Hydrogen

| Document | What it gives |
|---|---|
| Humbird et al., *Process Design and Economics for Biochemical Conversion of Lignocellulosic Biomass to Ethanol*, [NREL/TP-5100-47764](https://www.osti.gov/biblio/1013269), 2011 | The canonical DCFROR / minimum selling price reference; nth-plant economics; the fixed-operating-cost conventions and staffing table |
| [NREL H2A / H2A-Lite](https://www.nrel.gov/hydrogen/h2a-lite.html) | DOE's official hydrogen TEA models |
| [DOE Hydrogen Program Record 24005](https://www.hydrogen.energy.gov/docs/hydrogenprogramlibraries/pdfs/24005-clean-hydrogen-production-cost-pem-electrolyzer.pdf), 2024 | Installed PEM electrolyser capital, ~$2,000/kW (2022$) — used in the electrolysis demo |
| [NREL Annual Technology Baseline](https://atb.nrel.gov/) | The ATB LCOE formulation and its FCR/CAPEX convention |

### Indices and market data

CEPCI (annual 1964–2025, quarterly, monthly, sub-indices) compiled from
*Chemical Engineering*; RSMeans Historical Cost Index as an independent
cross-check; EIA industrial electricity and natural gas prices; BLS OEWS wage
data.

### Where teakit uses non-government sources

Marked as such wherever they appear: Turton et al. for the operator correlation
and the COM cross-check, Peters & Timmerhaus for the factored fixed-cost set,
Ulrich & Vasudevan for utility pricing, AACE RP 16R-90 and 18R-97 for
contingency bands and estimate classification, and published compilations for
location factors.

---

## Validation

`pytest -q` runs the acceptance suite, which is pinned to published values
rather than to teakit's own output:

| Test | Reference | Value |
|---|---|---|
| Loh Appendix A installed-cost example | DOE/NETL-2002/1169 | $150,245 |
| TASC/TOC, 3-year real build | NETL-PUB-22580 | 1.093 |
| TASC/TOC, 5-year real build | NETL-PUB-22580 | 1.154 |
| Fixed charge rate, real | NETL-PUB-22580 Ex. 3-6 | 0.0707 |
| Fixed charge rate, nominal | NETL-PUB-22580 Ex. 3-6 | 0.0886 |
| BEC 500 → TPC | NETL-PUB-22580 §2.1–2.4 | 705.0 |
| CRF, 10% / 20 yr | standard | 0.117460 |
| IRR at the solved MSP | by construction | = discount rate |
| Cellulosic ethanol demo | NREL design cases | $2.28/gal, in the published $2.15–2.50 band |

Plus invariants that must hold for *any* input: every fitted exponent inside
0.2–1.3, cost monotone in size, doubling size less than doubling cost wherever
n < 1, escalation reversible, the capital ladder monotone, `simple` below `dcf`,
sensitivity runs that do not mutate the project, and every chart spec
JSON-serialisable so the application cannot be broken by a library change.

---

## Limitations — state these in any report built on this

1. **Estimate class.** Correlation-based capital from a 1998 public data set is
   AACE **Class 5–4**: −25%/+50% at best, before the escalation error.
2. **Escalation span.** 1998 → today is far outside the five-year window cost
   engineers recommend for index escalation.
3. **CEPCI provenance.** Recent values are estimates and are flagged
   provisional in the output.
4. **Location.** Everything is U.S. Gulf Coast. The bundled location factors are
   indicative to roughly ±10 points and bundle three effects — freight, field
   labour and permitting — that move independently.
5. **Material and pressure.** Correlations are carbon steel at stated design
   conditions. Alloy factors are applied; **pressure corrections are not**.
6. **Currency is a reporting step, not a localisation.** The engine works in USD
   throughout. Choosing another currency converts the *finished* figure at a
   rate you control; it does not account for local content, labour, freight or
   duty, all of which move independently of the exchange rate and usually
   dominate it. Use the location factor for that, and read a converted number as
   "the US estimate, expressed in EUR" — never "what this plant costs in
   Europe". The rate and its source are recorded in the basis of every report.
7. **nth-plant.** The DCF defaults follow NREL's nth-plant convention: no
   first-of-a-kind premium, no pioneer cost growth, no learning penalty. For a
   first commercial unit an nth-plant number is a **floor, not an estimate** —
   see the RAND pioneer-plant studies (Merrow et al., R-2569-DOE, R-3215-DOE).
8. **Coverage.** The catalogue covers conventional process equipment. Anything
   technology-defining — electrolyser stacks, membranes, proprietary reactors,
   sorbent systems — needs a vendor quote or a published reference cost. The
   demos show how to blend the two, and why you must never mix a purchased cost
   with an installed cost in one subtotal.
9. **Utility and wage defaults are starting values, not answers.** They carry a
   source string and a vintage; replace anything that matters with your own
   tariff or quote.
10. **teakit is not a flowsheet simulator.** It will not close a mass or energy
   balance. The consumption rates you feed it have to come from somewhere else.
11. **Not legal, tax or investment advice.** Tax rates, depreciation schedules
    and financing structures change and vary by jurisdiction. Confirm them with
    a qualified adviser before relying on a result.

---

## Contributing

Correlations and reference values must cite a public source. Tests that pin
behaviour to a published number are worth more than tests that pin it to
yesterday's output. See `CONTRIBUTING.md`.

## Citing teakit

If an estimate made with teakit appears in published work, cite the study it was
written for, the toolkit itself, and the DOE/NETL and NREL sources under
[Sources](#sources):

> A. Lotfollahzade Moghaddam, S. Hejazi, M. Fattahi, M. Kibria, M. A. Khan.
> Molten metal methane pyrolysis for distributed hydrogen production: Reactor
> design, hydrodynamics, and technoeconomic insights. *Chemical Engineering
> Journal*, 2025. <https://doi.org/10.1016/j.cej.2025.169812>

> A. Lotfollahzade Moghaddam. teakit: techno-economic analysis of chemical
> process plants, version 2.0.0, 2026. <https://github.com/alotfi73/teakit>

`CITATION.cff` carries the same thing in the form GitHub reads, and
`teakit.citation("paper")` returns the reference as a string. Both report
formats print it in their footer.

## Author and licence

By A. Lotfollahzade Moghaddam, under the
[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)
— see `LICENSE`.

**Free** for any noncommercial purpose: academic research, teaching, personal
study and public-sector work. You may use it, change it and pass it on, so long
as whoever you pass it to gets the licence too.

**Commercial use needs a separate licence** from the author — that includes
using teakit on paid consulting or engineering work, and shipping it inside a
product or service you sell. Write to <alotfollahzade95@gmail.com> and it will
usually be straightforward.

This is a source-available licence, not an open-source one: the OSI definition
requires permitting commercial use, and this deliberately does not.

The underlying DOE, NETL and NREL documents are U.S. government works in the
public domain, and are not affected by this licence. CEPCI values are reproduced
as factual data for escalation; the index itself is proprietary to Access
Intelligence. Estimates you produce with teakit are yours.
