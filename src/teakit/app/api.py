"""
teakit.app.api — The application's calculation layer.
=====================================================

Pure ``dict`` in, ``dict`` out. No HTTP, no HTML, no globals. That separation
is deliberate: it means the entire application logic can be tested with plain
function calls, and it means the same layer could sit behind a desktop GUI, a
notebook widget or a REST service without change.

The one exception is the ``workspace_*`` group, which is how a report reaches
the user's report folder rather than the browser's download tray. Even there
the filesystem work lives in :mod:`teakit.app.workspace`; these endpoints only
translate its results into the same ``ok``-flagged dicts as everything else.

Every endpoint takes a JSON-shaped ``dict`` and returns a JSON-shaped ``dict``
with an ``ok`` flag. Errors come back as ``{"ok": False, "error": ...}`` rather
than raising, because a user typing a negative pump size into a form should get
a message, not a stack trace.

    >>> from teakit.app import api
    >>> api.meta()["ok"]
    True
    >>> r = api.run({"project": api.demo({"kind": "methanol"})["project"]})
    >>> r["ok"] and r["result"]["unit_cost"] > 0
    True
"""

from __future__ import annotations

import base64
import time
import traceback

from .. import (charts as _charts, currency as _currency, datasets as _datasets,
                defaults as _defaults, equipment as _equipment,
                equipment_data as _eqdata, examples as _examples,
                excel as _excel, indices as _indices, methods as _methods,
                opex as _opex, report as _report, sensitivity as _sens)
from ..capital import (AACE_CLASSES, LANG_FACTORS, LOH_DISTRIBUTIVE_FACTORS,
                       LOH_SETTING_FACTORS, PROCESS_CONTINGENCY_AACE)
from ..products import ALLOCATION_METHODS
from .. import project as _project_mod
from ..project import COSTING_METHODS, Project
from . import workspace as _workspace

__all__ = ["dispatch", "meta", "catalogue", "describe", "demo", "run",
           "parameters", "sensitivity", "export", "utility_defaults",
           "utility_chart",
           "exchange_rates", "explain", "workspace", "workspace_set",
           "workspace_reset", "workspace_save", "workspace_open",
           "workspace_pick", "ENDPOINTS"]


#: The last dollar-year the interface offers. Plants are costed years before
#: they are built, so the year list has to run past the published index -- the
#: CEPCI series stops at 2025 and there is no prospect of it being extended by
#: anything except time. A year with no published index is offered with an
#: empty value beside it for the user to fill in; see
#: :data:`teakit.indices.CEPCI_USER`.
YEAR_MAX = 2050


def _ok(**kw) -> dict:
    return {"ok": True, **kw}


def _err(msg: str, detail: str = "") -> dict:
    return {"ok": False, "error": str(msg), "detail": detail}


def _project_from(payload: dict) -> Project:
    return Project.from_dict(payload.get("project") or {})


# ============================================================================
# meta — everything the interface needs to build its forms
# ============================================================================
def meta(payload: dict | None = None) -> dict:
    """
    Reference data for the interface: the catalogue, the presets, the option
    lists. Fetched once at boot so every dropdown is generated from the library
    rather than duplicated in JavaScript.
    """
    from .. import CITATION, LICENSE_NOTE, __author__, __license__, __url__, __version__
    eq = []
    for key in sorted(_eqdata.EQUIPMENT):
        r = _eqdata.EQUIPMENT[key]
        eq.append(dict(
            key=key, description=r["description"], unit=r["size_unit"],
            exponent=r["exponent"], base_size=r["base_size"],
            base_cost=r["base_cost"], valid_min=r["valid_min"],
            valid_max=r["valid_max"], r_squared=r.get("r_squared"),
            rel_rmse=r.get("rel_rmse"), n_points=r.get("n_points"),
            reliable=r.get("reliable", True), caution=r.get("caution") or "",
            group=key.split("_")[0]))
    return _ok(
        version=__version__,
        # Provenance, for the Info section: who wrote it, what it may be
        # used for, and what to cite.
        author=__author__,
        license=__license__,
        license_note=LICENSE_NOTE,
        url=__url__,
        citation=CITATION,
        equipment=eq,
        aliases=sorted(_eqdata.ALIASES),
        # The alias -> catalogue key mapping, not just the names. Without it
        # the interface cannot work out that an item keyed "separator" rolls
        # up as a vessel, and would offer to edit a factor for an equipment
        # type the estimate never asks about.
        alias_map=dict(_eqdata.ALIASES),
        columns=[dict(key=k, description=v["description"])
                 for k, v in _eqdata.COLUMNS.items()],
        materials=sorted(_equipment.MATERIAL_FACTORS),
        locations=[dict(name=k, factor=v["factor"], labor=v["labor_factor"],
                        currency=v["currency"], note=v["note"])
                   for k, v in _defaults.LOCATIONS.items()],
        currencies=_currency.CURRENCIES,
        exchange_rates=dict(_currency.DEFAULT_RATES),
        exchange_rates_as_of=_currency.RATES_AS_OF,
        utilities=[dict(name=k, unit=v["unit"], price=v["price"],
                        basis_year=v["basis_year"], category=v["category"],
                        source=v["source"])
                   for k, v in _defaults.UTILITY_CATALOGUE.items()],
        labor_roles=[dict(role=k, salary=v["salary"], shift=v["shift"],
                          soc=v["soc"]) for k, v in _defaults.LABOR_ROLES.items()],
        nrel_staffing=_defaults.NREL_STAFFING,
        finance_presets={k: {kk: vv for kk, vv in v.items()}
                         for k, v in _defaults.FINANCE_PRESETS.items()},
        tax_presets=_defaults.TAX_PRESETS,
        operating_presets=_defaults.OPERATING_PRESETS,
        fixed_conventions={k: v["source"] for k, v in _opex.FIXED_CONVENTIONS.items()},
        costing_methods=list(COSTING_METHODS),
        allocation_methods=list(ALLOCATION_METHODS),
        installation_methods=["loh", "type", "lang", "factor"],
        # The equipment-type vocabulary, with the evidence behind each type's
        # scaling exponent and the service and setting class that give it an
        # installation factor. The interface builds both its type picker and
        # its per-type factor table from this, so the numbers on screen are
        # the library's rather than a second copy kept in JavaScript.
        equipment_types=_equipment.equipment_types(),
        literature_exponents={k: list(v) for k, v
                              in _equipment.LITERATURE_EXPONENTS.items()},
        six_tenths=_equipment.SIX_TENTHS,
        loh_services=list(LOH_DISTRIBUTIVE_FACTORS),
        loh_settings=sorted(LOH_SETTING_FACTORS),
        lang_types=list(LANG_FACTORS),
        # The factor tables themselves, so the interface can show what the
        # purchased-to-installed step comes to before the estimate is run
        # rather than only afterwards, in a note.
        loh_distributive={k: {kk: list(vv) for kk, vv in v.items()}
                          for k, v in LOH_DISTRIBUTIVE_FACTORS.items()},
        loh_setting_factors=dict(LOH_SETTING_FACTORS),
        lang_factors=dict(LANG_FACTORS),
        lang_delivery_factor=1.10,
        process_contingency_bands={k: list(v)
                                   for k, v in PROCESS_CONTINGENCY_AACE.items()},
        aace_classes={str(k): list(v) for k, v in AACE_CLASSES.items()},
        metrics=list(_sens.METRICS),
        demos=_examples.DEMOS,
        # Every year that can be chosen, published or not: the shipped series
        # plus a straight run to YEAR_MAX. `cepci` carries the values, and a
        # year absent from it is one the user has to supply an index for.
        cepci_years=sorted(set(_indices.CEPCI_ANNUAL)
                           | set(range(max(_indices.CEPCI_ANNUAL) + 1,
                                       YEAR_MAX + 1))),
        cepci=_indices.CEPCI_ANNUAL,
        cepci_provisional=dict(_indices.CEPCI_PROVISIONAL),
        cepci_year_max=YEAR_MAX,
        datasets=_datasets.available(),
        basis_year=_eqdata.BASIS_YEAR,
        basis_quarter=_eqdata.BASIS_QUARTER,
        basis_cepci=_eqdata.BASIS_CEPCI,
        basis_location=_eqdata.BASIS_LOCATION,
        basis_material=_eqdata.BASIS_MATERIAL,
        source=_eqdata.SOURCE,
        source_url=_eqdata.SOURCE_URL,
        # The interface builds every tooltip and its Info section from
        # these, so the explanation of an option lives in exactly one
        # place — beside the code that implements it.
        option_help=_methods.option_help_flat(),
        guide=_methods.GUIDE,
        # Units teakit offers per kind of utility, and which set each
        # catalogued utility belongs to. The interface builds its unit
        # dropdowns from these rather than keeping a second copy.
        unit_sets={k: {"label": v["label"], "units": list(v["units"]),
                       "per_hour": dict(v["per_hour"])}
                   for k, v in _defaults.UNIT_SETS.items()},
        utility_measures=dict(_defaults.UTILITY_MEASURES),
        equipment_categories=sorted(set(_project_mod.CATEGORY_LABELS.values())),
        category_labels=dict(_project_mod.CATEGORY_LABELS),
    )


def catalogue(payload: dict) -> dict:
    """Filtered equipment catalogue, for the picker's search box."""
    q = (payload.get("query") or "").strip().lower()
    out = []
    for key in sorted(_eqdata.EQUIPMENT):
        rec = _eqdata.EQUIPMENT[key]
        hay = f"{key} {rec['description']}".lower()
        if not q or q in hay:
            out.append(dict(key=key, description=rec["description"],
                            unit=rec["size_unit"], exponent=rec["exponent"],
                            valid_min=rec["valid_min"], valid_max=rec["valid_max"],
                            reliable=rec.get("reliable", True)))
    return _ok(items=out, count=len(out))


def describe(payload: dict) -> dict:
    """Everything known about one correlation, as text plus a cost curve."""
    key = payload.get("key") or ""
    try:
        text = _equipment.describe(key)
        k = _eqdata.resolve(key)
        rec = _eqdata.EQUIPMENT[k]
    except KeyError as exc:
        return _err(exc)
    year = int(payload.get("year") or 2025)
    lo, hi = rec["valid_min"], rec["valid_max"]
    xs = [lo * (hi / lo) ** (i / 24) for i in range(25)] if lo > 0 else []
    ys = []
    for x in xs:
        try:
            ys.append(_equipment.purchased_cost(k, x, year=year, quiet=True).cost)
        except Exception:                                  # noqa: BLE001
            ys.append(None)
    curve = _charts.line(f"{k} — cost curve, {year} USD", xs,
                         [y for y in ys if y is not None],
                         x_label=rec["size_unit"], y_label=f"{year} USD")
    return _ok(text=text, record={k2: v for k2, v in rec.items()
                                 if isinstance(v, (int, float, str, bool))},
               chart=curve.to_dict(), svg=curve.svg(640, 340))


def utility_defaults(payload: dict) -> dict:
    """Priced utility sheet for a given dollar-year."""
    year = payload.get("year")
    rows = _defaults.default_utility_set(int(year) if year else None)
    return _ok(rows=rows)


def exchange_rates(payload: dict) -> dict:
    """
    USD-based exchange rates for the interface.

    ``payload["live"]`` decides where they come from:

    ``True``   force a network fetch, and say so if it fails
    ``False``  never touch the network — the bundled offline table
    unset      the cached table if it is fresh, otherwise try the network

    Always returns ``ok``: a cost tool must keep working offline, so a failed
    fetch degrades to the best table available and reports which one that is.
    ``stale_days`` lets the interface warn on an old rate.
    """
    live = payload.get("live")
    source_note = ""
    if live is False:
        table = _currency.RateTable()
    elif live is True:
        fetched = _currency.fetch_rates()
        if fetched is None:
            table = _currency.load_rates() or _currency.RateTable()
            source_note = ("could not reach the exchange-rate feed — "
                           "showing the last rates available")
        else:
            _currency.save_rates(fetched)
            table = fetched
    else:
        table = _currency.cached_rates()

    quotes = {code: table.rates.get(code, _currency.DEFAULT_RATES.get(code, 1.0))
              for code in _currency.CURRENCIES}
    quotes["USD"] = 1.0
    probe = _currency.RateQuote("USD", 1.0, table.source, table.as_of)

    requested = payload.get("currency")
    single = {}
    if requested:
        code = str(requested).upper()
        if code not in _currency.CURRENCIES:
            return _err(f"unsupported currency {requested!r}")
        single = dict(currency=code, rate=quotes[code])

    return _ok(rates=quotes, source=table.source, as_of=table.as_of,
               live=table.live, stale_days=probe.stale_days,
               note=source_note, symbols=_currency.CURRENCIES, **single)


def demo(payload: dict) -> dict:
    """A populated demonstration project."""
    kind = payload.get("kind") or "methanol"
    try:
        p = _examples.build_demo(kind)
    except KeyError as exc:
        return _err(exc)
    return _ok(project=p.to_dict(), name=p.name, description=p.description)


def blank(payload: dict | None = None) -> dict:
    """An empty project with sensible defaults, for 'New'."""
    p = Project(name="New project", dollar_year=2025)
    p.opex.labor = _opex.LaborModel(operators_per_shift=3)
    return _ok(project=p.to_dict())


# ============================================================================
# run
# ============================================================================
def run(payload: dict) -> dict:
    """
    Run a project. Returns the result, the standard chart set and, if asked,
    the three-method comparison.
    """
    try:
        p = _project_from(payload)
    except Exception as exc:                               # noqa: BLE001
        return _err(f"could not read the project: {exc}", traceback.format_exc())

    method = payload.get("method") or p.method
    try:
        res = p.run(method)
    except Exception as exc:                               # noqa: BLE001
        return _err(str(exc), traceback.format_exc())

    out = res.to_dict()
    try:
        specs = _charts.default_charts(res)
        out_charts = {k: v.to_dict() for k, v in specs.items()}
    except Exception as exc:                               # noqa: BLE001
        out_charts = {}
        out.setdefault("warnings", []).append(f"charts unavailable: {exc}")
    # Kept apart from the standard set: these are about what the plant
    # consumes rather than what it costs, and they belong on their own
    # section rather than mixed into the capital figures.
    try:
        util_charts = {k: v.to_dict() for k, v
                       in _charts.utility_distribution_charts(res).items()}
    except Exception as exc:                               # noqa: BLE001
        util_charts = {}
        out.setdefault("warnings", []).append(
            f"utility charts unavailable: {exc}")

    comparison = None
    if payload.get("compare_methods"):
        comparison = {}
        for m in COSTING_METHODS:
            try:
                comparison[m] = p.run(m).unit_cost
            except Exception:                              # noqa: BLE001
                comparison[m] = None

    assumptions = [{"label": k, "value": v}
                   for k, v in _report.assumptions_table(p, res)]
    try:
        explanation = _methods.explain(p, res)
    except Exception as exc:                               # noqa: BLE001
        # A missing explanation must never cost the user their estimate.
        explanation = []
        out.setdefault("warnings", []).append(
            f"method explanation unavailable: {exc}")
    return _ok(result=out, charts=out_charts, utility_charts=util_charts,
               comparison=comparison,
               assumptions=assumptions, explanation=explanation,
               equipment_total=res.purchased_equipment_cost,
               headcount=res.opex.labor.headcount if res.opex.labor else 0.0)


def explain(payload: dict) -> dict:
    """
    The method appendix for a project: the equations actually used, with the
    run's own numbers substituted.

    The interface shows this under Results and at the end of every report, so
    a reader can reproduce the number rather than take it on trust.
    """
    try:
        p = _project_from(payload)
        res = p.run(payload.get("method") or p.method)
    except Exception as exc:                               # noqa: BLE001
        return _err(exc, traceback.format_exc())
    return _ok(sections=_methods.explain(p, res), guide=_methods.GUIDE)


def parameters(payload: dict) -> dict:
    """Every addressable numeric input, grouped — this drives the custom-plot
    and sensitivity pickers."""
    try:
        p = _project_from(payload)
        params = p.parameters()
    except Exception as exc:                               # noqa: BLE001
        return _err(exc, traceback.format_exc())
    groups: dict[str, list] = {}
    for prm in params:
        # The multipliers a tornado would use if nothing were typed, so the
        # interface can show what "auto" actually resolves to rather than
        # leaving the reader to guess whether a blank means +/-20%.
        lo_m, hi_m = _sens._range_for(prm["path"])
        prm["low_mult"], prm["high_mult"] = lo_m, hi_m
        v = prm.get("value")
        if isinstance(v, (int, float)):
            prm["auto_low"], prm["auto_high"] = v * lo_m, v * hi_m
        groups.setdefault(prm["group"], []).append(prm)
    by_path = {prm["path"]: prm for prm in params}
    suggested = [dict(path=s.path, label=s.display(), unit=s.unit,
                      value=by_path.get(s.path, {}).get("value"),
                      low_mult=by_path.get(s.path, {}).get("low_mult"),
                      high_mult=by_path.get(s.path, {}).get("high_mult"))
                 for s in _sens.suggest_params(p)]
    return _ok(parameters=params, groups=groups, suggested=suggested,
               metrics=list(_sens.METRICS))


# ============================================================================
# sensitivity
# ============================================================================
def sensitivity(payload: dict) -> dict:
    """
    Tornado, sweep, two-way grid or Monte Carlo, depending on ``kind``.

    Every branch returns a chart spec under ``chart`` so the interface renders
    them all through one code path.
    """
    try:
        p = _project_from(payload)
    except Exception as exc:                               # noqa: BLE001
        return _err(exc)
    kind = payload.get("kind") or "tornado"
    metric = payload.get("metric") or "msp"
    method = payload.get("method")

    try:
        if kind == "tornado":
            raw = payload.get("params") or None
            params = None
            if raw:
                params = [_sens.SensitivityParam(
                    path=q["path"], label=q.get("label", ""),
                    low=q.get("low"), high=q.get("high"),
                    low_mult=q.get("low_mult"), high_mult=q.get("high_mult"),
                    unit=q.get("unit", "")) for q in raw]
            t = _sens.tornado(p, params, metric=metric, method=method)
            return _ok(kind=kind, data=t.to_dict(),
                       chart=_charts.tornado_chart(t).to_dict())

        if kind == "sweep":
            path = payload.get("path")
            if not path:
                return _err("a sweep needs a parameter path")
            sw = _sens.sweep(p, path, metric=metric, n=int(payload.get("n") or 11),
                             span=tuple(payload["span"]) if payload.get("span") else None,
                             method=method, label=payload.get("label", ""))
            return _ok(kind=kind, data=sw.to_dict(),
                       chart=_charts.sweep_chart(sw).to_dict())

        if kind == "two_way":
            g = _sens.two_way(p, payload["x_path"], payload["y_path"],
                              metric=metric, nx=int(payload.get("nx") or 7),
                              ny=int(payload.get("ny") or 7), method=method)
            return _ok(kind=kind, data=g.to_dict(),
                       chart=_charts.grid_chart(g).to_dict())

        if kind == "monte_carlo":
            dists = payload.get("distributions") or {}
            if not dists:
                dists = {s.path: {} for s in _sens.suggest_params(p, 6)}
            mc = _sens.monte_carlo(p, dists, n=int(payload.get("n") or 400),
                                   metric=metric, seed=payload.get("seed", 0),
                                   method=method)
            return _ok(kind=kind, data=mc.to_dict(),
                       chart=_charts.monte_carlo_chart(mc).to_dict())

        if kind == "breakeven":
            v = _sens.breakeven(p, payload["path"], float(payload["target"]),
                                metric=metric, method=method)
            return _ok(kind=kind, value=v,
                       message=("no solution in the search bracket — the metric "
                                "may not be monotone in this parameter, or the "
                                "target may be unreachable") if v is None else "")
    except Exception as exc:                               # noqa: BLE001
        return _err(exc, traceback.format_exc())
    return _err(f"unknown sensitivity kind {kind!r}")


def utility_chart(payload: dict) -> dict:
    """
    Where one utility goes, as a chart.

    ``utility`` names it; ``group`` is "item", "section" or "type"; ``measure``
    is "quantity" or "cost"; ``kind`` is "donut" or "bar". Omit ``utility`` and
    the whole slate is compared on cost, which is the only measure that can be
    compared across utilities — kWh, m3 and MMBtu do not share an axis.
    """
    try:
        p = _project_from(payload)
        res = p.run(payload.get("method") or p.method)
    except Exception as exc:                               # noqa: BLE001
        return _err(exc)
    try:
        if payload.get("utility"):
            spec = _charts.utility_chart(
                res, payload["utility"],
                payload.get("group") or "item",
                payload.get("measure") or "quantity",
                payload.get("kind") or "donut")
        else:
            spec = _charts.utility_totals_chart(res)
    except (KeyError, ValueError) as exc:
        return _err(exc)
    return _ok(chart=spec.to_dict(), svg=spec.svg(),
               distribution=res.utility_distribution)


def custom_chart(payload: dict) -> dict:
    """
    Build a chart from an arbitrary series the user picked in the interface.

    ``source`` names a rollup on the result — ``equipment_shares``,
    ``opex_items``, ``capex_breakdown``, ``cost_stack``, ``section_shares``,
    ``type_shares``, ``opex_by_category`` — and ``kind`` names a chart type.
    """
    try:
        p = _project_from(payload)
        res = p.run(payload.get("method") or p.method)
    except Exception as exc:                               # noqa: BLE001
        return _err(exc)
    source = payload.get("source") or "equipment_shares"
    kind = payload.get("kind") or "bar"
    data = {
        "equipment_shares": res.equipment_shares,
        "section_shares": res.section_shares,
        "type_shares": res.type_shares,
        "capex_breakdown": res.capex_breakdown,
        "cost_stack": res.cost_stack,
        "opex_items": lambda: res.opex.items,
        "opex_variable": lambda: res.opex.variable_items,
        "opex_fixed": lambda: res.opex.fixed_items,
        "opex_by_category": lambda: res.opex.by_category,
    }.get(source)
    if data is None:
        return _err(f"unknown series {source!r}")
    series = data()
    try:
        spec = _charts.custom_chart(kind, payload.get("title") or source.replace("_", " "),
                                    series, currency=res.currency)
    except Exception as exc:                               # noqa: BLE001
        return _err(exc)
    return _ok(chart=spec.to_dict(), svg=spec.svg())


# ============================================================================
# export
# ============================================================================
def export(payload: dict) -> dict:
    """Produce a downloadable artefact. Returns text plus a suggested filename."""
    fmt = payload.get("format") or "html"
    try:
        p = _project_from(payload)
    except Exception as exc:                               # noqa: BLE001
        return _err(exc)
    if fmt == "json":
        return _ok(filename=_filename(p, "", "teakit.json"),
                   mime="application/json", content=p.to_json())
    try:
        res = p.run(payload.get("method") or p.method)
    except Exception as exc:                               # noqa: BLE001
        return _err(exc, traceback.format_exc())

    if fmt in ("xlsx", "excel"):
        comparison = {}
        for m in COSTING_METHODS:
            try:
                comparison[m] = p.run(m).unit_cost
            except Exception:                              # noqa: BLE001
                comparison[m] = None
        # A workbook is binary, and this API is JSON. Base64 is the transport;
        # `encoding` tells the caller to decode rather than write the string.
        raw = _excel.to_xlsx(p, res, comparison)
        return _ok(filename=_filename(p, "estimate", "xlsx"),
                   mime="application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet",
                   encoding="base64",
                   content=base64.b64encode(raw).decode("ascii"),
                   bytes=len(raw))

    if fmt == "html":
        specs = _charts.default_charts(res)
        specs.update(_charts.utility_distribution_charts(res))
        extra = payload.get("extra_charts") or {}
        for name, spec in extra.items():
            try:
                specs[name] = _charts.ChartSpec(**spec)
            except Exception:                              # noqa: BLE001
                pass
        return _ok(filename=_filename(p, "report", "html"), mime="text/html",
                   content=_report.to_html(p, res, specs))
    if fmt == "markdown":
        return _ok(filename=_filename(p, "report", "md"), mime="text/markdown",
                   content=_report.to_markdown(p, res))
    if fmt == "text":
        return _ok(filename=_filename(p, "report", "txt"), mime="text/plain",
                   content=_report.to_text(p, res))
    if fmt in ("equipment_csv", "cashflow_csv", "opex_csv",
               "equipment_utility_csv"):
        fn = {"equipment_csv": _report.equipment_csv,
              "cashflow_csv": _report.cash_flow_csv,
              "opex_csv": _report.opex_csv,
              "equipment_utility_csv": _report.equipment_utility_csv}[fmt]
        try:
            return _ok(filename=_filename(p, fmt[:-4], "csv"), mime="text/csv",
                       content=fn(res))
        except ValueError as exc:
            return _err(exc)
    if fmt == "svg":
        name = payload.get("chart") or "capex_waterfall"
        specs = _charts.default_charts(res)
        if name not in specs:
            return _err(f"no chart {name!r}")
        return _ok(filename=_filename(p, name, "svg"), mime="image/svg+xml",
                   content=specs[name].svg(payload.get("width", 900),
                                           payload.get("height", 460),
                                           bool(payload.get("dark"))))
    return _err(f"unknown format {fmt!r}")


# ============================================================================
# workspace — the folder the application saves into
# ============================================================================
def workspace(payload: dict | None = None) -> dict:
    """Where exports are being written, and what is already there."""
    return _ok(**_workspace.info())


def workspace_set(payload: dict) -> dict:
    """Point the report folder somewhere else and remember the choice."""
    try:
        _workspace.set_dir(payload.get("dir") or "")
    except ValueError as exc:
        return _err(exc)
    return _ok(**_workspace.info())


def workspace_reset(payload: dict | None = None) -> dict:
    """Go back to ``reports/`` beside the application."""
    _workspace.reset_dir()
    return _ok(**_workspace.info())


def workspace_save(payload: dict) -> dict:
    """
    Write one already-rendered export into the report folder.

    The interface calls :func:`export` first and hands the result straight
    back, so the file it saves is byte-for-byte the file it would have
    downloaded.
    """
    try:
        saved = _workspace.save(
            payload.get("filename") or "",
            payload.get("content") or "",
            payload.get("encoding") or "text",
            bool(payload.get("overwrite")))
    except ValueError as exc:
        return _err(exc)
    return _ok(saved=saved, **_workspace.info())


def workspace_open(payload: dict | None = None) -> dict:
    """Open the report folder in the system file manager."""
    try:
        opened = _workspace.reveal((payload or {}).get("path"))
    except ValueError as exc:
        return _err(exc)
    return _ok(opened=opened)


def workspace_pick(payload: dict | None = None) -> dict:
    """
    Show a native folder chooser and adopt whatever it returns.

    ``cancelled`` comes back true when the user closed the dialog, which is not
    an error and must not be reported as one.
    """
    try:
        picked = _workspace.pick_dir((payload or {}).get("dir"))
    except ValueError as exc:
        return _err(exc)
    if not picked:
        return _ok(cancelled=True, **_workspace.info())
    try:
        _workspace.set_dir(picked)
    except ValueError as exc:
        return _err(exc)
    return _ok(cancelled=False, **_workspace.info())


def _stamp() -> str:
    """Local date and time, to the minute, sortable."""
    return time.strftime("%Y%m%d-%H%M")


def _filename(project, suffix: str, ext: str) -> str:
    """
    ``methanol-plant-report-20260829-1432.html``.

    An estimate is revised, and two exports of the same study an hour apart
    are two different answers. The stamp puts them in order in the folder and
    stops the second silently becoming "-2" with nothing to say which is
    which. It is local time, because that is the clock the user revised on.
    """
    tail = f"-{suffix}" if suffix else ""
    return f"{_slug(project.name)}{tail}-{_stamp()}.{ext}"


def _slug(s: str) -> str:
    keep = "".join(c.lower() if c.isalnum() else "-" for c in s)
    while "--" in keep:
        keep = keep.replace("--", "-")
    return keep.strip("-") or "project"


# ============================================================================
# dispatch
# ============================================================================
ENDPOINTS = {
    "meta": meta, "catalogue": catalogue, "describe": describe,
    "utility_defaults": utility_defaults, "exchange_rates": exchange_rates,
    "demo": demo, "blank": blank,
    "run": run, "parameters": parameters, "sensitivity": sensitivity,
    "custom_chart": custom_chart, "utility_chart": utility_chart,
    "export": export, "explain": explain,
    "workspace": workspace, "workspace_set": workspace_set,
    "workspace_reset": workspace_reset, "workspace_save": workspace_save,
    "workspace_open": workspace_open, "workspace_pick": workspace_pick,
}


def dispatch(name: str, payload: dict | None = None) -> dict:
    """
    Route a named call. The single entry point the server uses, so adding an
    endpoint means adding a function and one dict entry.

    >>> dispatch("meta")["ok"]
    True
    >>> dispatch("nope")["ok"]
    False
    """
    fn = ENDPOINTS.get(name)
    if fn is None:
        return _err(f"unknown endpoint {name!r}",
                    f"available: {', '.join(sorted(ENDPOINTS))}")
    try:
        return fn(payload or {})
    except Exception as exc:                               # noqa: BLE001
        return _err(exc, traceback.format_exc())


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
