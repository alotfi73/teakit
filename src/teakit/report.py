"""
teakit.report — Turning a result into something you can hand to someone.
========================================================================

Four output formats, all stdlib:

``text``      the console dump, for a terminal or a log
``markdown``  for a README, a notebook or a pull request
``html``      a standalone file with the charts embedded as inline SVG —
              no CDN, no JavaScript, opens offline, prints properly
``csv``       the equipment list, the cash flow, or the OPEX sheet, for Excel

Every format leads with the **assumptions and their provenance**, not the
answer. A levelised cost without its basis is not a result, it is a rumour, and
the single most useful thing this module does is make the basis impossible to
omit: dollar-year, location, costing method, discount rate, allocation rule,
estimate class, and every warning the run raised.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from html import escape

from . import charts as _charts

__all__ = ["to_text", "to_markdown", "to_html", "equipment_csv",
           "equipment_utility_csv",
           "cash_flow_csv", "opex_csv", "assumptions_table", "save_html",
           "method_appendix_markdown", "method_appendix_html"]


# ============================================================================
# Assumptions
# ============================================================================
def assumptions_table(project, result) -> list[tuple[str, str]]:
    """
    The basis of the estimate, as ``[(label, value), ...]``.

    This is the table that belongs at the front of any report built on teakit.

    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import products
    >>> p = Project(dollar_year=2025, method="fcr")
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.products.products = [products.Product("widget", 15_000, "tonne")]
    >>> dict(assumptions_table(p, p.run()))["Costing method"]
    'fcr — FCR x TASC (NETL Eq. 3/4)'
    """
    f, c = project.finance, project.capital
    method_desc = {
        "dcf": "dcf — after-tax cash flow, price solved at NPV = 0 (NREL/H2A)",
        "fcr": "fcr — FCR x TASC (NETL Eq. 3/4)",
        "crf": "crf — annualised capital (CRF x TOC) + O&M, pre-tax",
        "simple": "simple — straight-line capital recovery, NO cost of capital",
    }.get(result.method, result.method)
    # .get, not [], and a fallback that names the method: an unknown key here
    # used to take the whole report down with a bare KeyError.
    inst = {"loh": "DOE/NETL distributive factors (Loh et al. 2002)",
            "type": f"DOE/NETL distributive factors by equipment type "
                    f"(Loh et al. 2002), x{result.installation_factor:.3f} overall",
            "lang": f"Lang factor ({c.lang_type})",
            "factor": f"user factor x{c.installation_factor:g}",
            }.get(c.installation_method, c.installation_method)
    rows = [
        ("Project", project.name),
        ("Prepared", date.today().isoformat()),
        ("Dollar year", f"{result.dollar_year} {result.currency}"),
        ("Location", f"{project.location} "
                     f"(location factor {project.effective_location_factor():.2f})"),
        ("Costing method", method_desc),
        ("Installation method", inst),
        ("Cost basis of correlations", "1998 Q1 USGC, DOE/NETL-2002/1169 "
                                       "App. B, escalated by CEPCI"),
        ("Capital basis", f"{c.basis}; EPC fee {c.epc_fee_frac:.1%} of BEC, "
                          f"process contingency {c.process_contingency_frac:.1%}, "
                          f"project contingency {c.project_contingency_frac:.1%}"),
        ("Discount rate", f"{f.discount_rate:.2%} ({f.basis})"),
        ("Tax rate", f"{f.tax_rate:.2%}"),
        ("Depreciation", f"MACRS {f.depreciation_years}-year"),
        ("Plant life", f"{f.plant_life_years} years"),
        ("Construction", f"{f.construction_years} years"),
        ("Operating time", f"{result.opex.operating_hours:,.0f} h/yr at "
                           f"{result.opex.capacity_factor:.0%} capacity factor"),
        ("Fixed-cost convention", project.opex.convention),
        ("Allocation", result.allocation.method),
        ("Estimate class", "AACE Class 5-4 (-25%/+50% at best) — correlation-based "
                           "capital from a public data set"),
    ]
    if getattr(result, "currency", "USD") != "USD":
        # The rate belongs in the basis: it is an assumption like any other, and
        # without it the reader cannot get back to the USD engineering estimate.
        rate = getattr(result, "exchange_rate", 1.0)
        src = getattr(result, "exchange_rate_source", "unspecified")
        rows.insert(3, ("Exchange rate",
                        f"1 USD = {rate:g} {result.currency} ({src}); applied to "
                        f"the finished USD estimate, which is unchanged"))
    if f.preset:
        rows.insert(5, ("Finance basis", f.preset))
    if f.debt_frac:
        rows.append(("Debt", f"{f.debt_frac:.0%} at {f.debt_interest_rate:.2%} "
                             f"over {f.debt_term_years} years"))
    return rows


# ============================================================================
# Text
# ============================================================================
def to_text(project, result) -> str:
    """Console report: assumptions, then the full cascade, then the answer."""
    out = ["=" * 72, f"  {project.name}", "=" * 72, "", "BASIS OF ESTIMATE", "-" * 72]
    for k, v in assumptions_table(project, result):
        out.append(f"  {k:<26} {v}")
    out += ["", result.report()]
    if result.cash_flow is not None:
        out += ["", "CASH FLOW", result.cash_flow.table(max_rows=16)]
    if result.notes:
        out += ["", "NOTES"] + [f"  - {n}" for n in result.notes]
    return "\n".join(out)


# ============================================================================
# Markdown
# ============================================================================
def _md_table(headers: list[str], rows: list[list], align: str = "l") -> str:
    sep = {"l": ":---", "r": "---:", "c": ":---:"}[align]
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "| " + " | ".join(sep for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def to_markdown(project, result, include_equipment: bool = True,
                include_method: bool = True) -> str:
    """
    Markdown report, suitable for a README or a notebook cell.

    ``include_method`` appends the method appendix — the equations used, with
    this run's numbers in them.
    """
    cur = result.currency
    out = [f"# {project.name}", ""]
    if project.description:
        out += [project.description, ""]
    out += [f"**{result.product} cost: {result.unit_cost:,.4g} {cur}/{result.unit}**"
            f"  ({result.method} method)", "", "## Basis of estimate", "",
            _md_table(["Item", "Value"],
                      [[k, v] for k, v in assumptions_table(project, result)]), ""]

    out += ["## Capital", "",
            _md_table(["Level", f"{cur}"],
                      [["Bare erected cost (BEC)", f"{result.capital.bec:,.0f}"],
                       ["EPC cost (EPCC)", f"{result.capital.epcc:,.0f}"],
                       ["Total plant cost (TPC)", f"{result.capital.tpc:,.0f}"],
                       ["Total overnight cost (TOC)", f"{result.capital.toc:,.0f}"],
                       [f"Total as-spent capital (TASC, "
                        f"x{result.capital.tasc_toc_factor:.3f})",
                        f"{result.capital.tasc:,.0f}"]], align="r"), ""]

    if include_equipment and result.equipment_rows:
        # Purchased and installed, side by side. They differ by a factor of two
        # to four, and a schedule showing only the first invites a reader to
        # add it up and call the total a plant.
        out += ["## Equipment", "",
                _md_table(["Tag", "Item", "Size", "Unit", "n",
                           f"Purchased, {cur}", f"Installed, {cur}"],
                          [[r["tag"], (r.get("name") or r["description"])[:40],
                            f"{r['size']:,.4g}", r["size_unit"], r["quantity"],
                            "—" if r["installed"] else f"{r['cost']:,.0f}",
                            f"{r.get('installed_cost', r['cost']):,.0f}"]
                           for r in result.equipment_rows]), "",
                f"Purchased equipment total: **{result.purchased_equipment_cost:,.0f} "
                f"{cur}**, and a bare erected cost of **{result.bec:,.0f} {cur}** "
                + (f"— installed item by item from its equipment type, "
                   f"x{result.installation_factor:.3f} across the list."
                   if project.capital.installation_method == "type"
                   else f"at an installation factor of "
                        f"x{result.installation_factor:.3f}.")
                + " A dash means the price entered already included "
                  "installation.", ""]
        recorded = [r for r in result.equipment_rows if r.get("parameter_summary")]
        if recorded:
            out += ["### Process parameters", "",
                    "Recorded against each item. They do not enter the costing — "
                    "the size above does — and are given here as the basis of "
                    "the consumption figures below.", "",
                    _md_table(["Tag", "Parameters"],
                              [[r["tag"], r["parameter_summary"]]
                               for r in recorded]), ""]

    if getattr(result, "equipment_utilities", None):
        rows = result.equipment_utilities
        out += ["## Utility consumption by equipment", "",
                "Entered against the item that incurs it, priced here, and "
                "included in the operating cost above. Rates are for the "
                "running units; installed spares are excluded. An hourly rate "
                "is quoted as a draw and the price per the unit it is metered "
                "in — a compressor is 5,200 kW at a price per kWh.", "",
                _md_table(["Tag", "Utility", "Rate", "Rate unit",
                           f"Price {cur}/unit", f"{cur}/yr"],
                          [[r["tag"], r["utility"], f"{r['plant_rate']:,.4g}",
                            r.get("rate_unit", r["unit"]),
                            f"{r['price']:,.4g}/{r['unit']}" if r["priced"] else "—",
                            f"{r['annual_cost']:,.0f}" if r["priced"] else "no price"]
                           for r in rows]
                          + [["**Total**", "", "", "", "",
                              f"**{sum(x['annual_cost'] for x in rows):,.0f}**"]]), ""]

    dist = getattr(result, "utility_distribution", None) or []
    if dist:
        out += ["## Utilities", "",
                "What the plant draws, and what it costs. Quantities are "
                "annual and at the capacity factor above.", "",
                _md_table(["Utility", "Annual quantity", "Unit", "Items",
                           f"Price {cur}/unit", f"{cur}/yr"],
                          [[e["utility"], f"{e['annual_quantity']:,.0f}",
                            e["unit"], str(e["n_items"]),
                            f"{e['price']:,.4g}" if e["priced"] else "no price",
                            f"{e['annual_cost']:,.0f}"] for e in dist]
                          + [["**Total**", "", "", "", "",
                              f"**{sum(e['annual_cost'] for e in dist):,.0f}**"]]),
                ""]

    if getattr(result, "equipment_consumables", None):
        parts = result.equipment_consumables
        out += ["## Replacement parts", "",
                "Parts that are bought again over the plant's life — "
                "electrodes, catalyst, membranes, liners. Each is annualised "
                "over its replacement interval and is already inside the "
                "operating cost below.", "",
                _md_table(["Tag", "Part", "Each", "Replaced", "Per year",
                           f"{cur}/yr"],
                          [[r["tag"], r["part"],
                            f"{r['quantity']:,.4g} {r['unit']}".strip(),
                            r["interval"], f"{r['annual_quantity']:,.4g}",
                            f"{r['annual_cost']:,.0f}"] for r in parts]
                          + [["**Total**", "", "", "", "",
                              f"**{sum(x['annual_cost'] for x in parts):,.0f}**"]]), ""]

    op = result.opex
    out += ["## Operating cost", "",
            _md_table(["Line", f"{cur}/yr"],
                      [[k, f"{v:,.0f}"] for k, v in
                       sorted(op.items.items(), key=lambda kv: -abs(kv[1]))]
                      + [["**Total**", f"**{op.total:,.0f}**"]], align="r"), ""]

    out += ["## Levelised cost build-up", "",
            _md_table(["Component", f"{cur}/{result.unit}"],
                      [[k, f"{v:,.4g}"] for k, v in result.cost_stack().items()]
                      + [["**Total**", f"**{result.unit_cost:,.4g}**"]], align="r"), ""]

    if result.warnings:
        out += ["## Warnings", ""] + [f"- {w}" for w in result.warnings] + [""]
    out += ["## Method notes", ""] + [f"- {n}" for n in result.notes]
    if include_method:
        out += ["", method_appendix_markdown(project, result)]

    # Local import: teakit/__init__.py imports this module on the way to
    # defining these, so at module level it would be circular.
    from . import __author__, __license__, __url__, __version__, citation

    out += ["", "---", "",
            f"Generated by [teakit]({__url__}) {__version__} — capital "
            "correlations from DOE/NETL-2002/1169, capital cascade from "
            "NETL-PUB-22580, cash flow method from NREL/TP-5100-47764.",
            "",
            f"teakit is by {__author__}, under the {__license__} licence. "
            "If this estimate appears in published work, please cite:",
            "",
            f"> {citation('paper')}"]
    return "\n".join(out)


# ============================================================================
# HTML
# ============================================================================
_CSS = """
:root{--ink:#182628;--muted:#5d6f72;--line:#dde5e5;--bg:#fbfbf9;--card:#fff;
--accent:#1b6b73;--amber:#d98324}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:17px;margin:38px 0 12px;padding-bottom:7px;
border-bottom:2px solid var(--accent);letter-spacing:.02em;text-transform:uppercase}
.sub{color:var(--muted);margin:0 0 26px;font-size:13px}
.headline{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--amber);
padding:18px 22px;margin:22px 0 8px;border-radius:3px}
.headline .v{font-size:32px;font-weight:650;letter-spacing:-.02em}
.headline .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
table{width:100%;border-collapse:collapse;font-size:13.5px;background:var(--card)}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
font-weight:600;background:#f4f7f7}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.total td{font-weight:650;border-top:2px solid var(--accent);background:#f4f7f7}
.fig{background:var(--card);border:1px solid var(--line);border-radius:3px;
padding:8px;margin:16px 0}
.warn{background:#fdf6ec;border-left:3px solid var(--amber);padding:10px 14px;
margin:8px 0;font-size:13.5px}
.note{color:var(--muted);font-size:13px;margin:5px 0}
pre.eqn{background:#f4f7f7;border:1px solid var(--line);border-left:3px solid
var(--accent);border-radius:3px;padding:9px 12px;margin:4px 0 12px;
font-size:13px;overflow-x:auto;white-space:pre-wrap}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
color:var(--muted);font-size:12px}
@media print{body{background:#fff}.wrap{padding:0}.fig{break-inside:avoid}}
"""


def _bare(url: str) -> str:
    """``https://example.com/x`` -> ``example.com/x``."""
    return url.split("://", 1)[-1]


def _html_table(headers, rows, numeric_from=1) -> str:
    h = "".join(f'<th class="{"n" if i >= numeric_from else ""}">{escape(str(x))}</th>'
                for i, x in enumerate(headers))
    body = []
    for r in rows:
        cls = ' class="total"' if str(r[0]).startswith("**") else ""
        cells = "".join(
            f'<td class="{"n" if i >= numeric_from else ""}">'
            f'{escape(str(c).replace("**", ""))}</td>' for i, c in enumerate(r))
        body.append(f"<tr{cls}>{cells}</tr>")
    return f"<table><thead><tr>{h}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def to_html(project, result, chart_specs: dict | None = None,
            dark: bool = False) -> str:
    """
    A standalone HTML report with inline SVG figures.

    No external resources of any kind: the file opens from a USB stick on a
    machine with no network, which is the situation you are in more often than
    the tooling assumes.

    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import products
    >>> p = Project(dollar_year=2025, method="fcr")
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.products.products = [products.Product("widget", 15_000, "tonne")]
    >>> "<svg" in to_html(p, p.run())
    True
    """
    cur, unit = result.currency, result.unit
    specs = chart_specs if chart_specs is not None else _charts.default_charts(result)
    o = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>",
         f"<meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>{escape(project.name)} — techno-economic analysis</title>",
         f"<style>{_CSS}</style></head><body><div class='wrap'>",
         f"<h1>{escape(project.name)}</h1>",
         f"<p class='sub'>Techno-economic analysis &middot; {date.today().isoformat()} "
         f"&middot; {result.dollar_year} {cur} &middot; {escape(project.location)}</p>"]
    if project.description:
        o.append(f"<p>{escape(project.description)}</p>")

    o += [f"<div class='headline'><div class='l'>Levelised cost of "
          f"{escape(result.product)}</div>"
          f"<div class='v'>{result.unit_cost:,.4g} <span style='font-size:16px'>"
          f"{cur}/{escape(unit)}</span></div>"
          f"<div class='note'>{escape(result.method)} method &middot; "
          f"{result.annual_production:,.0f} {escape(unit)}/yr &middot; "
          f"TOC {result.capital.toc:,.0f} {cur}</div></div>"]

    for w in result.warnings:
        o.append(f"<div class='warn'>{escape(w)}</div>")

    o.append("<h2>Basis of estimate</h2>")
    o.append(_html_table(["Item", "Value"], assumptions_table(project, result),
                         numeric_from=99))

    o.append("<h2>Capital cost</h2>")
    c = result.capital
    o.append(_html_table(
        ["Level", cur],
        [["Bare erected cost (BEC)", f"{c.bec:,.0f}"],
         ["+ EPC contractor services", f"{c.epc_fee:,.0f}"],
         ["= EPC cost (EPCC)", f"{c.epcc:,.0f}"],
         ["+ process contingency", f"{c.process_contingency:,.0f}"],
         ["+ project contingency", f"{c.project_contingency:,.0f}"],
         ["= Total plant cost (TPC)", f"{c.tpc:,.0f}"],
         ["+ owner's costs", f"{c.total_owners_cost:,.0f}"],
         ["**= Total overnight cost (TOC)", f"{c.toc:,.0f}"],
         [f"x TASC/TOC ({c.tasc_toc_factor:.4f})", f"{c.tasc:,.0f}"]]))
    for key in ("capex_waterfall", "equipment_share", "section_share",
                "type_share"):
        if key in specs:
            o.append(f"<div class='fig'>{specs[key].svg(920, 400, dark)}</div>")

    o.append("<h2>Equipment list</h2>")
    o.append("<p class='note'>Purchased cost is FOB, for every unit of the item. "
             "Installed cost is the item's share of the bare erected cost — "
             + ("purchased cost times the factor its equipment type carries, "
                f"which averages x{result.installation_factor:.3f} across this "
                "list."
                if project.capital.installation_method == "type"
                else f"purchased cost times x{result.installation_factor:.3f}.")
             + " A dash under purchased means the price entered already "
               "included installation, so it enters the cascade at BEC "
               "untouched.</p>")
    o.append(_html_table(
        ["Tag", "Item", "Size", "Unit", "n",
         f"Purchased, {cur}", f"Installed, {cur}"],
        [[r["tag"], (r.get("name") or r["description"])[:44],
          f"{r['size']:,.4g}", r["size_unit"], r["quantity"],
          "&mdash;" if r["installed"] else f"{r['cost']:,.0f}",
          f"{r.get('installed_cost', r['cost']):,.0f}"]
         for r in result.equipment_rows]
        + [["**Purchased equipment total, and bare erected cost", "", "", "", "",
            f"{result.purchased_equipment_cost:,.0f}",
            f"{result.bec:,.0f}"]], numeric_from=2))

    recorded = [r for r in result.equipment_rows if r.get("parameter_summary")]
    if recorded:
        o.append("<h3>Process parameters</h3>")
        o.append("<p class='note'>Recorded against each item. They do not enter "
                 "the costing — the size above does — and are given here as the "
                 "basis of the consumption figures that follow.</p>")
        o.append(_html_table(["Tag", "Parameters"],
                             [[r["tag"], r["parameter_summary"]]
                              for r in recorded], numeric_from=99))

    if getattr(result, "equipment_utilities", None):
        eu = result.equipment_utilities
        o.append("<h2>Utility consumption by equipment</h2>")
        o.append("<p class='note'>Entered against the item that incurs it and "
                 "included in the operating cost above, so the utility bill can "
                 "be traced to the machines that cause it. Rates are for the "
                 "running units; installed spares are excluded. An hourly rate "
                 "is quoted as a draw and the price per the unit it is metered "
                 "in &mdash; a compressor is 5,200 kW at a price per kWh.</p>")
        o.append(_html_table(
            ["Tag", "Item", "Utility", "Rate", "Rate unit",
             f"Price, {cur}/unit", f"Cost, {cur}/yr"],
            [[r["tag"], r["item"][:34], r["utility"], f"{r['plant_rate']:,.4g}",
              r.get("rate_unit", r["unit"]),
              f"{r['price']:,.4g}/{r['unit']}" if r["priced"] else "—",
              f"{r['annual_cost']:,.0f}" if r["priced"] else "no price"]
             for r in eu]
            + [["**Total from equipment", "", "", "", "", "",
                f"{sum(x['annual_cost'] for x in eu):,.0f}"]], numeric_from=3))

    if getattr(result, "equipment_consumables", None):
        parts = result.equipment_consumables
        o.append("<h2>Replacement parts</h2>")
        o.append("<p class='note'>Parts bought again over the plant's life. "
                 "Each is annualised over its replacement interval — a set "
                 "lasting 18 months costs two-thirds of a set a year — and is "
                 "already inside the operating cost below.</p>")
        o.append(_html_table(
            ["Tag", "Item", "Part", "Each", "Replaced", "Per year",
             f"Cost, {cur}/yr"],
            [[r["tag"], r["item"][:30], r["part"],
              f"{r['quantity']:,.4g} {r['unit']}".strip(), r["interval"],
              f"{r['annual_quantity']:,.4g}", f"{r['annual_cost']:,.0f}"]
             for r in parts]
            + [["**Total replacement parts", "", "", "", "", "",
                f"{sum(x['annual_cost'] for x in parts):,.0f}"]], numeric_from=5))

    o.append("<h2>Operating cost</h2>")
    op = result.opex
    rows = [[k, f"{v:,.0f}"] for k, v in
            sorted(op.variable_items.items(), key=lambda kv: -abs(kv[1]))]
    rows.append(["**Subtotal variable", f"{op.variable_total:,.0f}"])
    rows += [[k, f"{v:,.0f}"] for k, v in
             sorted(op.fixed_items.items(), key=lambda kv: -abs(kv[1]))]
    rows.append(["**Subtotal fixed", f"{op.fixed_total:,.0f}"])
    rows.append(["**Total annual operating cost", f"{op.total:,.0f}"])
    o.append(_html_table(["Line", f"{cur}/yr"], rows))
    for key in ("opex_breakdown", "opex_by_category", "capex_opex_split"):
        if key in specs:
            o.append(f"<div class='fig'>{specs[key].svg(920, 400, dark)}</div>")

    # ---- utilities -------------------------------------------------------
    # A section of its own, because it answers a different question from
    # everything above it: not what the plant costs, but what it consumes and
    # which machines consume it.
    dist = getattr(result, "utility_distribution", None) or []
    if dist:
        o.append("<h2>Utilities</h2>")
        o.append("<p class='note'>What the plant draws, and where it goes. "
                 "Quantities are annual and at the capacity factor above. "
                 "A line entered on the operating-cost panel rather than "
                 "against a machine appears as one unattributable block, "
                 "which is the honest way to show it.</p>")
        o.append(_html_table(
            ["Utility", "Annual quantity", "Unit", "Items",
             f"Price, {cur}/unit", f"Cost, {cur}/yr", "% of variable cost"],
            [[e["utility"], f"{e['annual_quantity']:,.0f}", e["unit"],
              str(e["n_items"]),
              f"{e['price']:,.4g}" if e["priced"] else "no price",
              f"{e['annual_cost']:,.0f}",
              f"{e['annual_cost'] / (result.opex.variable_total or 1) * 100:,.1f}%"]
             for e in dist]
            + [["**Total", "", "", "", "",
                f"{sum(e['annual_cost'] for e in dist):,.0f}", "100.0%"]],
            numeric_from=1))

        # The utility with the most machines behind it gets its contributors
        # spelled out — not simply the dearest, which on a fuels plant is the
        # feedstock and is one unattributable line. Ties go to the dearer of
        # them, since `dist` is already in cost order.
        top = max(dist, key=lambda e: sum(1 for i in e["items"]
                                          if i["source"] == "equipment"))
        if len(top["items"]) > 1:
            o.append(f"<h3>{escape(top['utility'])} — who draws it</h3>")
            o.append(_html_table(
                ["Item", "Section", "Type", "Rate", "Unit",
                 f"Annual, {escape(top['unit'])}", "Share", f"Cost, {cur}/yr"],
                [[(i["tag"] or i["label"]), i["section"], i["equipment_type"],
                  f"{i['rate']:,.4g}", i["rate_unit"],
                  f"{i['annual_quantity']:,.0f}",
                  f"{i['quantity_share'] * 100:,.1f}%",
                  f"{i['annual_cost']:,.0f}"] for i in top["items"]],
                numeric_from=3))

        for key, spec in specs.items():
            if key == "utility_totals" or key.startswith("utility_"):
                o.append(f"<div class='fig'>{spec.svg(920, 400, dark)}</div>")

    o.append("<h2>Levelised cost</h2>")
    o.append(_html_table(
        ["Component", f"{cur}/{unit}"],
        [[k, f"{v:,.4g}"] for k, v in result.cost_stack().items()]
        + [[f"**{result.product} cost", f"{result.unit_cost:,.4g}"]]))
    if "cost_stack" in specs:
        o.append(f"<div class='fig'>{specs['cost_stack'].svg(920, 360, dark)}</div>")

    if result.cash_flow is not None:
        o.append("<h2>Cash flow</h2>")
        cf = result.cash_flow
        o.append(f"<p class='note'>NPV {cf.npv:,.0f} {cur} at "
                 f"{project.finance.discount_rate:.2%}; IRR "
                 f"{(cf.irr or 0):.2%}"
                 + (f"; discounted payback year {cf.payback_year:.1f}"
                    if cf.payback_year is not None else "") + ".</p>")
        if "cash_flow" in specs:
            o.append(f"<div class='fig'>{specs['cash_flow'].svg(920, 380, dark)}</div>")
        o.append(_html_table(
            ["Year", "Capex", "Revenue", "Opex", "Deprec.", "Tax", "Net CF", "Cum. DCF"],
            [[cf.years[i], f"{-cf.capex[i]:,.0f}", f"{cf.revenue[i]:,.0f}",
              f"{-cf.opex[i]:,.0f}", f"{cf.depreciation[i]:,.0f}",
              f"{-cf.tax[i]:,.0f}", f"{cf.net_cash_flow[i]:,.0f}",
              f"{cf.cumulative_dcf[i]:,.0f}"] for i in range(len(cf.years))]))

    extra = {k: v for k, v in specs.items()
             if k not in ("capex_waterfall", "equipment_share", "section_share",
                          "opex_breakdown", "opex_by_category", "capex_opex_split",
                          "cost_stack", "cash_flow")}
    if extra:
        o.append("<h2>Sensitivity</h2>")
        for spec in extra.values():
            o.append(f"<div class='fig'>{spec.svg(920, 420, dark)}</div>")

    o.append(method_appendix_html(project, result))

    o.append("<h2>Method notes</h2><ul>")
    o += [f"<li>{escape(n)}</li>" for n in result.notes]
    o.append("</ul>")
    # Local import, for the reason given in to_markdown.
    from . import CITATION, __author__, __license__, __url__, __version__

    paper = CITATION["paper"]
    o.append(
        "<footer>Generated by teakit. Capital correlations regressed from "
        "DOE/NETL-2002/1169 (Loh, Lyons &amp; White, 2002), Appendix B. Capital "
        "cascade and fixed charge rate from NETL-PUB-22580. Discounted cash flow "
        "method from NREL/TP-5100-47764 (Humbird et al., 2011). Escalation by the "
        "Chemical Engineering Plant Cost Index. This is an AACE Class 5-4 "
        "estimate and is not investment advice."
        # Bare text, not links: the report has to stay self-contained, and a
        # DOI cites perfectly well without a scheme in front of it.
        f"<p>teakit {escape(__version__)} by {escape(__author__)}, under the "
        f"{escape(__license__)} licence — {escape(_bare(__url__))}. "
        "If this estimate appears in published work, please cite: "
        f"{escape(paper['authors'])}. {escape(paper['title'])}. "
        f"<i>{escape(paper['journal'])}</i>, {paper['year']}. "
        f"doi:{escape(paper['doi'])}.</p></footer>")
    o.append("</div></body></html>")
    return "".join(o)


def save_html(project, result, path: str, chart_specs: dict | None = None) -> str:
    html = to_html(project, result, chart_specs)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


# ============================================================================
# Method appendix
# ============================================================================
def method_appendix_markdown(project, result) -> str:
    """
    The equations actually used on this run, with this run's numbers in them.

    Goes at the end of a report because that is where a reviewer looks for it:
    the answer first, then the arithmetic that produced it, in enough detail to
    be reproduced with a calculator.

    >>> from teakit import demo
    >>> p = demo()
    >>> "## Method and calculations" in method_appendix_markdown(p, p.run())
    True
    """
    from . import methods as _methods
    out = ["## Method and calculations", "",
           "The equations actually used on this run, with this run's own "
           "numbers substituted. Only the methods selected are set out in "
           "full; the alternatives are named so it is clear a choice was "
           "made.", ""]
    for i, sec in enumerate(_methods.explain(project, result), start=1):
        out += [f"### {i}. {sec['title']}", "", sec["summary"], ""]
        if sec["source"]:
            out += [f"*Source: {sec['source']}*", ""]
        for eq in sec["equations"]:
            out += [f"**{eq['label']}**", "", "```", eq["expr"], "```", ""]
        if sec["symbols"]:
            out += [_md_table(["Symbol", "Meaning", "This run"],
                              [[x["sym"], x["meaning"], x["value"]]
                               for x in sec["symbols"]]), ""]
        if sec["steps"]:
            out += [_md_table(["Step", "Value"],
                              [[x["label"], x["detail"]]
                               for x in sec["steps"]], align="l"), ""]
        for n in sec["notes"]:
            out += [f"> {n}", ""]
    return "\n".join(out)


def method_appendix_html(project, result) -> str:
    """The same appendix as an HTML fragment, for :func:`to_html`."""
    from . import methods as _methods
    o = ['<h2 id="method">Method and calculations</h2>',
         "<p class='note'>The equations actually used on this run, with this "
         "run's own numbers substituted, so the result can be reproduced with "
         "a calculator. Only the methods selected are set out in full; the "
         "alternatives are named so it is clear a choice was made.</p>"]
    for i, sec in enumerate(_methods.explain(project, result), start=1):
        o.append(f"<h3>{i}. {escape(sec['title'])}</h3>")
        o.append(f"<p>{escape(sec['summary'])}</p>")
        if sec["source"]:
            o.append(f"<p class='note'>Source: {escape(sec['source'])}</p>")
        for eq in sec["equations"]:
            o.append(f"<p class='note'>{escape(eq['label'])}</p>"
                     f"<pre class='eqn'>{escape(eq['expr'])}</pre>")
        if sec["symbols"]:
            o.append(_html_table(
                ["Symbol", "Meaning", "This run"],
                [[x["sym"], x["meaning"], x["value"]] for x in sec["symbols"]],
                numeric_from=99))
        if sec["steps"]:
            o.append(_html_table(
                ["Step", "Value"],
                [[x["label"], x["detail"]] for x in sec["steps"]],
                numeric_from=1))
        for n in sec["notes"]:
            o.append(f"<div class='warn'>{escape(str(n))}</div>")
    return "".join(o)


# ============================================================================
# CSV
# ============================================================================
def _csv(headers, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue()


def equipment_csv(result) -> str:
    """Equipment list as CSV, with the full audit trail per line.

    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import products
    >>> p = Project(dollar_year=2025, method="fcr")
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.products.products = [products.Product("w", 100, "t")]
    >>> equipment_csv(p.run()).splitlines()[0].split(",")[0]
    'tag'
    """
    return _csv(
        ["tag", "name", "description", "category", "mode", "size", "size_unit",
         "exponent", "base_size", "base_cost_basis_year", "material",
         "quantity", "unit_cost", "total_cost", "installation_factor",
         "installed_cost", "installed_basis", "section",
         "process_parameters", "utility_cost_per_year",
         "consumable_cost_per_year", "replacement_parts", "notes"],
        [[r["tag"], r.get("name", ""), r["description"], r.get("category", ""),
          r["mode"], r["size"],
          r["size_unit"], f"{r['exponent']:.4f}", r["base_size"],
          f"{r['base_cost']:.2f}", r["material"], r["quantity"],
          f"{r['unit_cost']:.2f}", f"{r['cost']:.2f}",
          f"{r.get('installation_factor', 1.0):.4f}",
          f"{r.get('installed_cost', r['cost']):.2f}", r["installed"],
          r["section"], r.get("parameter_summary", ""),
          f"{r.get('utility_cost', 0.0):.2f}",
          f"{r.get('consumable_cost', 0.0):.2f}",
          r.get("consumable_summary", ""),
          "; ".join(r["notes"])] for r in result.equipment_rows])


def equipment_utility_csv(result) -> str:
    """
    What each equipment item consumes, priced, one row per line.

    >>> from teakit.project import Project, EquipmentItem, EquipmentUtility
    >>> from teakit import products
    >>> p = Project(dollar_year=2025, method="fcr")
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000,
    ...     utilities=[EquipmentUtility("cooling water", 120.0)])]
    >>> p.products.products = [products.Product("w", 100, "t")]
    >>> equipment_utility_csv(p.run()).splitlines()[1].split(",")[0]
    'E-101'
    """
    rows = getattr(result, "equipment_utilities", None) or []
    if not rows:
        raise ValueError("no equipment utilities — nothing has a consumption "
                         "recorded against it")
    return _csv(
        # `rate_unit` is what the rate is read in (kW), `unit` what it is
        # priced and totalled in (kWh). They differ on every hourly line and
        # a reader needs both.
        ["tag", "item", "section", "utility", "category", "rate_per_unit",
         "per_unit", "running_units", "plant_rate", "rate_unit",
         "quantity_unit", "rate_basis",
         "follows_capacity_factor", "price", "price_source",
         "annual_quantity", "annual_cost", "opex_line", "note"],
        [[r["tag"], r["item"], r["section"], r["utility"], r["category"],
          f"{r['rate']:.6g}", r["per_unit"], r["running_units"],
          f"{r['plant_rate']:.6g}", r.get("rate_unit", r["unit"]),
          r["unit"], r["basis"],
          r["scales_with_rate"],
          f"{r['price']:.6g}" if r["priced"] else "",
          r["price_source"], f"{r['annual_quantity']:.6g}",
          f"{r['annual_cost']:.2f}", r["line"], r["note"]] for r in rows])


def cash_flow_csv(result) -> str:
    """Year-by-year cash flow as CSV."""
    cf = result.cash_flow
    if cf is None:
        raise ValueError("no cash flow — run with method='dcf'")
    return _csv(
        ["year", "capex", "revenue", "opex", "depreciation", "interest",
         "principal", "taxable_income", "tax", "net_cash_flow",
         "discounted_cash_flow", "cumulative_dcf"],
        [[cf.years[i], f"{cf.capex[i]:.2f}", f"{cf.revenue[i]:.2f}",
          f"{cf.opex[i]:.2f}", f"{cf.depreciation[i]:.2f}",
          f"{cf.interest[i]:.2f}", f"{cf.principal[i]:.2f}",
          f"{cf.taxable_income[i]:.2f}", f"{cf.tax[i]:.2f}",
          f"{cf.net_cash_flow[i]:.2f}", f"{cf.discounted_cash_flow[i]:.2f}",
          f"{cf.cumulative_dcf[i]:.2f}"] for i in range(len(cf.years))])


def opex_csv(result) -> str:
    """Operating cost sheet as CSV."""
    rows = []
    for k, v in result.opex.variable_items.items():
        q = result.opex.quantities.get(k, ("", ""))
        rows.append(["variable", k, q[0], q[1], f"{v:.2f}"])
    for k, v in result.opex.fixed_items.items():
        rows.append(["fixed", k, "", "", f"{v:.2f}"])
    rows.append(["total", "TOTAL ANNUAL OPERATING COST", "", "",
                 f"{result.opex.total:.2f}"])
    return _csv(["class", "line", "annual_quantity", "unit", "annual_cost"], rows)


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
