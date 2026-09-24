"""
teakit.cli — Command line interface.
====================================

    teakit --help

Subcommands:

``equipment``  cost one item, with the full audit trail
``catalogue``  list the correlations, or describe one
``escalate``   move a cost between dollar-years
``capital``    run the BEC -> TASC cascade
``levelized``  CRF / FCR / levelised cost
``dcf``        cash flow and minimum selling price
``run``        load a project JSON, run it, print or export
``sensitivity`` tornado / sweep / Monte Carlo on a project JSON
``demo``       write a demonstration project JSON
``app``        launch the graphical application
"""

from __future__ import annotations

import argparse
import json
import sys


def _p_money(v: float) -> str:
    return f"{v:,.2f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="teakit",
        description="Techno-economic analysis of chemical process plants. "
                    "Capital from DOE/NETL, cash flow from NREL, escalation by CEPCI.")
    from . import __version__
    ap.add_argument("--version", action="version", version=f"teakit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # ---- equipment ----
    e = sub.add_parser("equipment", help="cost one piece of equipment")
    e.add_argument("kind")
    e.add_argument("size", type=float)
    e.add_argument("--year", type=int, default=2025)
    e.add_argument("--material", default="carbon steel")
    e.add_argument("--location-factor", type=float, default=1.0)
    e.add_argument("--extrapolate", action="store_true")

    # ---- catalogue ----
    c = sub.add_parser("catalogue", help="list or describe correlations")
    c.add_argument("name", nargs="?", help="describe this one")
    c.add_argument("--group", help="filter by key prefix")
    c.add_argument("--exponents", action="store_true", help="print exponent table")

    # ---- escalate ----
    x = sub.add_parser("escalate", help="move a cost between dollar-years")
    x.add_argument("cost", type=float)
    x.add_argument("from_year", type=int)
    x.add_argument("to_year", type=int)

    # ---- capital ----
    k = sub.add_parser("capital", help="BEC -> EPCC -> TPC -> TOC -> TASC")
    k.add_argument("bec", type=float)
    k.add_argument("--epc-fee", type=float, default=0.175)
    k.add_argument("--process-contingency", type=float, default=0.0)
    k.add_argument("--project-contingency", type=float, default=0.20)
    k.add_argument("--construction-years", type=int, default=3)
    k.add_argument("--basis", choices=["real", "nominal"], default="real")

    # ---- levelized ----
    lv = sub.add_parser("levelized", help="CRF, FCR and a levelised cost")
    lv.add_argument("--rate", type=float, required=True)
    lv.add_argument("--years", type=int, required=True)
    lv.add_argument("--tax-rate", type=float, default=0.2574)
    lv.add_argument("--depreciation-years", type=int, default=20)
    lv.add_argument("--capital", type=float)
    lv.add_argument("--fixed-opex", type=float, default=0.0)
    lv.add_argument("--variable-opex", type=float, default=0.0)
    lv.add_argument("--production", type=float)

    # ---- dcf ----
    d = sub.add_parser("dcf", help="cash flow and minimum selling price")
    d.add_argument("--capital", type=float, required=True)
    d.add_argument("--production", type=float, required=True)
    d.add_argument("--fixed-opex", type=float, default=0.0)
    d.add_argument("--variable-opex", type=float, default=0.0)
    d.add_argument("--byproduct-revenue", type=float, default=0.0)
    d.add_argument("--rate", type=float, default=0.10)
    d.add_argument("--tax-rate", type=float, default=0.2574)
    d.add_argument("--life", type=int, default=30)
    d.add_argument("--construction-years", type=int, default=3)
    d.add_argument("--depreciation-years", type=int, default=7)
    d.add_argument("--table", action="store_true")

    # ---- run ----
    r = sub.add_parser("run", help="run a project JSON file")
    r.add_argument("path")
    r.add_argument("--method", choices=["dcf", "fcr", "simple"])
    r.add_argument("--format",
                   choices=["text", "markdown", "html", "json", "xlsx"],
                   default="text",
                   help="xlsx writes a sectioned Excel workbook with live "
                        "formulas, charts and the method appendix; it needs -o")
    r.add_argument("-o", "--output", help="write to this file instead of stdout")
    r.add_argument("--compare-methods", action="store_true")
    r.add_argument("--csv", choices=["equipment", "cashflow", "opex"])

    # ---- sensitivity ----
    s = sub.add_parser("sensitivity", help="tornado, sweep or Monte Carlo")
    s.add_argument("path")
    s.add_argument("--kind", choices=["tornado", "sweep", "monte-carlo"],
                   default="tornado")
    s.add_argument("--param", action="append", default=[],
                   help="dotted parameter path; repeatable")
    s.add_argument("--metric", default="msp")
    s.add_argument("-n", type=int, default=11)
    s.add_argument("--svg", help="write the chart to this SVG file")

    # ---- demo ----
    dm = sub.add_parser("demo", help="write a demonstration project")
    dm.add_argument("kind", nargs="?", default="methanol",
                    choices=["methanol", "electrolysis", "biorefinery"])
    dm.add_argument("-o", "--output", help="write JSON here; default is stdout")
    dm.add_argument("--run", action="store_true", help="run it and print the report")

    # ---- app ----
    a = sub.add_parser("app", help="launch the graphical application")
    a.add_argument("--port", type=int, default=8765)
    a.add_argument("--host", default="127.0.0.1")
    a.add_argument("--no-browser", action="store_true")
    a.add_argument("--desktop", action="store_true",
                   help="open in a native window instead of the browser "
                        "(needs the 'desktop' extra)")
    a.add_argument("--debug", action="store_true",
                   help="log every request, and enable the WebView dev tools "
                        "when used with --desktop")

    args = ap.parse_args(argv)
    return _dispatch(args)


def _dispatch(args) -> int:                                # noqa: C901
    import teakit as tea

    if args.cmd == "equipment":
        r = tea.purchased_cost(args.kind, args.size, year=args.year,
                               material=args.material,
                               location_factor=args.location_factor,
                               allow_extrapolation=args.extrapolate)
        print(r.report())
        return 0

    if args.cmd == "catalogue":
        if args.exponents:
            print(tea.exponent_table())
        elif args.name:
            print(tea.describe(args.name))
        else:
            keys = tea.catalogue(args.group)
            for key in keys:
                rec = tea.EQUIPMENT[key]
                print(f"{key:<36} n={rec['exponent']:.3f}  "
                      f"{rec['valid_min']:g}-{rec['valid_max']:g} {rec['size_unit']}")
            print(f"\n{len(keys)} correlations. "
                  f"'teakit catalogue NAME' for detail.")
        return 0

    if args.cmd == "escalate":
        out = tea.escalate(args.cost, args.from_year, args.to_year)
        i1, i2 = tea.cepci(args.from_year), tea.cepci(args.to_year)
        print(f"{_p_money(args.cost)} ({args.from_year}) -> "
              f"{_p_money(out)} ({args.to_year})")
        print(f"CEPCI {i1:.1f} -> {i2:.1f}, ratio {i2 / i1:.4f}")
        prov = tea.is_provisional(args.to_year)
        if prov:
            print(f"! {prov.splitlines()[0]}")
        return 0

    if args.cmd == "capital":
        m = tea.NETLCapitalCost(
            bec=args.bec, epc_fee_frac=args.epc_fee,
            process_contingency_frac=args.process_contingency,
            project_contingency_frac=args.project_contingency,
            construction_years=args.construction_years, basis=args.basis)
        print(m.evaluate().report())
        return 0

    if args.cmd == "levelized":
        cr = tea.crf(args.rate, args.years)
        fc = tea.fcr(args.rate, args.years, args.tax_rate, args.depreciation_years)
        print(f"CRF  {cr:.6f}   ({args.rate:.4%} over {args.years} years)")
        print(f"FCR  {fc:.6f}   (tax {args.tax_rate:.2%}, MACRS "
              f"{args.depreciation_years}-year)")
        if args.capital and args.production:
            res = tea.lcox(args.capital, fc, args.fixed_opex,
                           args.variable_opex, args.production)
            print()
            print(res.report() if hasattr(res, "report")
                  else f"levelised cost {res.levelized_cost:,.4f}")
        return 0

    if args.cmd == "dcf":
        m = tea.CashFlowModel(
            total_capital=args.capital, annual_production=args.production,
            annual_fixed_opex=args.fixed_opex,
            annual_variable_opex=args.variable_opex,
            annual_byproduct_revenue=args.byproduct_revenue,
            discount_rate=args.rate, tax_rate=args.tax_rate,
            plant_life_years=args.life,
            construction_years=args.construction_years,
            depreciation_years=args.depreciation_years)
        msp = m.minimum_selling_price()
        res = m.run(msp)
        print(f"minimum selling price  {msp:,.4f} per unit")
        print(f"NPV at that price      {res.npv:,.2f}")
        print(f"IRR                    {(res.irr or 0):.4%}")
        if args.table:
            print()
            print(res.table())
        return 0

    if args.cmd == "run":
        p = tea.Project.load(args.path)
        if args.compare_methods:
            comp = p.method_comparison()
            base = comp["dcf"]
            print(f"{'method':<10}{'unit cost':>16}{'vs dcf':>12}")
            for k, v in comp.items():
                print(f"{k:<10}{v:>16,.4f}{(v / base - 1) * 100:>11.1f}%")
            return 0
        res = p.run(args.method)
        from . import report as rep

        if args.format == "xlsx":
            # A workbook is binary, so unlike every other format it cannot go
            # to stdout — say so rather than writing mojibake to a terminal.
            if not args.output:
                print("--format xlsx writes a binary file; give -o NAME.xlsx",
                      file=sys.stderr)
                return 2
            from . import excel as _excel
            comparison = {}
            for m in ("dcf", "fcr", "simple"):
                try:
                    comparison[m] = p.run(m).unit_cost
                except Exception:                          # noqa: BLE001
                    comparison[m] = None
            data = _excel.to_xlsx(p, res, comparison)
            with open(args.output, "wb") as fh:
                fh.write(data)
            print(f"wrote {args.output} ({len(data) / 1024:.0f} KB)")
            return 0

        if args.csv:
            text = {"equipment": rep.equipment_csv,
                    "cashflow": rep.cash_flow_csv,
                    "opex": rep.opex_csv}[args.csv](res)
        elif args.format == "text":
            text = rep.to_text(p, res)
        elif args.format == "markdown":
            text = rep.to_markdown(p, res)
        elif args.format == "html":
            text = rep.to_html(p, res)
        else:
            text = json.dumps(res.to_dict(), indent=2, default=str)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"wrote {args.output}")
        else:
            print(text)
        return 0

    if args.cmd == "sensitivity":
        from . import charts, sensitivity as sens
        p = tea.Project.load(args.path)
        spec = None
        if args.kind == "tornado":
            t = sens.tornado(p, args.param or None, metric=args.metric)
            print(t.report())
            spec = charts.tornado_chart(t)
        elif args.kind == "sweep":
            if not args.param:
                print("sweep needs --param", file=sys.stderr)
                return 2
            sw = sens.sweep(p, args.param[0], metric=args.metric, n=args.n)
            print(f"{'value':>16}{args.metric:>16}")
            for xv, yv in zip(sw.x, sw.y):
                print(f"{xv:>16,.6g}{yv:>16,.6g}")
            spec = charts.sweep_chart(sw)
        else:
            dists = {q: {} for q in (args.param or ["finance.discount_rate"])}
            mc = sens.monte_carlo(p, dists, n=args.n if args.n > 11 else 300,
                                  metric=args.metric)
            print(mc.report())
            spec = charts.monte_carlo_chart(mc)
        if args.svg and spec is not None:
            spec.save_svg(args.svg)
            print(f"\nwrote {args.svg}")
        return 0

    if args.cmd == "demo":
        p = tea.demo(args.kind)
        if args.run:
            from . import report as rep
            print(rep.to_text(p, p.run()))
            return 0
        js = p.to_json()
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(js)
            print(f"wrote {args.output} — run it with: teakit run {args.output}")
        else:
            print(js)
        return 0

    if args.cmd == "app":
        if args.desktop:
            from .app.desktop import launch
            return launch(debug=args.debug, host=args.host, port=args.port)
        from .app.server import serve
        serve(host=args.host, port=args.port, open_browser=not args.no_browser,
              verbose=args.debug)
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
