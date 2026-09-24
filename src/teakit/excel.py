"""
teakit.excel — The estimate as a working Excel workbook.
=========================================================

Not a dump of numbers. A sectioned, colour-coded workbook in which the parts
that are arithmetic are **live formulas**, so a reviewer can change an
equipment size, a contingency or a utility price in Excel and watch the
estimate move — and the parts that are not arithmetic are clearly marked as
stamped values, so nobody mistakes a frozen number for a live one.

The convention, stated on the cover sheet and followed everywhere:

======================  ====================================================
amber cell, boxed       an **input**. Change it; the workbook recomputes.
plain cell              **computed** by a formula from the inputs.
grey italic cell        a **stamped value** from the teakit engine that Excel
                        cannot recompute — the DCF price solve, the MACRS
                        schedule, the per-item distributive installation
                        build-up.
======================  ====================================================

That last row is the honest part. Re-implementing the whole engine in
spreadsheet formulas would guarantee that the workbook and teakit eventually
disagree, and a cost estimate that disagrees with itself is worse than one
that says plainly where it stops.

Sheets, in order: Cover, Basis, Equipment, Capital, Operating cost, Products,
Cash flow (dcf runs only), Results, and Method — the last being the equations
actually used, with this run's numbers substituted.

    >>> import teakit
    >>> p = teakit.demo("methanol")
    >>> to_xlsx(p, p.run())[:2] == b"PK"
    True
"""

from __future__ import annotations

from datetime import date

from . import methods as _methods
from . import report as _report
from .xlsx import Workbook, cell_ref, quote_sheet

__all__ = ["to_xlsx", "build_workbook"]

# ---------------------------------------------------------------------------
# palette — the application's own colours, so screen and workbook agree
# ---------------------------------------------------------------------------
INK = "13211F"
PETROL = "0F5C63"
PETROL_LT = "D9E7E8"
AMBER = "B5651D"
AMBER_LT = "FDF3E6"
PAPER = "F2F5F0"
BAND = "E8EFE8"
RULE = "C6D0C6"
MUTED = "6C807D"
RED = "8F2D20"

TAB = {"cover": PETROL, "basis": "4A7C59", "equipment": "1B6B73",
       "capital": "3D5A80", "opex": "D98324", "utilities": "C07B2A",
       "products": "8C4A5F",
       "cashflow": "6B4E71", "results": "2A9D8F", "method": "A68A3F"}


def _q(sheet, local: str) -> str:
    """A local reference like ``B7`` made cross-sheet: ``Capital!$B$7``."""
    letters = "".join(ch for ch in local if ch.isalpha())
    digits = "".join(ch for ch in local if ch.isdigit())
    return f"{quote_sheet(sheet.name)}!${letters}${digits}"


class _Fmt:
    """Every style the workbook uses, interned once against one workbook."""

    def __init__(self, wb: Workbook, sym: str):
        s = wb.style
        money = f'"{sym}"#,##0'
        money4 = f'"{sym}"#,##0.0000'
        box = {"all": "thin", "color": RULE}
        tot = {"top": "medium", "bottom": "double", "color": INK}
        amber_box = {"all": "thin", "color": AMBER}

        self.title = s(font={"bold": True, "size": 20, "color": PETROL})
        self.subtitle = s(font={"size": 12, "color": MUTED},
                          align={"wrap": True, "v": "top"})
        self.h1 = s(font={"bold": True, "size": 13, "color": "FFFFFF"},
                    fill=PETROL, align={"v": "center", "indent": 1})
        self.h2 = s(font={"bold": True, "size": 11, "color": INK}, fill=BAND,
                    border={"bottom": "medium", "color": PETROL},
                    align={"v": "center", "indent": 1})
        self.th = s(font={"bold": True, "size": 10, "color": "FFFFFF"},
                    fill=PETROL, border={"all": "thin", "color": PETROL},
                    align={"h": "center", "v": "center", "wrap": True})
        self.thl = s(font={"bold": True, "size": 10, "color": "FFFFFF"},
                     fill=PETROL, border={"all": "thin", "color": PETROL},
                     align={"h": "left", "v": "center", "wrap": True})

        self.label = s(font={"size": 10.5}, border=box, align={"wrap": True})
        self.label_b = s(font={"bold": True, "size": 10.5}, border=box,
                         align={"wrap": True})
        self.text = s(font={"size": 10.5}, border=box,
                      align={"wrap": True, "v": "top"})
        self.wrap = s(font={"size": 10.5}, align={"wrap": True, "v": "top"})
        self.note = s(font={"size": 10, "italic": True, "color": MUTED},
                      align={"wrap": True, "v": "top"})
        self.mono = s(font={"size": 10, "name": "Consolas"}, border=box,
                      align={"wrap": True, "v": "top"})
        self.eqn = s(font={"size": 10.5, "name": "Consolas", "color": PETROL},
                     fill=PAPER, border=box, align={"wrap": True, "v": "top"})

        self.num = s(fmt="#,##0", border=box)
        self.num4 = s(fmt="#,##0.0000", border=box)
        self.money = s(fmt=money, border=box)
        self.money4 = s(fmt=money4, border=box)
        self.pct = s(fmt="0.0%", border=box)
        self.pct2 = s(fmt="0.00%", border=box)

        # inputs — amber, boxed. "You may change this."
        self.in_num = s(fmt="#,##0", fill=AMBER_LT, border=amber_box)
        self.in_num4 = s(fmt="#,##0.0000", fill=AMBER_LT, border=amber_box)
        self.in_money = s(fmt=money, fill=AMBER_LT, border=amber_box)
        self.in_money4 = s(fmt=money4, fill=AMBER_LT, border=amber_box)
        self.in_pct = s(fmt="0.00%", fill=AMBER_LT, border=amber_box)
        self.in_text = s(font={"size": 10.5}, fill=AMBER_LT, border=amber_box)

        # stamped — grey italic. "Excel cannot recompute this."
        self.st_money = s(fmt=money, fill=PAPER, border=box,
                          font={"italic": True, "color": MUTED})
        self.st_money4 = s(fmt=money4, fill=PAPER, border=box,
                           font={"italic": True, "color": MUTED})
        self.st_num = s(fmt="#,##0", fill=PAPER, border=box,
                        font={"italic": True, "color": MUTED})
        self.st_pct = s(fmt="0.00%", fill=PAPER, border=box,
                        font={"italic": True, "color": MUTED})
        self.st_text = s(font={"size": 10.5, "italic": True, "color": MUTED},
                         fill=PAPER, border=box, align={"wrap": True})

        self.tot_lbl = s(font={"bold": True, "size": 11}, fill=BAND, border=tot)
        self.tot_money = s(fmt=money, fill=BAND, border=tot,
                           font={"bold": True, "size": 11})
        self.tot_money4 = s(fmt=money4, fill=BAND, border=tot,
                            font={"bold": True, "size": 11})
        self.tot_num = s(fmt="#,##0", fill=BAND, border=tot,
                         font={"bold": True, "size": 11})
        self.tot_pct = s(fmt="0.0%", fill=BAND, border=tot,
                         font={"bold": True, "size": 11})
        self.sub_lbl = s(font={"bold": True, "size": 10.5}, fill=BAND,
                         border=box)
        self.sub_money = s(fmt=money, fill=BAND, border=box,
                           font={"bold": True, "size": 10.5})
        self.sub_num = s(fmt="#,##0", fill=BAND, border=box,
                         font={"bold": True, "size": 10.5})

        self.hero = s(font={"bold": True, "size": 30, "color": PETROL},
                      align={"h": "center", "v": "center"}, fmt=money4)
        self.hero_lbl = s(font={"bold": True, "size": 10, "color": MUTED},
                          align={"h": "center"})
        self.hero_unit = s(font={"size": 12, "color": INK},
                           align={"h": "center", "wrap": True})

        self.warn = s(font={"size": 10, "color": RED}, fill=AMBER_LT,
                      border={"all": "thin", "color": AMBER},
                      align={"wrap": True, "v": "top"})
        self.legend_in = s(fill=AMBER_LT, border=amber_box)
        self.legend_calc = s(border=box)
        self.legend_st = s(fill=PAPER, border=box)


def _band(sh, fmt, row, text, span, style):
    sh.merge(row, 1, row, span, text, style)
    sh.set_height(row, 26 if style is fmt.h1 else 20)
    return row + 1


def _h1(sh, fmt, row, text, span=8):
    return _band(sh, fmt, row, text, span, fmt.h1)


def _h2(sh, fmt, row, text, span=8):
    return _band(sh, fmt, row, text, span, fmt.h2)


def _prose(sh, fmt, row, text, span=8, height=30):
    sh.merge(row, 1, row, span, text, fmt.note)
    sh.set_height(row, height)
    return row + 1


# ===========================================================================
# Cover
# ===========================================================================
def _cover(wb, fmt, p, res, cur):
    sh = wb.add_sheet("Cover", TAB["cover"])
    sh.show_gridlines = False
    sh.set_width(1, 12)
    sh.set_width(2, 22)
    sh.set_width(3, 16, 8)

    sh.merge(2, 1, 2, 8, p.name or "Untitled project", fmt.title)
    sh.set_height(2, 34)
    sh.merge(3, 1, 3, 8, p.description
             or "Techno-economic analysis on DOE/NETL and NREL methodology",
             fmt.subtitle)
    sh.set_height(3, 30)

    r = 5
    hero_style = wb.style(fill=PETROL_LT,
                          border={"all": "medium", "color": PETROL})
    for rr in range(r, r + 4):
        for cc in range(1, 9):
            sh.write(rr, cc, None, hero_style)
    sh.merge(r, 1, r, 8, "LEVELISED COST", fmt.hero_lbl)
    sh.merge(r + 1, 1, r + 2, 8, res.unit_cost, fmt.hero)
    sh.set_height(r + 1, 26)
    sh.set_height(r + 2, 22)
    sh.merge(r + 3, 1, r + 3, 8,
             f"{res.currency} per {res.unit} of {res.product}  ·  "
             f"{res.method} method  ·  {res.dollar_year} dollars", fmt.hero_unit)
    r += 5

    r = _h2(sh, fmt, r, "AT A GLANCE")
    for label, value, style in [
        ("Total overnight cost (TOC)", res.capital.toc, fmt.money),
        ("Total as-spent capital (TASC)", res.capital.tasc, fmt.money),
        ("Purchased equipment cost", res.purchased_equipment_cost, fmt.money),
        ("Annual operating cost", res.opex.total, fmt.money),
        ("Annual production", res.annual_production, fmt.num),
        ("Equipment items", len(p.equipment), fmt.num),
    ]:
        sh.merge(r, 1, r, 3, label, fmt.label_b)
        sh.merge(r, 4, r, 6, value, style)
        sh.write(r, 7, None, fmt.label)
        sh.write(r, 8, None, fmt.label)
        r += 1
    r += 1

    r = _h2(sh, fmt, r, "HOW TO READ THIS WORKBOOK")
    for style, name, meaning in [
        (fmt.legend_in, "input",
         "Change it. Every formula downstream recomputes."),
        (fmt.legend_calc, "computed",
         "A live formula. Click any cell to see the arithmetic."),
        (fmt.legend_st, "stamped",
         "A value from the teakit engine that Excel cannot recompute — the "
         "DCF price solve, the MACRS schedule, the per-item installation "
         "build-up. Re-run teakit to change these."),
    ]:
        sh.write(r, 1, None, style)
        sh.merge(r, 2, r, 3, name, fmt.label_b)
        sh.merge(r, 4, r, 8, meaning, fmt.wrap)
        sh.set_height(r, 32)
        r += 1
    r += 1

    r = _h2(sh, fmt, r, "CONTENTS")
    for name, what in [
        ("Basis", "dollar-year, location, method — every assumption behind "
                  "the number, with its source"),
        ("Equipment", "the equipment list priced item by item, on live "
                      "power-law formulas"),
        ("Capital", "the NETL ladder from bare erected cost to as-spent "
                    "capital"),
        ("Operating cost", "variable and fixed lines for one operating year"),
        ("Products", "the product slate and how cost is allocated across it"),
        ("Cash flow", "the year-by-year discounted cash flow (dcf runs only)"),
        ("Results", "the cost build-up, the biggest lines, the three methods "
                    "side by side"),
        ("Method", "the equations actually used on this run, with these "
                   "numbers substituted"),
    ]:
        sh.merge(r, 1, r, 3, name, fmt.label_b)
        sh.merge(r, 4, r, 8, what, fmt.wrap)
        r += 1
    r += 1

    r = _prose(sh, fmt, r,
               f"Prepared {date.today().isoformat()} with teakit. Estimate "
               f"class AACE 5-4: -25%/+50% at best. Equipment correlations "
               f"from DOE/NETL-2002/1169 escalated by CEPCI; capital cascade "
               f"per NETL-PUB-22580; cash flow per NREL/TP-5100-47764.",
               8, 44)

    if res.warnings:
        r += 1
        r = _h2(sh, fmt, r, "WARNINGS FROM THIS RUN")
        for w in res.warnings:
            sh.merge(r, 1, r, 8, str(w), fmt.warn)
            sh.set_height(r, 30)
            r += 1
    return sh


# ===========================================================================
# Basis
# ===========================================================================
def _basis(wb, fmt, p, res, cur):
    sh = wb.add_sheet("Basis", TAB["basis"])
    sh.show_gridlines = False
    sh.set_width(1, 34)
    sh.set_width(2, 20)
    sh.set_width(3, 14, 6)

    r = _h1(sh, fmt, 1, "BASIS OF ESTIMATE", 6)
    r = _prose(sh, fmt, r,
               "A levelised cost without its basis is not a result. This is "
               "what a reviewer checks first.", 6, 20)
    r += 1

    sh.write(r, 1, "Assumption", fmt.thl)
    sh.merge(r, 2, r, 6, "Value", fmt.thl)
    r += 1
    for label, value in _report.assumptions_table(p, res):
        sh.write(r, 1, label, fmt.label_b)
        sh.merge(r, 2, r, 6, str(value), fmt.text)
        sh.set_height(r, 15 if len(str(value)) < 72 else 30)
        r += 1
    r += 1

    r = _h2(sh, fmt, r,
            "KEY INPUTS — CHANGE THESE AND THE WORKBOOK RECOMPUTES", 6)
    sh.write(r, 1, "Input", fmt.thl)
    sh.write(r, 2, "Value", fmt.th)
    sh.merge(r, 3, r, 6, "Note", fmt.thl)
    r += 1

    f, c, o = p.finance, p.capital, p.opex
    cells: dict[str, str] = {}
    for key, label, value, style, note in [
        ("loc", "Location factor", p.effective_location_factor(), fmt.in_num4,
         f"US Gulf Coast = 1.00; this run uses {p.location}"),
        ("epc", "EPC services, % of BEC", c.epc_fee_frac, fmt.in_pct,
         "NETL uses 15-20%"),
        ("proc", "Process contingency, % of BEC", c.process_contingency_frac,
         fmt.in_pct, "technology immaturity"),
        ("proj", "Project contingency, %", c.project_contingency_frac,
         fmt.in_pct, "estimate immaturity; AACE 16R-90 gives 15-30% for a "
                     "budget estimate"),
        ("tasc", "TASC / TOC factor", res.capital.tasc_toc_factor, fmt.in_num4,
         f"{c.basis} basis over a {f.construction_years}-year build"),
        ("hours", "Operating hours per year", o.operating_hours, fmt.in_num,
         "hours at rate"),
        ("cf", "Capacity factor", o.capacity_factor, fmt.in_pct,
         "fraction of nameplate actually produced"),
        ("disc", "Discount rate", f.discount_rate, fmt.in_pct, f.basis),
        ("tax", "Effective tax rate", f.tax_rate, fmt.in_pct,
         "federal plus state"),
        ("life", "Plant life, years", f.plant_life_years, fmt.in_num,
         "capital recovery period"),
        ("prod", "Annual production", res.annual_production, fmt.in_num,
         f"{res.unit} of {res.product}"),
    ]:
        sh.write(r, 1, label, fmt.label_b)
        sh.write(r, 2, value, style)
        cells[key] = _q(sh, cell_ref(r, 2))
        sh.merge(r, 3, r, 6, note, fmt.note)
        r += 1

    if res.charge_rate:
        sh.write(r, 1, res.charge_rate_name or "Charge rate", fmt.label_b)
        sh.write(r, 2, res.charge_rate, fmt.in_pct)
        cells["charge_rate"] = _q(sh, cell_ref(r, 2))
        sh.merge(r, 3, r, 6,
                 "computed by teakit from the discount rate, the tax rate and "
                 "the depreciation schedule", fmt.note)
        r += 1
    r += 1

    _prose(sh, fmt, r,
           "Changing an input here moves the Capital, Operating cost and "
           "Results sheets. It does not re-solve the DCF price — that needs "
           "the iterative cash-flow model, so re-run teakit for it.", 6, 30)
    return sh, cells


# ===========================================================================
# Equipment
# ===========================================================================
def _equipment(wb, fmt, p, res, cur, basis):
    sh = wb.add_sheet("Equipment", TAB["equipment"])
    for col, w in enumerate([11, 34, 11, 13, 15, 13, 14, 10, 11, 7, 15, 16,
                             14, 10, 44], start=1):
        sh.set_width(col, w)

    r = _h1(sh, fmt, 1, "EQUIPMENT LIST", 15)
    r = _prose(sh, fmt, r,
               "Cost = base cost x (size / base size) ^ exponent x factor, "
               "then x quantity. The amber columns are yours: change a size, "
               "an exponent or a quantity and the cost recomputes. 'Factor' "
               "combines CEPCI escalation to the dollar-year with the "
               "material and location factors.", 15, 32)

    head = ["Tag", "Description", "Basis", "Size", "Size unit", "Base size",
            "Base cost", "Exponent", "Factor", "Qty", f"Unit cost ({cur})",
            f"Total cost ({cur})", "Section", "Installed?", "Notes"]
    hrow = r
    sh.write_row(hrow, 1, head, style=fmt.th)
    sh.set_height(hrow, 32)
    r += 1

    first = r
    for row in res.equipment_rows:
        base_cost = row.get("base_cost") or 0.0
        base_size = row.get("base_size") or 0.0
        size = row.get("size") or 0.0
        n = row.get("exponent") or 0.0
        qty = row.get("quantity") or 1
        unit_cost = row.get("unit_cost") or 0.0
        mode = row.get("mode", "catalogue")

        # One combined adjustment factor — escalation x material x location —
        # derived so the spreadsheet formula reproduces the engine's unit cost
        # exactly rather than approximately.
        scaled = (base_cost if (mode == "direct" or base_size <= 0 or size <= 0)
                  else base_cost * (size / base_size) ** n)
        factor = (unit_cost / scaled) if scaled else 1.0

        sh.write(r, 1, row["tag"], fmt.label_b)
        sh.write(r, 2, row.get("name") or row.get("description", ""), fmt.label)
        sh.write(r, 3, mode, fmt.label)
        sh.write(r, 4, size, fmt.in_num4)
        sh.write(r, 5, row.get("size_unit", ""), fmt.label)
        sh.write(r, 6, base_size, fmt.in_num4)
        sh.write(r, 7, base_cost, fmt.in_money)
        sh.write(r, 8, n, fmt.in_num4)
        sh.write(r, 9, factor, fmt.in_num4)
        sh.write(r, 10, qty, fmt.in_num)

        c_size, c_bsize, c_bcost, c_exp, c_fac = (
            cell_ref(r, 4), cell_ref(r, 6), cell_ref(r, 7),
            cell_ref(r, 8), cell_ref(r, 9))
        if mode == "direct" or base_size <= 0:
            sh.write(r, 11, f"={c_bcost}*{c_fac}", fmt.money)
        else:
            # The IF guards a cleared base size, which would otherwise show
            # #DIV/0! the moment somebody empties the cell.
            sh.write(r, 11,
                     f"=IF({c_bsize}=0,{c_bcost}*{c_fac},"
                     f"{c_bcost}*({c_size}/{c_bsize})^{c_exp}*{c_fac})",
                     fmt.money)
        sh.write(r, 12, f"={cell_ref(r, 11)}*{cell_ref(r, 10)}", fmt.money)
        sh.write(r, 13, row.get("section", ""), fmt.label)
        sh.write(r, 14, "yes" if row.get("installed") else "no", fmt.label)
        notes = list(row.get("notes") or [])
        if row.get("parameter_summary"):
            notes.append(row["parameter_summary"])
        sh.write(r, 15, "; ".join(notes), fmt.note)
        r += 1
    last = r - 1

    totals = {}
    if last >= first:
        col_L = f"{cell_ref(first, 12)}:{cell_ref(last, 12)}"
        col_N = f"{cell_ref(first, 14)}:{cell_ref(last, 14)}"
        # Purchased and already-installed costs must not share a subtotal —
        # mixing them is the error the whole application is built to prevent,
        # so the split is on the face of the sheet and stays live: flip a row's
        # Installed? flag and both subtotals move.
        for label, formula, style, key, note in [
            ("PURCHASED EQUIPMENT COST",
             f'=SUMIF({col_N},"no",{col_L})', fmt.sub_money, "purchased",
             "goes through the installation factors"),
            ("Already-installed direct cost",
             f'=SUMIF({col_N},"yes",{col_L})', fmt.sub_money, "installed",
             "enters the capital cascade at BEC, unmultiplied"),
            ("TOTAL EQUIPMENT COST", f"=SUM({col_L})", fmt.tot_money, "grand",
             "both of the above"),
        ]:
            style_lbl = fmt.tot_lbl if key == "grand" else fmt.sub_lbl
            sh.merge(r, 1, r, 11, label, style_lbl)
            sh.write(r, 12, formula, style)
            sh.write(r, 13, None, style_lbl)
            sh.write(r, 14, None, style_lbl)
            sh.write(r, 15, note, fmt.note)
            totals[key] = _q(sh, cell_ref(r, 12))
            r += 1
        sh.data_bar(col_L, PETROL)
        sh.autofilter = f"{cell_ref(hrow, 1)}:{cell_ref(last, 15)}"
    sh.freeze = (hrow, 2)
    total_ref = totals.get("grand")
    r += 2

    # -- summary by plant section ---------------------------------------
    sections: dict[str, list[int]] = {}
    for i, row in enumerate(res.equipment_rows):
        sections.setdefault(row.get("section") or "unassigned",
                            []).append(first + i)

    if sections and total_ref:
        r = _h2(sh, fmt, r, "SUMMARY BY PLANT SECTION", 15)
        sh.write_row(r, 1, ["Section", "Items", f"Purchased cost ({cur})",
                            "% of total"], style=fmt.th)
        r += 1
        sec_first = r
        for name, rows_in in sections.items():
            sh.write(r, 1, name, fmt.label_b)
            sh.write(r, 2, len(rows_in), fmt.num)
            sh.write(r, 3, "=" + "+".join(cell_ref(i, 12) for i in rows_in),
                     fmt.money)
            sh.write(r, 4, f"={cell_ref(r, 3)}/{total_ref}", fmt.pct)
            r += 1
        sec_last = r - 1
        sh.write(r, 1, "TOTAL", fmt.tot_lbl)
        sh.write(r, 2, len(res.equipment_rows), fmt.tot_num)
        sh.write(r, 3, f"=SUM({cell_ref(sec_first, 3)}:"
                       f"{cell_ref(sec_last, 3)})", fmt.tot_money)
        sh.write(r, 4, f"=SUM({cell_ref(sec_first, 4)}:"
                       f"{cell_ref(sec_last, 4)})", fmt.tot_pct)
        sh.data_bar(f"{cell_ref(sec_first, 3)}:{cell_ref(sec_last, 3)}", PETROL)
        sh.add_chart("pie", "Purchased cost by plant section",
                     sh.ref(sec_first, 1, sec_last, 1),
                     [("Purchased cost", sh.ref(sec_first, 3, sec_last, 3))],
                     (sec_first, 6), (520, 320))
        r += 2

    # -- the ten largest items ------------------------------------------
    top = sorted(range(len(res.equipment_rows)),
                 key=lambda i: -(res.equipment_rows[i].get("cost") or 0))[:10]
    if top:
        r = _h2(sh, fmt, r, "TEN LARGEST ITEMS", 15)
        sh.write_row(r, 1, ["Tag", "Description", f"Total cost ({cur})"],
                     style=fmt.th)
        r += 1
        big_first = r
        for i in top:
            sh.write(r, 1, res.equipment_rows[i]["tag"], fmt.label_b)
            sh.write(r, 2, res.equipment_rows[i].get("description", ""),
                     fmt.label)
            sh.write(r, 3, f"={cell_ref(first + i, 12)}", fmt.money)
            r += 1
        big_last = r - 1
        sh.data_bar(f"{cell_ref(big_first, 3)}:{cell_ref(big_last, 3)}", AMBER)
        sh.add_chart("bar", "Ten largest equipment items",
                     sh.ref(big_first, 1, big_last, 1),
                     [(f"Cost ({cur})", sh.ref(big_first, 3, big_last, 3))],
                     (big_first, 6), (560, 340), y_title=cur)
    return sh, totals


# ===========================================================================
# Capital
# ===========================================================================
def _capital(wb, fmt, p, res, cur, basis, eq_total):
    sh = wb.add_sheet("Capital", TAB["capital"])
    sh.show_gridlines = False
    for col, w in enumerate([40, 20, 12, 58], start=1):
        sh.set_width(col, w)

    cap, c = res.capital, p.capital
    r = _h1(sh, fmt, 1, "CAPITAL COST — BEC TO TASC", 4)
    r = _prose(sh, fmt, r,
               "NETL-PUB-22580 §2.1. Purchased equipment is typically only "
               "15-30% of what a plant costs; this sheet is the rest of it. "
               "Change a percentage on the Basis sheet and the whole ladder "
               "moves.", 4, 32)
    r += 1

    sh.write_row(r, 1, ["Element", f"Amount ({cur})", "% of TPC",
                        "What it is"], style=fmt.th)
    sh.set_height(r, 22)
    r += 1
    refs = {}

    def line(key, label, style, what, formula=None, value=None):
        nonlocal r
        # text(): rung names such as "= Total plant cost (TPC)" are labels, not
        # formulas.
        sh.text(r, 1, label, fmt.label_b)
        sh.write(r, 2, formula if formula is not None else value, style)
        sh.write(r, 4, what, fmt.note)
        refs[key] = cell_ref(r, 2)
        row_at = r
        r += 1
        return refs[key], row_at

    pec, pec_row = line(
        "pec", "Purchased equipment cost", fmt.money,
        "the purchased subtotal from the Equipment sheet — items not already "
        "flagged as installed",
        f"={eq_total['purchased']}" if eq_total
        else repr(float(res.purchased_equipment_cost)))

    inst_label = {"loh": "DOE/NETL distributive factors, one service and "
                         "setting class for the list",
                  "type": "DOE/NETL distributive factors resolved per item "
                          "from its equipment type",
                  "lang": f"Lang factor, {c.lang_type}",
                  "factor": f"user factor x{c.installation_factor:g}",
                  }.get(c.installation_method, c.installation_method)
    # BEC = f(purchased) + already-installed. So the effective installation
    # multiple is (BEC - already installed) / purchased — NOT bec/purchased,
    # and emphatically not installed_direct/purchased: ProjectResult calls the
    # already-installed entries `installed_direct`, which reads like the
    # opposite of what it is.
    already = res.installed_direct
    mult_value = ((res.bec - already) / res.purchased_equipment_cost
                  if res.purchased_equipment_cost else 1.0)
    mult, _ = line("mult", "x installation multiple", fmt.in_num4,
                   f"{inst_label} — the effective purchased-to-installed "
                   f"multiple this run produced", value=mult_value)
    inst, _ = line("inst", "= Installed direct cost", fmt.money,
                   "purchased equipment, installed", f"={pec}*{mult}")

    # Items entered as an installed price bypass installation and join at BEC.
    already_ref = None
    if abs(already) > 0.5 or eq_total:
        already_ref, _ = line(
            "already", "+ already-installed items", fmt.money,
            "vendor or programme prices entered as installed costs; these must "
            "not pass through the installation factors a second time",
            f"={eq_total['installed']}" if eq_total else repr(float(already)))
    bec, _ = line("bec", "= Bare erected cost (BEC)", fmt.sub_money, "",
                  f"={inst}+{already_ref}" if already_ref else f"={inst}")
    epc, _ = line("epc", "+ EPC contractor services", fmt.money,
                  "detailed design, procurement, construction management, "
                  "permitting", f"={bec}*{basis['epc']}")
    epcc, _ = line("epcc", "= EPC cost (EPCC)", fmt.sub_money, "",
                   f"={bec}+{epc}")
    prc, _ = line("prc", "+ process contingency", fmt.money,
                  "technology immaturity — a process you have not built before",
                  f"={bec}*{basis['proc']}")
    pjc, _ = line("pjc", "+ project contingency", fmt.money,
                  "estimate immaturity — an estimate you have not finished",
                  f"=({epcc}+{prc})*{basis['proj']}")
    tpc, _ = line("tpc", "= Total plant cost (TPC)", fmt.sub_money, "",
                        f"={epcc}+{prc}+{pjc}")

    owner_first = r
    for k, v in (cap.owners_costs or {}).items():
        is_land = "land" in k.lower()
        sh.write(r, 1, "+ " + k, fmt.label)
        if is_land:
            sh.write(r, 2, v, fmt.in_money)
            sh.write(r, 4, "an absolute amount, and not depreciable", fmt.note)
        else:
            frac = v / cap.tpc if cap.tpc else 0.0
            sh.write(r, 2, f"={tpc}*{frac!r}", fmt.money)
            sh.write(r, 4, f"{frac:.2%} of TPC (NETL Exhibit 2-4)", fmt.note)
        r += 1
    owner_last = r - 1

    own = None
    if owner_last >= owner_first:
        sh.write(r, 1, "= Owner's costs", fmt.sub_lbl)
        sh.write(r, 2, f"=SUM({cell_ref(owner_first, 2)}:"
                       f"{cell_ref(owner_last, 2)})", fmt.sub_money)
        own = cell_ref(r, 2)
        sh.write(r, 4, "NETL Exhibit 2-4", fmt.note)
        r += 1

    toc, _ = line("toc", "= Total overnight cost (TOC)", fmt.tot_money,
                  "an overnight cost, in base-year dollars",
                  f"={tpc}+{own}" if own else f"={tpc}")
    tf, _ = line("tf", "x TASC / TOC factor", fmt.num4,
                 f"escalation and carrying cost over "
                 f"{p.finance.construction_years} years, {c.basis} basis",
                 f"={basis['tasc']}")
    tasc, _ = line("tasc", "= Total as-spent capital (TASC)", fmt.tot_money,
                   "mixed current-year dollars — the quantity the NETL fixed "
                   "charge rate multiplies", f"={toc}*{tf}")

    # % of TPC, for every money row in the ladder. The installation multiple
    # and the TASC/TOC factor are ratios, not money, so they are skipped.
    skip = {refs["mult"], refs["tf"]}
    for rr in range(pec_row, r):
        if not sh._cells.get(rr, {}).get(2):
            continue
        if cell_ref(rr, 2) in skip:
            sh.write(rr, 3, None, fmt.label)
            continue
        sh.write(rr, 3, f'=IF({tpc}=0,"",{cell_ref(rr, 2)}/{tpc})', fmt.pct)

    r += 1
    r = _prose(sh, fmt, r,
               "Process contingency covers a technology you have not built. "
               "Project contingency covers an estimate you have not finished. "
               "They are not interchangeable, and a first-of-a-kind plant "
               "needs both.", 4, 30)
    r += 1

    r = _h2(sh, fmt, r, "CAPITAL BUILD-UP", 4)
    sh.write_row(r, 1, ["Element", f"Amount ({cur})"], style=fmt.th)
    r += 1
    wf_first = r
    for label, ref in [("Installed equipment", inst),
                       ("Already installed", already_ref),
                       ("EPC services", epc),
                       ("Process contingency", prc),
                       ("Project contingency", pjc), ("Owner's costs", own)]:
        if ref is None:
            continue
        sh.write(r, 1, label, fmt.label_b)
        sh.write(r, 2, f"={ref}", fmt.money)
        r += 1
    wf_last = r - 1
    sh.data_bar(f"{cell_ref(wf_first, 2)}:{cell_ref(wf_last, 2)}", "3D5A80")
    sh.add_chart("column", f"Capital cost by element ({cur})",
                 sh.ref(wf_first, 1, wf_last, 1),
                 [(cur, sh.ref(wf_first, 2, wf_last, 2))],
                 (wf_first, 4), (560, 330), y_title=cur)

    return sh, {k: _q(sh, v) for k, v in refs.items()}


# ===========================================================================
# Operating cost
# ===========================================================================
def _opex(wb, fmt, p, res, cur, basis, capital):
    sh = wb.add_sheet("Operating cost", TAB["opex"])
    sh.show_gridlines = False
    for col, w in enumerate([30, 14, 13, 14, 16, 18, 12, 40], start=1):
        sh.set_width(col, w)

    o, ro = p.opex, res.opex
    r = _h1(sh, fmt, 1, "ANNUAL OPERATING COST", 8)
    r = _prose(sh, fmt, r,
               "Variable lines scale with production; fixed lines do not. "
               "Depreciation and interest are deliberately absent — the "
               "costing method charges for capital, and repeating it here "
               "would count the plant twice. Rates and prices are amber: "
               "change them and the totals move.", 8, 32)
    r += 1

    hours = basis["hours"]
    cf = basis["cf"]

    r = _h2(sh, fmt, r, "VARIABLE COSTS", 8)
    sh.write_row(r, 1, ["Line", "Rate", "Basis", "Unit",
                        f"Price ({cur}/unit)", "Annual quantity",
                        f"Annual cost ({cur})", "Source"], style=fmt.th)
    sh.set_height(r, 24)
    r += 1

    var_first = r
    # Project.run() prices the plant-level lines the user typed *plus* the
    # consumption recorded against each equipment item. Both have to be on
    # this sheet, or the workbook's total is not the estimate's total.
    try:
        derived = p.equipment_utility_streams()
    except Exception:                                      # noqa: BLE001
        derived = {}
    streams = (
        [("raw_material", s) for s in (o.raw_materials or [])]
        + [("raw_material", s) for s in derived.get("raw_materials", [])]
        + [("utility", s) for s in (o.utilities or [])]
        + [("utility", s) for s in derived.get("utilities", [])]
        + [("waste", s) for s in (o.waste or [])]
        + [("waste", s) for s in derived.get("waste", [])]
        + [("other", s) for s in (o.other_variable or [])]
        + [("other", s) for s in derived.get("other_variable", [])]
    )
    for _cat, s in streams:
        sh.write(r, 1, s.name, fmt.label_b)
        sh.write(r, 2, s.rate, fmt.in_num4)
        sh.write(r, 3, f"per {s.basis}", fmt.label)
        sh.write(r, 4, s.unit, fmt.label)
        sh.write(r, 5, s.price, fmt.in_money4)
        B, E = cell_ref(r, 2), cell_ref(r, 5)
        # Mirrors Stream.annual_quantity: hourly rates multiply by operating
        # hours, annual rates do not, and a line pinned against the capacity
        # factor ignores it.
        scale = cf if s.scales_with_rate else "1"
        qty = f"={B}*{hours}*{scale}" if s.basis == "hour" else f"={B}*{scale}"
        sh.write(r, 6, qty, fmt.num)
        sh.write(r, 7, f"={cell_ref(r, 6)}*{E}", fmt.money)
        sh.write(r, 8, s.source or s.note or "", fmt.note)
        r += 1
    var_last = r - 1

    if var_last >= var_first:
        sh.merge(r, 1, r, 6, "Variable subtotal", fmt.sub_lbl)
        sh.write(r, 7, f"=SUM({cell_ref(var_first, 7)}:"
                       f"{cell_ref(var_last, 7)})", fmt.sub_money)
        sh.write(r, 8, None, fmt.sub_lbl)
        var_total = cell_ref(r, 7)
        sh.data_bar(f"{cell_ref(var_first, 7)}:{cell_ref(var_last, 7)}", AMBER)
    else:
        sh.merge(r, 1, r, 6, "Variable subtotal", fmt.sub_lbl)
        sh.write(r, 7, ro.variable_total, fmt.sub_money)
        var_total = cell_ref(r, 7)
    r += 2

    # -- fixed ----------------------------------------------------------
    r = _h2(sh, fmt, r, f"FIXED COSTS — {o.convention} convention", 8)
    r = _prose(sh, fmt, r,
               "Factored from capital and from labour. Pick one convention "
               "and name it in the report; mixing conventions double-counts "
               "overhead. These are stamped from the engine, which applies "
               "each convention's own basis (installed cost, FCI or TPC).",
               8, 30)
    sh.write_row(r, 1, ["Line", "", "", "", "", "",
                        f"Annual cost ({cur})", "Note"], style=fmt.th)
    r += 1
    fix_first = r
    for k, v in ro.fixed_items.items():
        sh.merge(r, 1, r, 6, k, fmt.label_b)
        sh.write(r, 7, v, fmt.st_money)
        sh.write(r, 8, "", fmt.note)
        r += 1
    fix_last = r - 1
    sh.merge(r, 1, r, 6, "Fixed subtotal", fmt.sub_lbl)
    if fix_last >= fix_first:
        sh.write(r, 7, f"=SUM({cell_ref(fix_first, 7)}:"
                       f"{cell_ref(fix_last, 7)})", fmt.sub_money)
        sh.data_bar(f"{cell_ref(fix_first, 7)}:{cell_ref(fix_last, 7)}",
                    "4A7C59")
    else:
        sh.write(r, 7, ro.fixed_total, fmt.sub_money)
    sh.write(r, 8, None, fmt.sub_lbl)
    fix_total = cell_ref(r, 7)
    r += 2

    sh.merge(r, 1, r, 6, "TOTAL ANNUAL OPERATING COST", fmt.tot_lbl)
    sh.write(r, 7, f"={var_total}+{fix_total}", fmt.tot_money)
    sh.write(r, 8, None, fmt.tot_lbl)
    opex_total = _q(sh, cell_ref(r, 7))
    r += 2

    if ro.labor:
        r = _h2(sh, fmt, r, "LABOUR", 8)
        for label, value, style in [
            ("Headcount", ro.labor.headcount, fmt.num4),
            ("Base payroll", ro.labor.base_payroll, fmt.money),
            ("Payroll burden", ro.labor.burden, fmt.money),
            ("Supervision", ro.labor.supervision, fmt.money),
            ("Total labour", ro.labor.total_labor, fmt.sub_money),
        ]:
            sh.merge(r, 1, r, 6, label, fmt.label_b)
            sh.write(r, 7, value, style)
            sh.write(r, 8, None, fmt.label)
            r += 1
        r += 1

    # -- by category, and a chart ---------------------------------------
    if ro.by_category:
        r = _h2(sh, fmt, r, "BY CATEGORY", 8)
        sh.write_row(r, 1, ["Category", "", "", "", "", "",
                            f"Annual cost ({cur})", ""], style=fmt.th)
        r += 1
        cat_first = r
        for k, v in ro.by_category.items():
            sh.merge(r, 1, r, 6, k, fmt.label_b)
            sh.write(r, 7, v, fmt.money)
            sh.write(r, 8, None, fmt.label)
            r += 1
        cat_last = r - 1
        sh.add_chart("pie", "Operating cost by category",
                     sh.ref(cat_first, 1, cat_last, 1),
                     [("Annual cost", sh.ref(cat_first, 7, cat_last, 7))],
                     (cat_first, 9), (520, 320))

    # Biggest operating lines — usually where the money actually is.
    big = ro.largest(10)
    if big:
        r += 1
        r = _h2(sh, fmt, r, "TEN LARGEST OPERATING LINES", 8)
        sh.write_row(r, 1, ["Line", "", "", "", "", "",
                            f"Annual cost ({cur})", ""], style=fmt.th)
        r += 1
        b_first = r
        for k, v in big:
            sh.merge(r, 1, r, 6, k, fmt.label_b)
            sh.write(r, 7, v, fmt.money)
            sh.write(r, 8, None, fmt.label)
            r += 1
        b_last = r - 1
        sh.data_bar(f"{cell_ref(b_first, 7)}:{cell_ref(b_last, 7)}", "D98324")
        sh.add_chart("bar", "Ten largest operating lines",
                     sh.ref(b_first, 1, b_last, 1),
                     [(f"Annual cost ({cur})", sh.ref(b_first, 7, b_last, 7))],
                     (b_first, 9), (560, 340), y_title=cur)
    return sh, opex_total


# ===========================================================================
# Utilities
# ===========================================================================
def _utilities(wb, fmt, p, res, cur):
    """
    What the plant draws, and which machines draw it.

    Every other sheet in this workbook is about money. This one is about
    consumption, which is the question a process engineer asks first and the
    one the workbook could not answer at all: the rate each item runs at, in
    the unit an engineer reads it in, what that comes to over a year, and what
    share of the utility it is.

    Quantities are values rather than formulas. They are the product of a rate,
    the operating hours, the capacity factor and the running count, and three
    of those live on other sheets — a chain of cross-sheet references here
    would be fragile and would not survive a row being deleted.
    """
    dist = getattr(res, "utility_distribution", None) or []
    if not dist:
        return None

    sh = wb.add_sheet("Utilities", TAB["utilities"])
    sh.show_gridlines = False
    for col, w in enumerate([24, 18, 12, 10, 14, 18, 14, 40], start=1):
        sh.set_width(col, w)

    r = _h1(sh, fmt, 1, "UTILITY CONSUMPTION", 8)
    r = _prose(sh, fmt, r,
               "What the plant consumes, at "
               f"{res.opex.operating_hours:,.0f} h/yr and a "
               f"{res.opex.capacity_factor:.0%} capacity factor. An hourly "
               "rate is a draw and is written as one — a compressor is 5,200 "
               "kW — while the price stays per the unit the utility is "
               "metered in. Consumption entered against an item can be traced "
               "to it; a plant-level line cannot, and says so.", 8, 44)
    r += 1

    # ---- the slate ------------------------------------------------------
    sh.write_row(r, 1, ["Utility", "Annual quantity", "Unit", "Items",
                        f"Price ({cur}/unit)", f"Annual cost ({cur})",
                        "% of variable", "Category"], style=fmt.th)
    sh.set_height(r, 24)
    r += 1
    first = r
    for e in dist:
        sh.write(r, 1, e["utility"], fmt.label_b)
        sh.write(r, 2, e["annual_quantity"], fmt.num)
        sh.write(r, 3, e["unit"], fmt.label)
        sh.write(r, 4, e["n_items"], fmt.num)
        if e["priced"]:
            sh.write(r, 5, e["price"], fmt.in_money4)
        else:
            sh.write(r, 5, "no price", fmt.note)
        sh.write(r, 6, e["annual_cost"], fmt.money)
        sh.write(r, 7, e["annual_cost"] / (res.opex.variable_total or 1.0),
                 fmt.pct)
        sh.write(r, 8, (e["category"] or "utility").replace("_", " "), fmt.note)
        r += 1
    last = r - 1
    if last >= first:
        sh.data_bar(f"{cell_ref(first, 6)}:{cell_ref(last, 6)}", "D98324")
        sh.merge(r, 1, r, 5, "TOTAL VARIABLE UTILITY COST", fmt.tot_lbl)
        sh.write(r, 6, f"=SUM({cell_ref(first, 6)}:{cell_ref(last, 6)})",
                 fmt.tot_money)
        sh.write(r, 7, None, fmt.tot_lbl)
        sh.write(r, 8, None, fmt.tot_lbl)
        r += 2
        sh.add_chart("bar", f"Annual cost by utility ({cur})",
                     sh.ref(first, 1, last, 1),
                     [(f"Annual cost ({cur})", sh.ref(first, 6, last, 6))],
                     (first, 10), (560, 340), y_title=cur)

    # ---- who draws each of them ----------------------------------------
    for e in dist:
        drawn = [i for i in e["items"] if i["annual_quantity"]]
        if len(drawn) < 2:
            continue
        r = _h2(sh, fmt, r, f"{e['utility'].upper()} — WHO DRAWS IT", 8)
        sh.write_row(r, 1, ["Item", "Section", "Equipment type", "Units",
                            "Rate", "Rate unit",
                            f"Annual ({e['unit']})", "Share"], style=fmt.th)
        sh.set_height(r, 24)
        r += 1
        d_first = r
        for i in drawn:
            sh.write(r, 1, i["tag"] or i["label"], fmt.label_b)
            sh.write(r, 2, i["section"], fmt.label)
            sh.write(r, 3, i["equipment_type"], fmt.label)
            sh.write(r, 4, i["units"], fmt.num)
            sh.write(r, 5, i["rate"], fmt.num4)
            sh.write(r, 6, i["rate_unit"], fmt.label)
            sh.write(r, 7, i["annual_quantity"], fmt.num)
            sh.write(r, 8, i["quantity_share"], fmt.pct)
            r += 1
        d_last = r - 1
        sh.data_bar(f"{cell_ref(d_first, 7)}:{cell_ref(d_last, 7)}", "1B6B73")
        sh.merge(r, 1, r, 6, "TOTAL", fmt.tot_lbl)
        sh.write(r, 7, f"=SUM({cell_ref(d_first, 7)}:{cell_ref(d_last, 7)})",
                 fmt.tot_num)
        sh.write(r, 8, None, fmt.tot_lbl)
        r += 2
    return sh


# ===========================================================================
# Products
# ===========================================================================
def _products(wb, fmt, p, res, cur):
    sh = wb.add_sheet("Products", TAB["products"])
    sh.show_gridlines = False
    for col, w in enumerate([26, 18, 12, 16, 14, 18, 40], start=1):
        sh.set_width(col, w)

    alloc = res.allocation
    r = _h1(sh, fmt, 1, "PRODUCTS AND COST ALLOCATION", 7)
    r = _prose(sh, fmt, r,
               "Exactly one product is primary, and its price is what the "
               "estimate solves for. Everything else is credited or "
               "allocated — and which of those you choose can move the answer "
               "by a factor of two.", 7, 30)
    r += 1

    sh.write_row(r, 1, ["Product", "Annual production", "Unit",
                        f"Price ({cur}/unit)", "Role",
                        f"Annual revenue ({cur})", "Note"], style=fmt.th)
    sh.set_height(r, 24)
    r += 1
    first = r
    hours = p.opex.operating_hours
    for prod in (p.products.products or []):
        sh.write(r, 1, prod.name, fmt.label_b)
        # The column is annual, whatever basis the figure was entered on, so
        # the revenue formula beside it multiplies a year's output by a price.
        sh.write(r, 2, prod.quantity(1.0, hours), fmt.in_num)
        sh.write(r, 3, prod.unit, fmt.label)
        if prod.price is None:
            sh.write(r, 4, res.unit_cost if prod.role == "primary" else 0,
                     fmt.st_money4)
        else:
            sh.write(r, 4, prod.price, fmt.in_money4)
        sh.write(r, 5, prod.role, fmt.label)
        sh.write(r, 6, f"={cell_ref(r, 2)}*{cell_ref(r, 4)}", fmt.money)
        entered = (f"entered as {prod.annual_production:,.4g} "
                   f"{prod.unit}/h x {hours:,.0f} h/yr"
                   if prod.basis == "hour" else "")
        note = prod.note or ("price solved by the estimate"
                             if prod.price is None else "")
        sh.write(r, 7, "; ".join(x for x in (note, entered) if x), fmt.note)
        r += 1
    last = r - 1
    if last >= first:
        sh.merge(r, 1, r, 5, "TOTAL REVENUE at these prices", fmt.tot_lbl)
        sh.write(r, 6, f"=SUM({cell_ref(first, 6)}:{cell_ref(last, 6)})",
                 fmt.tot_money)
        sh.write(r, 7, None, fmt.tot_lbl)
        r += 2

    r = _h2(sh, fmt, r, f"ALLOCATION — {alloc.method}", 7)
    r = _prose(sh, fmt, r,
               _methods.OPTION_HELP["allocation"].get(alloc.method, ""),
               7, 34)
    for label, value, style in [
        ("Total annual cost to allocate", alloc.total_cost, fmt.money),
        ("Cost borne by the primary product", alloc.cost_to_primary,
         fmt.money),
        (f"Primary product ({alloc.primary})", alloc.primary_quantity,
         fmt.num),
        (f"Unit cost ({cur}/{alloc.primary_unit})",
         alloc.unit_cost_primary, fmt.tot_money4),
    ]:
        sh.merge(r, 1, r, 4, label, fmt.label_b)
        sh.merge(r, 5, r, 6, value, style)
        sh.write(r, 7, None, fmt.label)
        r += 1

    if alloc.credits:
        r += 1
        r = _h2(sh, fmt, r, "CREDITS", 7)
        for k, v in alloc.credits.items():
            sh.merge(r, 1, r, 4, k, fmt.label_b)
            sh.merge(r, 5, r, 6, v, fmt.money)
            sh.write(r, 7, None, fmt.label)
            r += 1
    if alloc.shares:
        r += 1
        r = _h2(sh, fmt, r, "COST SHARES", 7)
        s_first = r
        for k, v in alloc.shares.items():
            sh.merge(r, 1, r, 4, k, fmt.label_b)
            sh.merge(r, 5, r, 6, v, fmt.pct)
            sh.write(r, 7, None, fmt.label)
            r += 1
        s_last = r - 1
        sh.add_chart("pie", "Cost allocation between products",
                     sh.ref(s_first, 1, s_last, 1),
                     [("Share", sh.ref(s_first, 5, s_last, 5))],
                     (s_first, 8), (480, 300))
    for n in (alloc.notes or []):
        r += 1
        sh.merge(r, 1, r, 7, str(n), fmt.warn)
        sh.set_height(r, 28)
    return sh


# ===========================================================================
# Cash flow
# ===========================================================================
def _cashflow(wb, fmt, p, res, cur):
    cf = res.cash_flow
    if cf is None:
        return None
    sh = wb.add_sheet("Cash flow", TAB["cashflow"])
    for col, w in enumerate([8, 16, 16, 16, 15, 13, 13, 16, 14, 16, 17, 18],
                            start=1):
        sh.set_width(col, w)

    r = _h1(sh, fmt, 1, "DISCOUNTED CASH FLOW", 12)
    r = _prose(sh, fmt, r,
               f"Every figure in {cur}. The product price was solved so the "
               f"net present value is exactly zero at a "
               f"{cf.discount_rate:.2%} discount rate — that price is the "
               f"minimum selling price. These are stamped values: the solve "
               f"is iterative and Excel cannot reproduce it from the inputs "
               f"alone.", 12, 32)

    head = ["Year", "Capex", "Revenue", "Opex", "Depreciation", "Interest",
            "Principal", "Taxable income", "Tax", "Net cash flow",
            "Discounted CF", "Cumulative DCF"]
    hrow = r
    sh.write_row(hrow, 1, head, style=fmt.th)
    sh.set_height(hrow, 30)
    r += 1
    first = r
    cols = [cf.capex, cf.revenue, cf.opex, cf.depreciation, cf.interest,
            cf.principal, cf.taxable_income, cf.tax, cf.net_cash_flow,
            cf.discounted_cash_flow, cf.cumulative_dcf]
    for i, year in enumerate(cf.years):
        sh.write(r, 1, year, fmt.label_b)
        for j, series in enumerate(cols, start=2):
            sh.write(r, j, series[i], fmt.money)
        r += 1
    last = r - 1
    sh.write(r, 1, "TOTAL", fmt.tot_lbl)
    for j in range(2, 13):
        if j == 12:
            sh.write(r, j, None, fmt.tot_lbl)
        else:
            sh.write(r, j, f"=SUM({cell_ref(first, j)}:{cell_ref(last, j)})",
                     fmt.tot_money)
    sh.freeze = (hrow, 1)
    r += 2

    for label, value, style in [
        ("Discount rate", cf.discount_rate, fmt.pct2),
        ("Total capital in the cash flow", cf.total_capital, fmt.money),
        ("NPV at the solved price", cf.npv, fmt.money),
        ("IRR at that price", cf.irr if cf.irr is not None else "not solvable",
         fmt.pct2 if cf.irr is not None else fmt.label),
        ("Payback",
         f"year {cf.payback_year:.1f}" if cf.payback_year is not None
         else "not within the modelled life", fmt.label),
        (f"Solved price ({cur}/{res.unit})", cf.price, fmt.tot_money4),
    ]:
        sh.merge(r, 1, r, 4, label, fmt.label_b)
        sh.merge(r, 5, r, 7, value, style)
        r += 1

    sh.add_chart("column", f"Net cash flow by year ({cur})",
                 sh.ref(first, 1, last, 1),
                 [("Net cash flow", sh.ref(first, 10, last, 10))],
                 (r + 2, 1), (760, 360), y_title=cur)
    sh.add_chart("line", f"Cumulative discounted cash flow ({cur})",
                 sh.ref(first, 1, last, 1),
                 [("Cumulative DCF", sh.ref(first, 12, last, 12))],
                 (r + 2, 14), (700, 360), y_title=cur)
    return sh


# ===========================================================================
# Results
# ===========================================================================
def _results(wb, fmt, p, res, cur, basis, capital, opex_total, comparison):
    sh = wb.add_sheet("Results", TAB["results"])
    sh.show_gridlines = False
    for col, w in enumerate([34, 18, 14, 16, 46], start=1):
        sh.set_width(col, w)

    r = _h1(sh, fmt, 1, "RESULTS", 5)
    r = _prose(sh, fmt, r, "Read the basis and the warnings before the "
                           "number.", 5, 18)
    r += 1

    hero_style = wb.style(fill=PETROL_LT,
                          border={"all": "medium", "color": PETROL})
    for rr in range(r, r + 4):
        for cc in range(1, 6):
            sh.write(rr, cc, None, hero_style)
    sh.merge(r, 1, r, 5, "LEVELISED COST", fmt.hero_lbl)
    sh.merge(r + 1, 1, r + 2, 5, res.unit_cost, fmt.hero)
    sh.set_height(r + 1, 26)
    sh.set_height(r + 2, 22)
    sh.merge(r + 3, 1, r + 3, 5,
             f"{res.currency} per {res.unit} of {res.product}  ·  "
             f"{res.method} method", fmt.hero_unit)
    r += 5

    # -- cost stack -----------------------------------------------------
    r = _h2(sh, fmt, r, "COST BUILD-UP", 5)
    sh.write_row(r, 1, ["Component", f"{cur} per {res.unit}",
                        "% of gross", "Annual " + cur, "Note"], style=fmt.th)
    r += 1
    gross = (res.capital_component + res.fixed_component
             + res.variable_component)
    q = res.annual_production
    stack_first = r
    for label, value, note in [
        ("Capital charge", res.capital_component,
         "the cost of building the plant, spread over its output"),
        ("Fixed operating", res.fixed_component,
         "labour, maintenance, insurance, tax, overhead"),
        ("Variable operating", res.variable_component,
         "feedstock, catalyst, utilities, waste"),
    ]:
        sh.write(r, 1, label, fmt.label_b)
        sh.write(r, 2, value, fmt.money4)
        sh.write(r, 3, f"={cell_ref(r, 2)}/{gross!r}" if gross else 0, fmt.pct)
        sh.write(r, 4, f"={cell_ref(r, 2)}*{q!r}", fmt.money)
        sh.write(r, 5, note, fmt.note)
        r += 1
    stack_last = r - 1
    sh.text(r, 1, "= Gross levelised cost", fmt.sub_lbl)
    sh.write(r, 2, f"=SUM({cell_ref(stack_first, 2)}:"
                   f"{cell_ref(stack_last, 2)})", wb.style(
                       fmt=f'"{cur}"#,##0.0000', fill=BAND,
                       border={"all": "thin", "color": RULE},
                       font={"bold": True, "size": 10.5}))
    gross_cell = cell_ref(r, 2)
    sh.write(r, 3, None, fmt.sub_lbl)
    sh.write(r, 4, f"={gross_cell}*{q!r}", fmt.sub_money)
    sh.write(r, 5, None, fmt.sub_lbl)
    r += 1
    sh.text(r, 1, "- Byproduct credit", fmt.label_b)
    sh.write(r, 2, res.byproduct_component, fmt.money4)
    credit_cell = cell_ref(r, 2)
    sh.write(r, 3, None, fmt.label)
    sh.write(r, 4, f"={credit_cell}*{q!r}", fmt.money)
    sh.write(r, 5, "secondary revenue subtracted from total cost", fmt.note)
    r += 1
    sh.text(r, 1, "= LEVELISED COST", fmt.tot_lbl)
    sh.write(r, 2, f"={gross_cell}-{credit_cell}", fmt.tot_money4)
    sh.write(r, 3, None, fmt.tot_lbl)
    sh.write(r, 4, f"={cell_ref(r, 2)}*{q!r}", fmt.tot_money)
    sh.write(r, 5, None, fmt.tot_lbl)
    sh.data_bar(f"{cell_ref(stack_first, 2)}:{cell_ref(stack_last, 2)}",
                PETROL)
    sh.add_chart("pie", f"Levelised cost build-up ({cur}/{res.unit})",
                 sh.ref(stack_first, 1, stack_last, 1),
                 [("Component", sh.ref(stack_first, 2, stack_last, 2))],
                 (stack_first, 7), (500, 310))
    r += 2

    # -- the three methods ----------------------------------------------
    if comparison:
        r = _h2(sh, fmt, r, "THE THREE COSTING METHODS, SIDE BY SIDE", 5)
        r = _prose(sh, fmt, r,
                   "The same plant, costed three ways. The spread between them "
                   "is a property of the convention, not of the plant — quote "
                   "the method with the number.", 5, 30)
        sh.write_row(r, 1, ["Method", f"{cur} per {res.unit}",
                            "vs. this run", "", "What it does"],
                     style=fmt.th)
        r += 1
        cmp_first = r
        for name, value in comparison.items():
            sh.write(r, 1, name + (" (this run)" if name == res.method else ""),
                     fmt.label_b)
            if value is None:
                sh.write(r, 2, "did not run", fmt.label)
                sh.write(r, 3, None, fmt.label)
            else:
                sh.write(r, 2, value, fmt.money4)
                sh.write(r, 3, f"={cell_ref(r, 2)}/{res.unit_cost!r}-1",
                         fmt.pct)
            sh.write(r, 4, None, fmt.label)
            sh.write(r, 5, _methods.OPTION_HELP["method"].get(name, ""),
                     fmt.note)
            sh.set_height(r, 30)
            r += 1
        cmp_last = r - 1
        sh.add_chart("column", f"Levelised cost by method ({cur}/{res.unit})",
                     sh.ref(cmp_first, 1, cmp_last, 1),
                     [(f"{cur}/{res.unit}",
                       sh.ref(cmp_first, 2, cmp_last, 2))],
                     (cmp_first, 7), (500, 310), y_title=f"{cur}/{res.unit}")
        r += 2

    # -- capital and opex summary ---------------------------------------
    r = _h2(sh, fmt, r, "SUMMARY", 5)
    for label, formula, style in [
        ("Purchased equipment cost", f"={capital['pec']}", fmt.money),
        ("Bare erected cost (BEC)", f"={capital['bec']}", fmt.money),
        ("Total plant cost (TPC)", f"={capital['tpc']}", fmt.money),
        ("Total overnight cost (TOC)", f"={capital['toc']}", fmt.money),
        ("Total as-spent capital (TASC)", f"={capital['tasc']}", fmt.money),
        ("Total annual operating cost", f"={opex_total}", fmt.money),
    ]:
        sh.write(r, 1, label, fmt.label_b)
        sh.merge(r, 2, r, 3, formula, style)
        sh.write(r, 4, None, fmt.label)
        sh.write(r, 5, None, fmt.label)
        r += 1
    r += 1

    if res.notes or res.warnings:
        r = _h2(sh, fmt, r, "NOTES AND WARNINGS", 5)
        for n in (res.warnings or []):
            sh.merge(r, 1, r, 5, "WARNING — " + str(n), fmt.warn)
            sh.set_height(r, 28)
            r += 1
        for n in (res.notes or []):
            sh.merge(r, 1, r, 5, str(n), fmt.text)
            sh.set_height(r, 24)
            r += 1
    return sh


# ===========================================================================
# Method appendix
# ===========================================================================
def _method(wb, fmt, p, res, cur):
    sh = wb.add_sheet("Method", TAB["method"])
    sh.show_gridlines = False
    for col, w in enumerate([32, 40, 34, 20], start=1):
        sh.set_width(col, w)

    r = _h1(sh, fmt, 1, "METHOD AND CALCULATIONS", 4)
    r = _prose(sh, fmt, r,
               "The equations actually used on this run, with this run's own "
               "numbers substituted, so the result can be reproduced with a "
               "calculator. Only the methods you selected are set out in "
               "full; the alternatives are named so it is clear a choice was "
               "made.", 4, 34)
    r += 1

    for i, sec in enumerate(_methods.explain(p, res), start=1):
        r = _h2(sh, fmt, r, f"{i}. {sec['title'].upper()}", 4)
        sh.merge(r, 1, r, 4, sec["summary"], fmt.wrap)
        sh.set_height(r, max(28, 14 * (len(sec["summary"]) // 110 + 1)))
        r += 1
        if sec["source"]:
            sh.merge(r, 1, r, 4, "Source: " + sec["source"], fmt.note)
            sh.set_height(r, 24)
            r += 1
        r += 1

        if sec["equations"]:
            sh.write(r, 1, "Equation", fmt.thl)
            sh.merge(r, 2, r, 4, "", fmt.thl)
            r += 1
            for eq in sec["equations"]:
                sh.write(r, 1, eq["label"], fmt.label)
                sh.merge(r, 2, r, 4, None, fmt.eqn)
                sh.text(r, 2, eq["expr"], fmt.eqn)
                sh.set_height(r, max(18, 14 * (len(eq["expr"]) // 90 + 1)))
                r += 1
            r += 1

        if sec["symbols"]:
            sh.write_row(r, 1, ["Symbol", "Meaning", "Value on this run", ""],
                         style=fmt.th)
            r += 1
            for s in sec["symbols"]:
                sh.write(r, 1, s["sym"], fmt.mono)
                sh.write(r, 2, s["meaning"], fmt.text)
                sh.merge(r, 3, r, 4, None, fmt.label_b)
                sh.text(r, 3, s["value"], fmt.label_b)
                sh.set_height(r, max(18, 14 * (len(s["meaning"]) // 46 + 1)))
                r += 1
            r += 1

        if sec["steps"]:
            sh.write_row(r, 1, ["Step", "Value", "", ""], style=fmt.th)
            r += 1
            for st in sec["steps"]:
                bold = st["label"].strip().startswith("=") or \
                    st["label"].isupper()
                sh.text(r, 1, st["label"], fmt.label_b if bold else fmt.label)
                sh.merge(r, 2, r, 4, None,
                         fmt.sub_lbl if bold else fmt.label)
                sh.text(r, 2, st["detail"], fmt.sub_lbl if bold else fmt.label)
                r += 1
            r += 1

        for n in sec["notes"]:
            sh.merge(r, 1, r, 4, str(n), fmt.note)
            sh.set_height(r, max(20, 13 * (len(str(n)) // 110 + 1)))
            r += 1
        r += 2
    return sh


# ===========================================================================
# assembly
# ===========================================================================
def build_workbook(project, result, comparison: dict | None = None) -> Workbook:
    """
    Build the workbook for one run.

    ``comparison`` is the optional ``{method: unit_cost}`` mapping the
    application already computes, so the Results sheet can put the three
    costing methods side by side without re-running anything.
    """
    cur = result.currency
    wb = Workbook(title=f"{project.name} — techno-economic estimate",
                  creator="teakit")
    # The currency symbol goes into number-format codes, where a stray quote
    # would break the format string; the ISO code is always safe.
    fmt = _Fmt(wb, cur.replace('"', ""))

    _cover(wb, fmt, project, result, cur)
    _, basis = _basis(wb, fmt, project, result, cur)
    _, eq_total = _equipment(wb, fmt, project, result, cur, basis)
    _, capital = _capital(wb, fmt, project, result, cur, basis, eq_total)
    _, opex_total = _opex(wb, fmt, project, result, cur, basis, capital)
    _utilities(wb, fmt, project, result, cur)
    _products(wb, fmt, project, result, cur)
    _cashflow(wb, fmt, project, result, cur)
    _results(wb, fmt, project, result, cur, basis, capital, opex_total,
             comparison)
    _method(wb, fmt, project, result, cur)
    return wb


def to_xlsx(project, result, comparison: dict | None = None) -> bytes:
    """The finished workbook as bytes, ready to write to a file or send."""
    return build_workbook(project, result, comparison).to_bytes()


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
