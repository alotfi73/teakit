# Cookbook

Short answers to the things people actually ask.

## Cost one piece of equipment, with an audit trail

```python
import teakit as tea
print(tea.purchased_cost("hx_shell_tube", 5_000, year=2025, material="ss316").report())
```

## Find out what a correlation is based on before trusting it

```python
print(tea.describe("compressor_centrifugal_150psia"))
print(tea.exponent_table())     # fitted exponent vs the literature range
```

Anything flagged unreliable says why. Cost it anyway if you must, but the
caution follows the number into the report.

## Use a vendor quote at one size, scaled with the catalogue exponent

```python
tea.EquipmentItem("R-101", kind="vessel_vertical_150psig",
                  size=8_000, base_cost=310_000, base_size=5_000, base_year=2024)
```

Set only what you know; the rest comes from the catalogue.

## Cost something the catalogue has never heard of

```python
# a correlation you have
tea.EquipmentItem("EL-101", mode="custom", size=210_000,
                  base_cost=2000 * 100_000, base_size=100_000, exponent=0.9,
                  base_year=2022, size_unit="kW", cost_is_installed=True)

# a single quote, no scaling
tea.EquipmentItem("F-101", mode="direct", direct_cost=48e6, base_year=2022,
                  cost_is_installed=True, note="reformer, licensor budget price")
```

`cost_is_installed=True` keeps the figure out of the installation factors.

## Move a cost between dollar-years

```python
tea.escalate(1_000_000, 2018, 2025)
tea.escalate(cost, 2020, 2025, quarter=2)
```

CEPCI is a *plant cost* index. It is the wrong deflator for wages, electricity
or feedstock — use a producer price index or a market series for those.

## Set a defensible contingency

```python
tea.PROCESS_CONTINGENCY_AACE     # AACE 16R-90 bands by technology maturity
tea.AACE_CLASSES                 # what accuracy each estimate class buys you
```

## Load a published financial basis instead of inventing one

```python
p.apply_finance_preset("NREL nth-plant")
p.apply_finance_preset("NETL investor-owned utility (real)")
list(tea.FINANCE_PRESETS)
```

Each carries a `source` string that lands in the report.

## Size the payroll when you have no staffing plan

```python
n = tea.operators_turton(n_non_particulate=14, n_particulate=1)
p.opex.labor = tea.LaborModel(operators_per_shift=n)
```

Count compressors, towers, reactors, heaters and exchangers. Do not count pumps
or vessels. Solids handling dominates the answer.

## Check an operating cost build-up against something independent

```python
tea.turton_com(fci=r.capital.toc, operating_labor=..., utilities=...,
               waste_treatment=..., raw_materials=...)["COM_d"]
```

More than ~20% apart from your line-by-line total means one of them is wrong.

## Find out how leveraged you are on a byproduct price

```python
p.products.credit_sensitivity(total_cost=annual_total)
```

An elasticity above ~1.5 means the headline number is a byproduct price
forecast wearing a process-economics hat. Switch to co-product allocation.

## Ask what price makes the project work

```python
tea.breakeven(p, "opex.raw_materials.feed.price", target=2.00)
tea.breakeven(p, "products.oxygen.price", target=4.50)
```

`None` means unreachable within the bracket — often the honest answer. If the
capital alone puts the floor above your target, no feed price will get there.

## Find out what actually drives the answer

```python
t = tea.tornado(p)                 # automatic parameter selection
print(t.report())
```

Then look only at the top three. The rest can be wrong by a factor of two.

## Report a range instead of a point

```python
r = tea.monte_carlo(p, {
    "opex.raw_materials.feed.price": {"dist": "pert", "low": 60, "mode": 82, "high": 130},
    "finance.discount_rate":         {"dist": "triangular", "low": 0.07, "high": 0.14},
    "capital.project_contingency_frac": {"dist": "uniform", "low": 0.15, "high": 0.35},
}, n=2000, seed=0)
print(r.report())      # P10 / P50 / P90
```

Say where the ranges came from. They are usually judgement, and judgement stated
is worth more than judgement hidden.

## See the curvature a tornado hides

```python
s = tea.sweep(p, "finance.discount_rate", n=21)
tea.charts.sweep_chart(s).save_svg("discount-rate.svg")
```

## Grid two assumptions that interact

```python
g = tea.two_way(p, "opex.utilities.electricity.price",
                   "opex.capacity_factor", nx=9, ny=9)
tea.charts.grid_chart(g).save_svg("grid.svg")
```

`nx × ny` full runs — keep it small on a DCF study.

## Produce something you can hand to someone

```python
tea.report.save_html(p, r, "study.html")          # standalone, figures inline
open("study.md", "w").write(tea.report.to_markdown(p, r))
open("equipment.csv", "w").write(tea.report.equipment_csv(r))
open("cashflow.csv", "w").write(tea.report.cash_flow_csv(r))
p.save("study.teakit.json")                        # re-openable in the app
```

## Compare two scenarios

```python
base = tea.demo("methanol")
alt = base.copy()
alt["opex.raw_materials.natural gas, feed + fuel.price"] = 8.00
alt.name = "High gas price"

for s in (base, alt):
    r = s.run()
    print(f"{s.name:24s} {r.unit_cost:8.2f} $/{r.unit}")
```

`copy()` round-trips through JSON, so the scenarios cannot share state.

## Drive it from a spreadsheet or a notebook

```python
import csv
rows = list(csv.DictReader(open("equipment.csv")))
p.equipment = [tea.EquipmentItem(tag=r["tag"], kind=r["kind"],
                                 size=float(r["size"]),
                                 quantity=int(r["quantity"]))
               for r in rows]
```

## Use matplotlib instead of the built-in SVG

```python
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
tea.charts.capex_breakdown_chart(r).to_matplotlib(ax)
plt.savefig("capex.png", dpi=200)
```

Needs `pip install teakit[plots]`. Everything works without it.
