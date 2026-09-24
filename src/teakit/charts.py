"""
teakit.charts — Plots, with no plotting library.
================================================

teakit has no runtime dependencies, which rules out matplotlib. That turns out
to be an advantage rather than a compromise: a chart here is a
:class:`ChartSpec` — data plus labels plus a type — and a spec can be rendered
three ways from the same object:

* :meth:`ChartSpec.svg` writes standalone SVG with the standard library, which
  drops straight into a report, a LaTeX document or a web page;
* :meth:`ChartSpec.to_dict` hands the same numbers to the graphical
  application's JavaScript, so the interactive chart and the exported figure can
  never disagree;
* :meth:`ChartSpec.to_matplotlib` builds a matplotlib figure **if** the user
  happens to have matplotlib installed, so people who want publication styling
  are not locked out.

The chart types are the ones a TEA actually needs, no more::

    bar          equipment cost by item, OPEX by line
    stacked_bar  cost stack by scenario, CAPEX vs OPEX
    donut        share of a total
    waterfall    the capital cascade, BEC -> TASC
    line         a sweep: cost against one parameter
    tornado      sensitivity, sorted
    histogram    Monte Carlo output
    scatter      anything two-dimensional
    heatmap      a two-way grid

Every builder in :mod:`teakit.charts` takes a :class:`teakit.project.ProjectResult`
(or a sensitivity result) and returns a spec, so a full figure set is one call to
:func:`default_charts`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from html import escape

__all__ = [
    "ChartSpec", "PALETTE", "PALETTE_DARK",
    "bar", "stacked_bar", "donut", "waterfall", "line", "tornado_chart",
    "histogram", "scatter", "heatmap",
    "capex_breakdown_chart", "equipment_share_chart", "opex_breakdown_chart",
    "cost_stack_chart", "capex_opex_chart", "cash_flow_chart",
    "sweep_chart", "monte_carlo_chart", "grid_chart", "default_charts",
    "custom_chart",
    "UTILITY_GROUPS", "utility_chart", "utility_totals_chart",
    "utility_distribution_charts",
]

#: Categorical palette. Petrol/amber, chosen to stay legible in greyscale
#: print and to survive the common forms of colour-vision deficiency.
PALETTE = ["#1b6b73", "#d98324", "#4a7c59", "#8c4a5f", "#3d5a80",
           "#a68a3f", "#6b4e71", "#2a9d8f", "#bc6c25", "#577590",
           "#9c6644", "#43658b"]

PALETTE_DARK = ["#4fb3bf", "#f0a04b", "#7cb083", "#c98099", "#7architecture",
                "#d4b36a", "#a78bb0", "#5fd0c3", "#e8975a", "#89a7c4",
                "#c99a78", "#7a9cc6"]
PALETTE_DARK[4] = "#7a9ec9"

_NEG = "#b3402f"
_POS = "#1b6b73"


# ============================================================================
# The spec
# ============================================================================
@dataclass
class ChartSpec:
    """
    A chart, as data. Render it however you like.

    Examples
    --------
    >>> c = bar("Equipment", {"pump": 40_000, "exchanger": 180_000})
    >>> c.kind
    'bar'
    >>> "<svg" in c.svg()
    True
    """
    kind: str
    title: str = ""
    labels: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    series: list[dict] = field(default_factory=list)     # [{name, values, color}]
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    z: list[list[float]] = field(default_factory=list)
    x_label: str = ""
    y_label: str = ""
    unit: str = ""
    currency: str = "$"
    note: str = ""
    meta: dict = field(default_factory=dict)

    # -- export ---------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    def total(self) -> float:
        return sum(self.values)

    def svg(self, width: int = 720, height: int = 400, dark: bool = False) -> str:
        """Render to standalone SVG."""
        return _render(self, width, height, dark)

    def save_svg(self, path: str, **kw) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.svg(**kw))

    def to_matplotlib(self, ax=None):                     # pragma: no cover
        """
        Build a matplotlib axes, if matplotlib is installed.

        Raises :class:`ImportError` with a clear message otherwise — teakit does
        not depend on matplotlib and will not pretend to.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise ImportError(
                "to_matplotlib() needs matplotlib, which teakit does not "
                "require. Install it, or use .svg() which needs nothing."
            ) from exc
        if ax is None:
            _, ax = plt.subplots(figsize=(9, 5))
        k = self.kind
        if k in ("bar", "waterfall", "tornado"):
            ax.barh(self.labels, self.values) if k == "tornado" else \
                ax.bar(self.labels, self.values)
            if k != "tornado":
                ax.tick_params(axis="x", rotation=45)
        elif k == "donut":
            ax.pie(self.values, labels=self.labels, wedgeprops=dict(width=0.42))
        elif k in ("line", "scatter"):
            (ax.plot if k == "line" else ax.scatter)(self.x, self.y)
        elif k == "stacked_bar":
            bottom = [0.0] * len(self.labels)
            for s in self.series:
                ax.bar(self.labels, s["values"], bottom=bottom, label=s["name"])
                bottom = [b + v for b, v in zip(bottom, s["values"])]
            ax.legend()
        elif k == "histogram":
            ax.stairs(self.values, self.x)
        elif k == "heatmap":
            ax.imshow(self.z, aspect="auto", origin="lower")
        ax.set_title(self.title)
        ax.set_xlabel(self.x_label)
        ax.set_ylabel(self.y_label)
        return ax


# ============================================================================
# Generic constructors
# ============================================================================
def bar(title: str, data: dict[str, float], y_label: str = "",
        currency: str = "$", note: str = "", sort: bool = True,
        top_n: int | None = None) -> ChartSpec:
    """
    Vertical bars from a ``{label: value}`` mapping.

    ``top_n`` collapses the tail into an "other" bar, which is what you want for
    an equipment list of forty items where six matter.
    """
    items = list(data.items())
    if sort:
        items.sort(key=lambda kv: -abs(kv[1]))
    if top_n and len(items) > top_n:
        head, tail = items[:top_n], items[top_n:]
        items = head + [(f"other ({len(tail)} items)", sum(v for _, v in tail))]
    return ChartSpec(kind="bar", title=title,
                     labels=[k for k, _ in items], values=[v for _, v in items],
                     y_label=y_label, currency=currency, note=note)


def stacked_bar(title: str, categories: list[str], series: list[dict],
                y_label: str = "", currency: str = "$", note: str = "") -> ChartSpec:
    """``series`` is ``[{"name": ..., "values": [...]}, ...]``, one value per category."""
    for i, s in enumerate(series):
        s.setdefault("color", PALETTE[i % len(PALETTE)])
    return ChartSpec(kind="stacked_bar", title=title, labels=categories,
                     series=series, y_label=y_label, currency=currency, note=note)


def donut(title: str, data: dict[str, float], currency: str = "$",
          note: str = "", top_n: int | None = 8) -> ChartSpec:
    items = sorted(data.items(), key=lambda kv: -abs(kv[1]))
    if top_n and len(items) > top_n:
        head, tail = items[:top_n], items[top_n:]
        items = head + [(f"other ({len(tail)})", sum(v for _, v in tail))]
    return ChartSpec(kind="donut", title=title, labels=[k for k, _ in items],
                     values=[v for _, v in items], currency=currency, note=note)


def waterfall(title: str, steps: list[tuple[str, float]], y_label: str = "",
              currency: str = "$", note: str = "",
              totals: list[str] | None = None) -> ChartSpec:
    """
    Cumulative build-up. ``steps`` is ``[(label, delta), ...]``; labels listed in
    ``totals`` are drawn as full-height subtotal bars rather than floating deltas.
    """
    return ChartSpec(kind="waterfall", title=title,
                     labels=[s[0] for s in steps], values=[s[1] for s in steps],
                     y_label=y_label, currency=currency, note=note,
                     meta={"totals": totals or []})


def line(title: str, x: list[float], y: list[float], x_label: str = "",
         y_label: str = "", currency: str = "$", note: str = "",
         marker: tuple[float, float] | None = None) -> ChartSpec:
    """Single series. ``marker`` draws a crosshair at the base case."""
    return ChartSpec(kind="line", title=title, x=list(x), y=list(y),
                     x_label=x_label, y_label=y_label, currency=currency,
                     note=note, meta={"marker": list(marker) if marker else None})


#: Human-readable names for the metrics a sensitivity study can target.
METRIC_TITLES = {
    "msp": "minimum selling price", "unit_cost": "levelised cost",
    "npv": "NPV", "irr": "IRR", "toc": "total overnight cost",
    "tasc": "total as-spent capital", "tpc": "total plant cost",
    "bec": "bare erected cost", "opex": "annual operating cost",
    "opex_fixed": "fixed operating cost", "opex_variable": "variable operating cost",
    "capital_component": "capital component of cost", "payback": "discounted payback",
}


def tornado_chart(result, currency: str = "$", top_n: int = 12,
                  subject: str = "") -> ChartSpec:
    """From a :class:`teakit.sensitivity.TornadoResult`."""
    rows = result.rows[:top_n]
    name = METRIC_TITLES.get(result.metric, result.metric)
    return ChartSpec(
        kind="tornado",
        title=f"Sensitivity of {name}" + (f" — {subject}" if subject else ""),
        labels=[r["label"] for r in rows],
        values=[r["swing"] for r in rows],
        series=[{"name": "low", "values": [r["low_value"] for r in rows]},
                {"name": "high", "values": [r["high_value"] for r in rows]}],
        x_label=result.metric, currency=currency,
        note="one-at-a-time; inputs assumed independent",
        meta={"base": result.base_value,
              "params": [{"low": r["low_param"], "high": r["high_param"],
                          "base": r["base_param"], "unit": r.get("unit", "")}
                         for r in rows]})


def histogram(title: str, edges: list[float], counts: list[int],
              x_label: str = "", note: str = "",
              markers: dict[str, float] | None = None) -> ChartSpec:
    return ChartSpec(kind="histogram", title=title, x=list(edges),
                     values=[float(c) for c in counts], x_label=x_label,
                     y_label="trials", note=note, meta={"markers": markers or {}})


def scatter(title: str, x: list[float], y: list[float], x_label: str = "",
            y_label: str = "", note: str = "") -> ChartSpec:
    return ChartSpec(kind="scatter", title=title, x=list(x), y=list(y),
                     x_label=x_label, y_label=y_label, note=note)


def heatmap(title: str, x: list[float], y: list[float], z: list[list[float]],
            x_label: str = "", y_label: str = "", note: str = "") -> ChartSpec:
    return ChartSpec(kind="heatmap", title=title, x=list(x), y=list(y), z=z,
                     x_label=x_label, y_label=y_label, note=note)


# ============================================================================
# Project-aware builders
# ============================================================================
def capex_breakdown_chart(result) -> ChartSpec:
    """The capital cascade as a waterfall, BEC through TASC."""
    c = result.capital
    steps = [("BEC", c.bec), ("EPC services", c.epc_fee)]
    if c.process_contingency:
        steps.append(("process cont.", c.process_contingency))
    steps.append(("project cont.", c.project_contingency))
    steps.append(("TPC", c.tpc))
    for k, v in c.owners_costs.items():
        if v:
            # "pre-production (start-up)" -> "pre-production": the parenthetical
            # is useful in a table and unreadable rotated under a bar.
            steps.append((_clip(k.split(" (")[0], 20), v))
    steps.append(("TOC", c.toc))
    steps.append(("constr. financing", c.tasc - c.toc))
    steps.append(("TASC", c.tasc))
    return waterfall(f"Capital cascade — {result.dollar_year} {result.currency}",
                     steps, y_label=result.currency, currency=result.currency,
                     totals=["TPC", "TOC", "TASC"],
                     note="TOC is an overnight cost; TASC includes escalation "
                          "and interest during construction")


def equipment_share_chart(result, top_n: int = 12,
                          purchased_only: bool = False) -> ChartSpec:
    """
    Equipment cost by line item.

    By default every item appears, with already-installed prices marked in the
    label, because dropping them hides real capital. Pass
    ``purchased_only=True`` for a like-for-like comparison of the items that
    actually went through the installation factors.
    """
    # Bar labels are rotated and cannot carry a tag, a description and a basis
    # marker at a legible size. The tag plus the marker is what a reader needs
    # to identify the bar; the description stays in the table and the tooltip.
    rows = [r for r in result.equipment_rows
            if not (purchased_only and r["installed"])]
    data: dict[str, float] = {}
    for r in rows:
        label = r["tag"] + (" [installed]" if r["installed"] else "")
        n = 2
        while label in data:
            label, n = f"{label} ({n})", n + 1
        data[label] = r["cost"]

    if purchased_only:
        return bar("Purchased equipment cost by item", data,
                   y_label=result.currency, currency=result.currency,
                   top_n=top_n,
                   note="purchased cost only, before installation factors")
    mixed = any(r["installed"] for r in result.equipment_rows)
    return bar("Equipment cost by item", data, y_label=result.currency,
               currency=result.currency, top_n=top_n,
               note=("mixed basis: bars marked [installed] entered at their "
                     "installed price and bypassed the installation factors")
               if mixed else "purchased cost, before installation factors")


def opex_breakdown_chart(result, top_n: int = 12) -> ChartSpec:
    return bar("Annual operating cost by line", result.opex.items,
               y_label=f"{result.currency}/yr", currency=result.currency,
               top_n=top_n,
               note="excludes depreciation and cost of capital by construction")


def cost_stack_chart(result) -> ChartSpec:
    stack = result.cost_stack()
    return stacked_bar(
        f"{result.product} cost build-up",
        [result.product],
        [{"name": k, "values": [v]} for k, v in stack.items()],
        y_label=f"{result.currency}/{result.unit}", currency=result.currency,
        note=f"method: {result.method}")


def capex_opex_chart(result) -> ChartSpec:
    """Annualised capital charge against annual operating cost."""
    q = result.annual_production
    return donut("Annualised cost split",
                 {"capital charge": result.capital_component * q,
                  "fixed operating": result.fixed_component * q,
                  "variable operating": result.variable_component * q},
                 currency=result.currency,
                 note="capital annualised by the selected method")


def cash_flow_chart(result) -> ChartSpec:
    """Net cash flow bars with the cumulative discounted cash flow overlaid."""
    cf = result.cash_flow
    if cf is None:
        raise ValueError("cash flow chart needs method='dcf'")
    return ChartSpec(
        kind="stacked_bar", title="Cash flow",
        labels=[str(y) for y in cf.years],
        series=[{"name": "net cash flow", "values": list(cf.net_cash_flow),
                 "color": PALETTE[0]}],
        y_label=result.currency, currency=result.currency,
        meta={"overlay": {"name": "cumulative DCF",
                          "values": list(cf.cumulative_dcf),
                          "color": PALETTE[1]},
              "npv": cf.npv, "irr": cf.irr},
        note="cumulative DCF crosses zero at the discounted payback")


def sweep_chart(sweep_result, currency: str = "$") -> ChartSpec:
    return line(f"{sweep_result.metric} vs {sweep_result.label}",
                sweep_result.x, sweep_result.y,
                x_label=f"{sweep_result.label} {sweep_result.unit}".strip(),
                y_label=sweep_result.metric, currency=currency,
                marker=(sweep_result.base_x, sweep_result.base_y))


def monte_carlo_chart(mc_result, currency: str = "$") -> ChartSpec:
    edges, counts = mc_result.histogram()
    p = mc_result.percentiles
    return histogram(f"Monte Carlo — {mc_result.metric}", edges, counts,
                     x_label=mc_result.metric,
                     note=f"{len(mc_result.samples):,} trials",
                     markers={k: p[k] for k in ("P10", "P50", "P90") if k in p})


def grid_chart(grid_result) -> ChartSpec:
    return heatmap(f"{grid_result.metric}: {grid_result.y_label} vs "
                   f"{grid_result.x_label}",
                   grid_result.x, grid_result.y, grid_result.z,
                   x_label=grid_result.x_label, y_label=grid_result.y_label)


def custom_chart(kind: str, title: str, data: dict, **kw) -> ChartSpec:
    """
    Build any chart from an arbitrary ``{label: value}`` mapping.

    This is the hook behind the application's "plot anything" control: the user
    picks a series and a chart type and this assembles it, without teakit
    needing to know what the series means.

    >>> custom_chart("donut", "My split", {"a": 1, "b": 2}).kind
    'donut'
    """
    builders = {"bar": bar, "donut": donut}
    if kind in builders:
        return builders[kind](title, data, **kw)
    if kind == "waterfall":
        return waterfall(title, list(data.items()), **kw)
    raise ValueError(f"custom_chart cannot build {kind!r} from a mapping")


# ============================================================================
# Utility distribution — the process engineer's question
# ============================================================================
#: How a utility entry can be broken down, and where each grouping reads from.
UTILITY_GROUPS = {
    "item": ("by equipment item", "items"),
    "section": ("by plant section", "by_section"),
    "type": ("by equipment type", "by_type"),
}


def _utility_entry(result, utility: str) -> dict | None:
    for e in getattr(result, "utility_distribution", None) or []:
        if e["utility"] == utility:
            return e
    return None


def utility_chart(result, utility: str, group: str = "item",
                  measure: str = "quantity", kind: str = "donut") -> ChartSpec:
    """
    Where one utility goes: consumption or cost, split by item, plant section
    or equipment type.

    Every other chart here answers "what does it cost". This one answers the
    question a process engineer actually asks first — *which machines are
    drawing it* — from figures already recorded against the items.

    ``measure="quantity"`` plots the physical quantity in the utility's own
    unit, which is the honest way to compare draws; ``"cost"`` plots money.

    Examples
    --------
    >>> import teakit
    >>> r = teakit.demo().run()
    >>> c = utility_chart(r, "electricity")
    >>> c.kind, c.unit
    ('donut', 'kWh')
    >>> len(c.labels) > 1
    True
    """
    e = _utility_entry(result, utility)
    if e is None:
        known = [x["utility"] for x in
                 getattr(result, "utility_distribution", None) or []]
        raise KeyError(f"no utility {utility!r} in this result. "
                       f"Available: {known}")
    if group not in UTILITY_GROUPS:
        raise ValueError(f"group must be one of {list(UTILITY_GROUPS)}")
    if measure not in ("quantity", "cost"):
        raise ValueError("measure must be 'quantity' or 'cost'")

    label, key = UTILITY_GROUPS[group]
    field_name = "annual_quantity" if measure == "quantity" else "annual_cost"
    rows = e[key]
    if group == "item":
        data = {(r["tag"] or r["label"]): r[field_name] for r in rows}
    else:
        data = {r["name"]: r[field_name] for r in rows}
    # A utility nothing draws is not a chart. Zero-value contributors would
    # only add slices of nothing.
    data = {k: v for k, v in data.items() if v}

    unit = e["unit"]
    title = f"{utility} {label}"
    if measure == "quantity":
        note = (f"{e['annual_quantity']:,.0f} {unit}/yr in total"
                + (f", of which {e['generated']:,.0f} generated"
                   if e["generated"] else ""))
        y_label = f"{unit}/yr"
    else:
        note = f"{e['annual_cost']:,.0f} {result.currency}/yr in total"
        y_label = f"{result.currency}/yr"

    if kind == "bar":
        spec = bar(title, data, y_label=y_label,
                   currency=result.currency if measure == "cost" else "",
                   note=note, top_n=14)
    elif kind == "donut":
        spec = donut(title, data,
                     currency=result.currency if measure == "cost" else "",
                     note=note)
    else:
        raise ValueError("kind must be 'bar' or 'donut'")
    spec.unit = unit if measure == "quantity" else result.currency
    spec.meta = {"utility": utility, "group": group, "measure": measure}
    return spec


def utility_totals_chart(result, measure: str = "cost") -> ChartSpec:
    """
    Every utility side by side. Cost only by default: quantities in kWh, m3
    and MMBtu do not belong on one axis, and putting them there invents a
    comparison that does not exist.
    """
    dist = getattr(result, "utility_distribution", None) or []
    if measure != "cost":
        raise ValueError("only cost can be compared across utilities — their "
                         "quantities are in different units")
    data = {e["utility"]: e["annual_cost"] for e in dist if e["annual_cost"]}
    return bar("Annual cost by utility", data, y_label=f"{result.currency}/yr",
               currency=result.currency, top_n=14,
               note="Every variable line, whether it was entered against an "
                    "item or as a plant-level figure")


def utility_distribution_charts(result, top_n: int = 4) -> dict[str, ChartSpec]:
    """
    The standard utility figures: what each utility costs, and for the
    biggest few, which equipment draws them — by item and by kind of machine.

    The two groupings answer different questions. *By item* is where you go to
    find the one compressor worth re-rating; *by equipment type* is where you
    see that pumping is a third of the site load however it is spread. Both
    are cheap to draw and neither substitutes for the other.

    A grouping with only one entry is skipped: a donut with a single slice
    says nothing the table above it did not.
    """
    dist = getattr(result, "utility_distribution", None) or []
    if not dist:
        return {}
    out: dict[str, ChartSpec] = {}
    if len([e for e in dist if e["annual_cost"]]) > 1:
        out["utility_totals"] = utility_totals_chart(result)
    shown = 0
    for e in dist:
        if shown >= top_n:
            break
        if len([i for i in e["items"] if i["annual_quantity"]]) < 2:
            continue
        key = "utility_" + "".join(
            c if c.isalnum() else "_" for c in e["utility"].lower()).strip("_")
        out[key] = utility_chart(result, e["utility"], "item", "quantity",
                                 "donut")
        if len([r for r in e["by_type"] if r["annual_quantity"]]) > 1:
            out[key + "_by_type"] = utility_chart(
                result, e["utility"], "type", "quantity", "bar")
        shown += 1
    return out


def default_charts(result) -> dict[str, ChartSpec]:
    """
    The standard figure set for a project result.

    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import products
    >>> p = Project(dollar_year=2025, method="fcr")
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.products.products = [products.Product("widget", 15_000, "tonne")]
    >>> set(default_charts(p.run())) >= {"capex_waterfall", "cost_stack"}
    True
    """
    out = {
        "capex_waterfall": capex_breakdown_chart(result),
        "equipment_share": equipment_share_chart(result),
        "opex_breakdown": opex_breakdown_chart(result),
        "cost_stack": cost_stack_chart(result),
        "capex_opex_split": capex_opex_chart(result),
    }
    if result.opex.by_category:
        out["opex_by_category"] = donut(
            "Operating cost by category",
            {k.replace("_", " "): v for k, v in result.opex.by_category.items()},
            currency=result.currency)
    if result.cash_flow is not None:
        out["cash_flow"] = cash_flow_chart(result)
    # Three views of one list, and a reviewer usually asks for all three:
    # which item cost the most, where on the site the money went, and what
    # kind of machine it was spent on. `equipment_share` above is the first.
    if len(result.section_shares()) > 1:
        out["section_share"] = donut("Equipment cost by plant section",
                                     result.section_shares(),
                                     currency=result.currency)
    if len(result.type_shares()) > 1:
        out["type_share"] = donut("Equipment cost by type",
                                  result.type_shares(),
                                  currency=result.currency)
    return out


# ============================================================================
# SVG renderer
# ============================================================================
_THEME_LIGHT = dict(fg="#1c2b2d", muted="#5d6f72", grid="#dfe6e6",
                    bg="#ffffff", axis="#8fa3a5")
_THEME_DARK = dict(fg="#e8eded", muted="#9db0b3", grid="#2b3a3d",
                   bg="#0f1719", axis="#5d7276")


#: Currencies that have a short symbol. Anything else prints its ISO code with
#: a thin space, because "USD200.0M" on an axis is unreadable.
_SYMBOLS = {"USD": "$", "$": "$", "CAD": "C$", "EUR": "\u20ac", "GBP": "\u00a3",
            "AUD": "A$", "MXN": "MX$", "CNY": "\u00a5", "JPY": "\u00a5",
            "INR": "\u20b9", "BRL": "R$"}


def _fmt(v: float, currency: str = "") -> str:
    a = abs(v)
    if a >= 1e9:
        s = f"{v / 1e9:,.2f}B"
    elif a >= 1e6:
        s = f"{v / 1e6:,.1f}M"
    elif a >= 1e3:
        s = f"{v / 1e3:,.0f}k"
    elif a >= 1:
        s = f"{v:,.1f}"
    elif a > 0:
        s = f"{v:,.4g}"
    else:
        s = "0"
    if not currency:
        return s
    sym = _SYMBOLS.get(currency.upper())
    if sym:
        return f"-{sym}{s[1:]}" if s.startswith("-") else f"{sym}{s}"
    return f"{currency}\u2009{s}"


def _clip(text: str, n: int) -> str:
    """Truncate with an ellipsis, so a cut label reads as cut."""
    text = str(text)
    return text if len(text) <= n else text[:n - 1].rstrip() + "\u2026"


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(abs(raw))) if raw else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw / mag <= m:
            step = m * mag
            break
    else:
        step = 10 * mag
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v <= hi + step * 0.5:
        ticks.append(round(v, 12))
        v += step
    return ticks


def _esc(s) -> str:
    return escape(str(s), quote=True)


#: Vertical space reserved above a plot for its title. See :func:`_render`.
TITLE_BAND = 34


def _render(spec: ChartSpec, W: int, H: int, dark: bool) -> str:
    th = _THEME_DARK if dark else _THEME_LIGHT
    pal = PALETTE_DARK if dark else PALETTE
    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="ui-sans-serif,-apple-system,'
        f'Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{W}" height="{H}" fill="{th["bg"]}"/>',
    ]
    # The title gets a band of its own and the plot is translated below it.
    # Drawing both into one box meant the margins had to dodge the heading,
    # which held until a bar reached the top of its axis and its value label
    # ran into the title. A donut keeps the old treatment on purpose: it is
    # drawn off-centre with the legend to its right, so the top-left corner is
    # free and a band would only shrink the ring.
    title_h = TITLE_BAND if (spec.title and spec.kind != "donut") else 0
    if spec.title:
        o.append(f'<text x="16" y="{24 if title_h else 26}" font-size="15" '
                 f'font-weight="600" fill="{th["fg"]}">{_esc(spec.title)}</text>')
    note_h = 18 if spec.note else 0
    if spec.note:
        o.append(f'<text x="16" y="{H - 8}" font-size="11" fill="{th["muted"]}">'
                 f'{_esc(spec.note)}</text>')

    plot_h = H - note_h - title_h
    if title_h:
        o.append(f'<g transform="translate(0,{title_h})">')
    k = spec.kind
    if k in ("bar", "waterfall"):
        o += _svg_bars(spec, W, plot_h, th, pal)
    elif k == "stacked_bar":
        o += _svg_stacked(spec, W, plot_h, th, pal)
    elif k == "donut":
        o += _svg_donut(spec, W, plot_h, th, pal)
    elif k in ("line", "scatter"):
        o += _svg_line(spec, W, plot_h, th, pal, points_only=(k == "scatter"))
    elif k == "tornado":
        o += _svg_tornado(spec, W, plot_h, th, pal)
    elif k == "histogram":
        o += _svg_histogram(spec, W, plot_h, th, pal)
    elif k == "heatmap":
        o += _svg_heatmap(spec, W, plot_h, th, pal)
    else:
        o.append(f'<text x="16" y="60" fill="{th["muted"]}">no renderer for '
                 f'{_esc(k)}</text>')
    if title_h:
        o.append("</g>")
    o.append("</svg>")
    return "\n".join(o)


def _axes(o, x0, y0, x1, y1, ticks, scale, th, y_label, currency):
    for t in ticks:
        y = scale(t)
        o.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
                 f'stroke="{th["grid"]}" stroke-width="1"/>')
        o.append(f'<text x="{x0 - 6}" y="{y + 4:.1f}" font-size="10" '
                 f'text-anchor="end" fill="{th["muted"]}">{_fmt(t, currency)}</text>')
    # A bare currency code as an axis label just repeats the tick prefixes and
    # collides with them at narrow widths. Ticks already carry the symbol.
    if y_label and y_label.upper() not in _SYMBOLS and len(y_label) > 4:
        o.append(f'<text x="14" y="{(y0 + y1) / 2:.0f}" font-size="10" '
                 f'fill="{th["muted"]}" transform="rotate(-90 14 '
                 f'{(y0 + y1) / 2:.0f})" text-anchor="middle">{_esc(y_label)}</text>')


def _svg_bars(spec, W, H, th, pal):
    o = []
    L, R, T, B = 76, 20, 22, 104
    x0, x1, y0, y1 = L, W - R, T, H - B
    vals = list(spec.values)
    waterfall_mode = spec.kind == "waterfall"
    totals = set(spec.meta.get("totals", []))

    if waterfall_mode:
        run, bars, cum = 0.0, [], []
        for lbl, v in zip(spec.labels, vals):
            if lbl in totals:
                bars.append((0.0, v))
                run = v
            else:
                bars.append((run, run + v))
                run += v
            cum.append(run)
        lo = min(min(b) for b in bars) if bars else 0
        hi = max(max(b) for b in bars) if bars else 1
    else:
        lo, hi = min(0, min(vals, default=0)), max(vals, default=1)
    lo = min(lo, 0)
    ticks = _nice_ticks(lo, hi)
    lo_t, hi_t = min(ticks), max(ticks)

    def sc(v):
        return y1 - (v - lo_t) / (hi_t - lo_t or 1) * (y1 - y0)

    _axes(o, x0, y0, x1, y1, ticks, sc, th, spec.y_label, spec.currency)
    n = max(len(vals), 1)
    slot = (x1 - x0) / n
    bw = min(slot * 0.68, 62)
    for i, lbl in enumerate(spec.labels):
        cx = x0 + slot * (i + 0.5)
        if waterfall_mode:
            a, b = bars[i]
            top, bot = sc(max(a, b)), sc(min(a, b))
            col = pal[0] if lbl in totals else (pal[1] if vals[i] >= 0 else _NEG)
            if lbl in totals:
                col = pal[0]
        else:
            v = vals[i]
            top, bot = sc(max(v, 0)), sc(min(v, 0))
            col = pal[i % len(pal)] if v >= 0 else _NEG
        h = max(bot - top, 1.2)
        o.append(f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                 f'height="{h:.1f}" fill="{col}" rx="2"><title>{_esc(lbl)}: '
                 f'{_fmt(vals[i], spec.currency)}</title></rect>')
        o.append(f'<text x="{cx:.1f}" y="{top - 5:.1f}" font-size="9.5" '
                 f'text-anchor="middle" fill="{th["fg"]}">'
                 f'{_fmt(vals[i], spec.currency)}</text>')
        o.append(f'<text x="{cx:.1f}" y="{y1 + 12:.1f}" font-size="9.5" '
                 f'fill="{th["muted"]}" text-anchor="end" '
                 f'transform="rotate(-38 {cx:.1f} {y1 + 12:.1f})">'
                 f'{_esc(_clip(lbl, 28))}</text>')
    o.append(f'<line x1="{x0}" y1="{sc(0):.1f}" x2="{x1}" y2="{sc(0):.1f}" '
             f'stroke="{th["axis"]}" stroke-width="1.2"/>')
    return o


def _svg_stacked(spec, W, H, th, pal):
    o = []
    L, R, T, B = 76, 20, 36, 74
    x0, x1, y0, y1 = L, W - R, T, H - B
    n = max(len(spec.labels), 1)
    pos = [sum(max(s["values"][i], 0) for s in spec.series) for i in range(n)]
    neg = [sum(min(s["values"][i], 0) for s in spec.series) for i in range(n)]
    overlay = spec.meta.get("overlay")
    hi = max(pos + ([max(overlay["values"])] if overlay else [0]))
    lo = min(neg + ([min(overlay["values"])] if overlay else [0]))
    ticks = _nice_ticks(min(lo, 0), hi)
    lo_t, hi_t = min(ticks), max(ticks)

    def sc(v):
        return y1 - (v - lo_t) / (hi_t - lo_t or 1) * (y1 - y0)

    _axes(o, x0, y0, x1, y1, ticks, sc, th, spec.y_label, spec.currency)
    slot = (x1 - x0) / n
    bw = min(slot * 0.7, 70)
    for i in range(n):
        cx = x0 + slot * (i + 0.5)
        up = dn = 0.0
        for j, s in enumerate(spec.series):
            v = s["values"][i]
            if v >= 0:
                top, bot = sc(up + v), sc(up)
                up += v
            else:
                top, bot = sc(dn), sc(dn + v)
                dn += v
            col = s.get("color") or pal[j % len(pal)]
            o.append(f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                     f'height="{max(bot - top, 0.8):.1f}" fill="{col}" rx="1.5">'
                     f'<title>{_esc(s["name"])}: {_fmt(v, spec.currency)}</title></rect>')
        step = max(1, n // 14)
        if i % step == 0:
            o.append(f'<text x="{cx:.1f}" y="{y1 + 14:.1f}" font-size="9.5" '
                     f'text-anchor="middle" fill="{th["muted"]}">'
                     f'{_esc(_clip(spec.labels[i], 14))}</text>')
    if overlay:
        pts = " ".join(f"{x0 + slot * (i + 0.5):.1f},{sc(v):.1f}"
                       for i, v in enumerate(overlay["values"]))
        o.append(f'<polyline points="{pts}" fill="none" stroke="'
                 f'{overlay.get("color", pal[1])}" stroke-width="2.2"/>')
    o.append(f'<line x1="{x0}" y1="{sc(0):.1f}" x2="{x1}" y2="{sc(0):.1f}" '
             f'stroke="{th["axis"]}" stroke-width="1.2"/>')
    # legend
    lx = x0
    for j, s in enumerate(spec.series + ([overlay] if overlay else [])):
        col = s.get("color") or pal[j % len(pal)]
        o.append(f'<rect x="{lx}" y="{T - 20}" width="10" height="10" fill="{col}" rx="2"/>')
        o.append(f'<text x="{lx + 14}" y="{T - 11}" font-size="10" '
                 f'fill="{th["muted"]}">{_esc(s["name"])}</text>')
        lx += 22 + 6.4 * len(s["name"])
    return o


def _svg_donut(spec, W, H, th, pal):
    o = []
    total = sum(abs(v) for v in spec.values) or 1.0
    cx, cy = W * 0.30, H * 0.55
    r, rin = min(W * 0.22, H * 0.34), min(W * 0.22, H * 0.34) * 0.58
    ang = -math.pi / 2
    for i, (lbl, v) in enumerate(zip(spec.labels, spec.values)):
        frac = abs(v) / total
        a2 = ang + frac * 2 * math.pi
        large = 1 if frac > 0.5 else 0
        x1_, y1_ = cx + r * math.cos(ang), cy + r * math.sin(ang)
        x2_, y2_ = cx + r * math.cos(a2), cy + r * math.sin(a2)
        x3, y3 = cx + rin * math.cos(a2), cy + rin * math.sin(a2)
        x4, y4 = cx + rin * math.cos(ang), cy + rin * math.sin(ang)
        d = (f"M {x1_:.2f} {y1_:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x2_:.2f} {y2_:.2f} "
             f"L {x3:.2f} {y3:.2f} A {rin:.2f} {rin:.2f} 0 {large} 0 {x4:.2f} {y4:.2f} Z")
        o.append(f'<path d="{d}" fill="{pal[i % len(pal)]}"><title>{_esc(lbl)}: '
                 f'{_fmt(v, spec.currency)} ({frac:.1%})</title></path>')
        ang = a2
    o.append(f'<text x="{cx:.0f}" y="{cy - 2:.0f}" font-size="15" font-weight="600" '
             f'text-anchor="middle" fill="{th["fg"]}">'
             f'{_fmt(sum(spec.values), spec.currency)}</text>')
    o.append(f'<text x="{cx:.0f}" y="{cy + 14:.0f}" font-size="10" '
             f'text-anchor="middle" fill="{th["muted"]}">total</text>')
    ly = 56
    for i, (lbl, v) in enumerate(zip(spec.labels, spec.values)):
        o.append(f'<rect x="{W * 0.56:.0f}" y="{ly - 9}" width="10" height="10" '
                 f'fill="{pal[i % len(pal)]}" rx="2"/>')
        o.append(f'<text x="{W * 0.56 + 16:.0f}" y="{ly}" font-size="11" '
                 f'fill="{th["fg"]}">{_esc(_clip(lbl, 30))}</text>')
        o.append(f'<text x="{W - 18}" y="{ly}" font-size="11" text-anchor="end" '
                 f'fill="{th["muted"]}">{abs(v) / total:.1%}</text>')
        ly += 19
    return o


def _svg_line(spec, W, H, th, pal, points_only=False):
    o = []
    L, R, T, B = 76, 24, 22, 52
    x0, x1, y0, y1 = L, W - R, T, H - B
    xs, ys = spec.x, spec.y
    if not xs:
        return o
    xlo, xhi = min(xs), max(xs)
    yt = _nice_ticks(min(ys), max(ys))
    ylo, yhi = min(yt), max(yt)

    def sy(v):
        return y1 - (v - ylo) / (yhi - ylo or 1) * (y1 - y0)

    def sx(v):
        return x0 + (v - xlo) / ((xhi - xlo) or 1) * (x1 - x0)

    _axes(o, x0, y0, x1, y1, yt, sy, th, spec.y_label, spec.currency)
    for t in _nice_ticks(xlo, xhi, 6):
        if xlo <= t <= xhi:
            o.append(f'<text x="{sx(t):.1f}" y="{y1 + 15:.0f}" font-size="10" '
                     f'text-anchor="middle" fill="{th["muted"]}">{_fmt(t)}</text>')
    if not points_only:
        pts = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(xs, ys))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{pal[0]}" '
                 f'stroke-width="2.4" stroke-linejoin="round"/>')
    for a, b in zip(xs, ys):
        o.append(f'<circle cx="{sx(a):.1f}" cy="{sy(b):.1f}" r="3" fill="{pal[0]}">'
                 f'<title>{_fmt(a)} -> {_fmt(b, spec.currency)}</title></circle>')
    m = spec.meta.get("marker")
    if m:
        o.append(f'<line x1="{sx(m[0]):.1f}" y1="{y0}" x2="{sx(m[0]):.1f}" '
                 f'y2="{y1}" stroke="{pal[1]}" stroke-width="1.4" '
                 f'stroke-dasharray="4 3"/>')
        o.append(f'<text x="{sx(m[0]) + 5:.1f}" y="{y0 + 12}" font-size="10" '
                 f'fill="{pal[1]}">base</text>')
    if spec.x_label:
        o.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 34:.0f}" font-size="10.5" '
                 f'text-anchor="middle" fill="{th["muted"]}">{_esc(spec.x_label)}</text>')
    return o


def _svg_tornado(spec, W, H, th, pal):
    o = []
    L, R, T, B = 192, 62, 38, 34
    x0, x1, y0, y1 = L, W - R, T, H - B
    base = spec.meta.get("base", 0.0)
    los = spec.series[0]["values"]
    his = spec.series[1]["values"]
    lo = min(list(los) + list(his) + [base])
    hi = max(list(los) + list(his) + [base])
    pad = (hi - lo) * 0.08 or abs(base) * 0.1 or 1
    lo, hi = lo - pad, hi + pad

    def sx(v):
        return x0 + (v - lo) / (hi - lo) * (x1 - x0)

    n = max(len(spec.labels), 1)
    rowh = (y1 - y0) / n
    bh = min(rowh * 0.62, 24)
    for t in _nice_ticks(lo, hi, 5):
        if lo <= t <= hi:
            o.append(f'<line x1="{sx(t):.1f}" y1="{y0}" x2="{sx(t):.1f}" y2="{y1}" '
                     f'stroke="{th["grid"]}"/>')
            o.append(f'<text x="{sx(t):.1f}" y="{y1 + 15}" font-size="10" '
                     f'text-anchor="middle" fill="{th["muted"]}">{_fmt(t)}</text>')
    for i, lbl in enumerate(spec.labels):
        cy = y0 + rowh * (i + 0.5)
        a, b = sx(los[i]), sx(his[i])
        bx = sx(base)
        o.append(f'<rect x="{min(a, bx):.1f}" y="{cy - bh / 2:.1f}" '
                 f'width="{abs(bx - a):.1f}" height="{bh:.1f}" fill="{pal[0]}" '
                 f'opacity="0.9" rx="2"><title>low: {_fmt(los[i])}</title></rect>')
        o.append(f'<rect x="{min(b, bx):.1f}" y="{cy - bh / 2:.1f}" '
                 f'width="{abs(b - bx):.1f}" height="{bh:.1f}" fill="{pal[1]}" '
                 f'opacity="0.9" rx="2"><title>high: {_fmt(his[i])}</title></rect>')
        o.append(f'<text x="{L - 10}" y="{cy + 4:.1f}" font-size="11" '
                 f'text-anchor="end" fill="{th["fg"]}">{_esc(_clip(lbl, 27))}</text>')
        o.append(f'<text x="{x1 + 6}" y="{cy + 4:.1f}" font-size="10" '
                 f'fill="{th["muted"]}">{spec.values[i] / (base or 1) * 100:.0f}%</text>')
    o.append(f'<line x1="{sx(base):.1f}" y1="{y0 - 6}" x2="{sx(base):.1f}" '
             f'y2="{y1}" stroke="{th["fg"]}" stroke-width="1.6"/>')
    o.append(f'<text x="{sx(base):.1f}" y="{y0 - 10}" font-size="10" '
             f'text-anchor="middle" fill="{th["fg"]}">base {_fmt(base)}</text>')
    return o


def _svg_histogram(spec, W, H, th, pal):
    o = []
    L, R, T, B = 62, 20, 22, 52
    x0, x1, y0, y1 = L, W - R, T, H - B
    edges, counts = spec.x, spec.values
    if len(edges) < 2:
        return o
    hi = max(counts) or 1
    ticks = _nice_ticks(0, hi, 4)

    def sy(v):
        return y1 - v / (max(ticks) or 1) * (y1 - y0)

    def sx(v):
        return x0 + (v - edges[0]) / ((edges[-1] - edges[0]) or 1) * (x1 - x0)

    _axes(o, x0, y0, x1, y1, ticks, sy, th, "trials", "")
    for i, c in enumerate(counts):
        a, b = sx(edges[i]), sx(edges[i + 1])
        o.append(f'<rect x="{a:.1f}" y="{sy(c):.1f}" width="{max(b - a - 1, 1):.1f}" '
                 f'height="{y1 - sy(c):.1f}" fill="{pal[0]}" opacity="0.85">'
                 f'<title>{_fmt(edges[i])}-{_fmt(edges[i + 1])}: {int(c)}</title></rect>')
    for j, (name, v) in enumerate(sorted(spec.meta.get("markers", {}).items())):
        o.append(f'<line x1="{sx(v):.1f}" y1="{y0}" x2="{sx(v):.1f}" y2="{y1}" '
                 f'stroke="{pal[1]}" stroke-width="1.6" stroke-dasharray="5 3"/>')
        o.append(f'<text x="{sx(v):.1f}" y="{y0 - 4 + j * 0}" font-size="10" '
                 f'text-anchor="middle" fill="{pal[1]}">{_esc(name)}</text>')
    for t in _nice_ticks(edges[0], edges[-1], 5):
        if edges[0] <= t <= edges[-1]:
            o.append(f'<text x="{sx(t):.1f}" y="{y1 + 15}" font-size="10" '
                     f'text-anchor="middle" fill="{th["muted"]}">{_fmt(t)}</text>')
    if spec.x_label:
        o.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 34}" font-size="10.5" '
                 f'text-anchor="middle" fill="{th["muted"]}">{_esc(spec.x_label)}</text>')
    return o


def _svg_heatmap(spec, W, H, th, pal):
    o = []
    L, R, T, B = 76, 78, 22, 52
    x0, x1, y0, y1 = L, W - R, T, H - B
    z = spec.z
    flat = [v for row in z for v in row if v == v]
    if not flat:
        return o
    lo, hi = min(flat), max(flat)
    ny, nx = len(z), len(z[0])
    cw, ch = (x1 - x0) / nx, (y1 - y0) / ny

    def col(v):
        t = (v - lo) / ((hi - lo) or 1)
        # petrol -> cream -> amber
        if t < 0.5:
            f = t * 2
            r, g, b = 27 + f * (245 - 27), 107 + f * (241 - 107), 115 + f * (222 - 115)
        else:
            f = (t - 0.5) * 2
            r, g, b = 245 - f * (245 - 217), 241 - f * (241 - 131), 222 - f * (222 - 36)
        return f"rgb({int(r)},{int(g)},{int(b)})"

    for i in range(ny):
        for j in range(nx):
            v = z[i][j]
            if v != v:
                continue
            o.append(f'<rect x="{x0 + j * cw:.1f}" y="{y1 - (i + 1) * ch:.1f}" '
                     f'width="{cw + 0.5:.1f}" height="{ch + 0.5:.1f}" '
                     f'fill="{col(v)}"><title>{_fmt(spec.x[j])}, '
                     f'{_fmt(spec.y[i])}: {_fmt(v)}</title></rect>')
    for j in range(0, nx, max(1, nx // 6)):
        o.append(f'<text x="{x0 + (j + 0.5) * cw:.1f}" y="{y1 + 15}" font-size="10" '
                 f'text-anchor="middle" fill="{th["muted"]}">{_fmt(spec.x[j])}</text>')
    for i in range(0, ny, max(1, ny // 6)):
        o.append(f'<text x="{x0 - 6}" y="{y1 - (i + 0.5) * ch + 4:.1f}" '
                 f'font-size="10" text-anchor="end" fill="{th["muted"]}">'
                 f'{_fmt(spec.y[i])}</text>')
    for s in range(11):
        v = lo + (hi - lo) * s / 10
        o.append(f'<rect x="{x1 + 18}" y="{y1 - (s + 1) * (y1 - y0) / 11:.1f}" '
                 f'width="14" height="{(y1 - y0) / 11 + 0.5:.1f}" fill="{col(v)}"/>')
    o.append(f'<text x="{x1 + 36}" y="{y1:.0f}" font-size="10" '
             f'fill="{th["muted"]}">{_fmt(lo)}</text>')
    o.append(f'<text x="{x1 + 36}" y="{y1 - (y1 - y0) + 10:.0f}" font-size="10" '
             f'fill="{th["muted"]}">{_fmt(hi)}</text>')
    if spec.x_label:
        o.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 34}" font-size="10.5" '
                 f'text-anchor="middle" fill="{th["muted"]}">{_esc(spec.x_label)}</text>')
    if spec.y_label:
        o.append(f'<text x="16" y="{(y0 + y1) / 2:.0f}" font-size="10.5" '
                 f'fill="{th["muted"]}" text-anchor="middle" '
                 f'transform="rotate(-90 16 {(y0 + y1) / 2:.0f})">'
                 f'{_esc(spec.y_label)}</text>')
    return o


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
