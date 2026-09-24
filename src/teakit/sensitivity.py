"""
teakit.sensitivity — Which assumptions actually drive the answer?
================================================================

A point estimate from a Class 4 study is a number with a -15/+30% band around
it, and the band is not symmetric across inputs: three or four assumptions
usually account for nearly all of it, and the rest could be wrong by a factor of
two without anyone noticing. Sensitivity analysis finds those three or four. It
is the most useful thing in a TEA and the most often skipped.

Everything here works on any :class:`teakit.project.Project` and any parameter
addressable by dotted path, so nothing is hard-coded to a particular study
shape::

    tornado(p, ["finance.discount_rate", "opex.raw_materials.feed.price"])

FOUR TOOLS
----------
:func:`tornado`
    Vary each parameter one at a time between a low and a high case; sort by the
    width of the swing. The standard chart in every published TEA.
:func:`sweep`
    One parameter across a range, for a line plot. Shows curvature that a
    two-point tornado hides — and capital charge against discount rate is
    strongly curved.
:func:`two_way`
    A grid over two parameters, for a contour or heat map. Use it when two
    assumptions interact, which the tornado assumes they do not.
:func:`monte_carlo`
    Sample every uncertain input simultaneously from a distribution and report
    the resulting spread. This is the only method here that produces a
    probability, and the probability is only as good as the distributions —
    which are usually guesses. Report P10/P50/P90, not a mean.

A CAUTION ON TORNADOES
----------------------
A one-at-a-time tornado holds everything else at base. Where inputs are
correlated — and feedstock price, product price and utility price usually are —
it will understate the true spread. Use :func:`monte_carlo` with correlated
draws, or at minimum say in the caption that the bars are independent.

Everything is pure stdlib: :mod:`random` for sampling, no NumPy.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field

__all__ = [
    "SensitivityParam", "TornadoResult", "SweepResult", "GridResult",
    "MonteCarloResult",
    "tornado", "sweep", "two_way", "monte_carlo", "breakeven",
    "DEFAULT_RANGES", "suggest_params", "METRICS",
]


# ============================================================================
# Metrics
# ============================================================================
def _metric_value(result, metric: str) -> float:
    """Pull a scalar out of a ProjectResult by name."""
    if metric in ("msp", "unit_cost", "lcop"):
        return result.unit_cost
    if metric == "npv":
        return result.cash_flow.npv if result.cash_flow else float("nan")
    if metric == "irr":
        return (result.cash_flow.irr or float("nan")) if result.cash_flow else float("nan")
    if metric == "toc":
        return result.capital.toc
    if metric == "tasc":
        return result.capital.tasc
    if metric == "tpc":
        return result.capital.tpc
    if metric == "bec":
        return result.bec
    if metric == "opex":
        return result.opex.total
    if metric == "opex_fixed":
        return result.opex.fixed_total
    if metric == "opex_variable":
        return result.opex.variable_total
    if metric == "capital_component":
        return result.capital_component
    if metric == "payback":
        return (result.cash_flow.payback_year if result.cash_flow
                and result.cash_flow.payback_year is not None else float("nan"))
    raise ValueError(f"Unknown metric {metric!r}. Options: {', '.join(METRICS)}")


#: Metrics any of the routines below can target.
METRICS = ("msp", "npv", "irr", "toc", "tasc", "tpc", "bec", "opex",
           "opex_fixed", "opex_variable", "capital_component", "payback")

#: Conventional low/high multipliers for a first-pass tornado, keyed by the
#: tail of the parameter path. These reflect how well each class of input is
#: usually known, not a uniform +/-20% applied to everything — which is the
#: commonest way to produce a misleading tornado.
DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "discount_rate": (0.70, 1.40),        # 7-14% around a 10% base
    "tax_rate": (0.80, 1.20),
    "plant_life_years": (0.67, 1.17),
    "construction_years": (0.67, 1.67),
    "project_contingency_frac": (0.75, 1.50),
    "process_contingency_frac": (0.50, 2.00),
    "epc_fee_frac": (0.86, 1.14),
    "price": (0.70, 1.30),                # commodity prices
    "rate": (0.90, 1.10),                 # consumption rates from a flowsheet
    "size": (0.80, 1.20),
    "annual_production": (0.90, 1.05),    # rarely beats nameplate
    "capacity_factor": (0.90, 1.03),
    "operating_hours": (0.90, 1.05),
    "operator_salary": (0.85, 1.20),
    "maintenance_frac_capital": (0.67, 1.67),
    "__default__": (0.75, 1.25),
}


def _range_for(path: str) -> tuple[float, float]:
    tail = path.rsplit(".", 1)[-1]
    if tail in DEFAULT_RANGES:
        return DEFAULT_RANGES[tail]
    for k, v in DEFAULT_RANGES.items():
        if k != "__default__" and path.endswith(k):
            return v
    return DEFAULT_RANGES["__default__"]


#: Path tails that carry no information on their own, so the label falls back
#: to the parent segment as well.
_GENERIC_TAILS = {"price", "rate", "size", "quantity", "annual_production",
                  "value", "cost", "frac"}


@dataclass
class SensitivityParam:
    """
    One axis of a sensitivity study.

    Give ``low`` and ``high`` as absolute values, or leave them out and let
    :data:`DEFAULT_RANGES` pick multipliers appropriate to the parameter class.

    >>> lo, hi = SensitivityParam("finance.discount_rate").resolve(0.10)
    >>> round(lo, 4), round(hi, 4)
    (0.07, 0.14)
    """
    path: str
    label: str = ""
    low: float | None = None
    high: float | None = None
    low_mult: float | None = None
    high_mult: float | None = None
    unit: str = ""

    def resolve(self, base: float) -> tuple[float, float]:
        lo_m, hi_m = _range_for(self.path)
        lo = self.low if self.low is not None else base * (self.low_mult or lo_m)
        hi = self.high if self.high is not None else base * (self.high_mult or hi_m)
        return lo, hi

    def display(self) -> str:
        """A readable label. ``opex.utilities.electricity.price`` becomes
        ``electricity price``, not ``price``.

        >>> SensitivityParam("opex.utilities.electricity.price").display()
        'electricity price'
        """
        if self.label:
            return self.label
        parts = self.path.split(".")
        tail = parts[-1]
        if tail in _GENERIC_TAILS and len(parts) > 2:
            return f"{parts[-2]} {tail}".replace("_", " ")
        return tail.replace("_", " ")


def suggest_params(project, n: int = 10) -> list[SensitivityParam]:
    """
    A sensible default set of tornado axes for a project, chosen by what
    usually matters: the discount rate, the biggest feed and utility prices,
    capital contingency, capacity factor and plant life.

    Candidates that do not resolve to a number on *this* project are dropped —
    ``opex.maintenance_frac_capital``, for instance, is ``None`` whenever it is
    inherited from a fixed-cost convention rather than set explicitly, and there
    is no base value to perturb.

    >>> from teakit.project import Project
    >>> len(suggest_params(Project())) > 0
    True
    """
    candidates: list[SensitivityParam] = [
        SensitivityParam("finance.discount_rate", "discount rate"),
        SensitivityParam("capital.project_contingency_frac", "project contingency"),
        SensitivityParam("finance.plant_life_years", "plant life"),
        SensitivityParam("opex.capacity_factor", "capacity factor"),
        SensitivityParam("opex.maintenance_frac_capital", "maintenance factor"),
        SensitivityParam("capital.epc_fee_frac", "EPC fee"),
    ]
    # biggest variable-cost lines, by annual spend
    streams = [(s, s.annual_cost(project.opex.operating_hours,
                                 project.opex.capacity_factor))
               for s in project.opex.all_streams()]
    streams.sort(key=lambda kv: -abs(kv[1]))
    from .project import _container_of
    for s, _ in streams[:4]:
        candidates.append(SensitivityParam(
            f"opex.{_container_of(s)}.{s.name}.price", f"{s.name} price",
            unit=f"$/{s.unit}"))
    for p in project.products.products:
        if p.role != "primary" and p.price is not None:
            candidates.append(SensitivityParam(f"products.{p.name}.price",
                                               f"{p.name} price", unit=f"$/{p.unit}"))
    return [c for c in candidates if _resolves(project, c.path)][:n]


def _resolves(project, path: str) -> bool:
    """True when ``path`` reads back a real, perturbable number."""
    try:
        v = project[path]
    except Exception:                                     # noqa: BLE001
        return False
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _assign(project, path: str, value: float) -> None:
    """
    Set a parameter, respecting its type.

    Some inputs are counts, not quantities: plant life, construction years,
    MACRS recovery period, equipment quantity. A continuous sweep or a
    triangular draw produces 27.3 years, which is meaningless and which the
    depreciation schedule rejects outright. Where the current value is an
    integer, the perturbed value is rounded to one — so a sweep over plant life
    steps through whole years instead of silently failing every trial.

    >>> from teakit.project import Project
    >>> p = Project()
    >>> _assign(p, "finance.plant_life_years", 27.3)
    >>> p.finance.plant_life_years
    27
    >>> _assign(p, "finance.discount_rate", 0.113)
    >>> p.finance.discount_rate
    0.113
    """
    current = project[path]
    if isinstance(current, int) and not isinstance(current, bool):
        value = int(round(value))
    project[path] = value


# ============================================================================
# 1. Tornado
# ============================================================================
@dataclass
class TornadoResult:
    """Output of :func:`tornado`, sorted widest-swing first."""
    metric: str
    base_value: float
    rows: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def report(self, width: int = 30) -> str:
        out = [f"TORNADO — {self.metric}, base = {self.base_value:,.4g}",
               "=" * 78,
               f"{'parameter':<{width}}{'low':>12}{'high':>12}"
               f"{'swing':>12}{'% of base':>12}"]
        for r in self.rows:
            out.append(f"{r['label'][:width]:<{width}}{r['low_value']:>12,.4g}"
                       f"{r['high_value']:>12,.4g}{r['swing']:>12,.4g}"
                       f"{r['swing_pct']:>11.1f}%")
        if self.notes:
            out.append("")
            out += [f"  ! {n}" for n in self.notes]
        return "\n".join(out)

    def to_dict(self) -> dict:
        return {"metric": self.metric, "base_value": self.base_value,
                "rows": self.rows, "notes": self.notes}


def tornado(project, params=None, metric: str = "msp",
            method: str | None = None) -> TornadoResult:
    """
    One-at-a-time sensitivity.

    Parameters
    ----------
    project : Project
    params : list of SensitivityParam or list of str
        Plain strings are accepted and get default ranges. ``None`` calls
        :func:`suggest_params`.
    metric : str
        See :data:`METRICS`.
    method : str, optional
        Override the project's costing method for the whole study.

    Examples
    --------
    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import opex, products
    >>> p = Project(dollar_year=2025)
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.opex.raw_materials = [opex.Stream("feed", 2.0, "tonne", 300.0)]
    >>> p.products.products = [products.Product("widget", 15_000, "tonne")]
    >>> t = tornado(p, ["finance.discount_rate", "opex.raw_materials.feed.price"])
    >>> t.rows[0]["swing"] >= t.rows[-1]["swing"]
    True
    """
    if params is None:
        params = suggest_params(project)
    params = [SensitivityParam(p) if isinstance(p, str) else p for p in params]

    base_res = project.run(method)
    base = _metric_value(base_res, metric)
    rows, notes = [], []

    for sp in params:
        try:
            base_p = float(project[sp.path])
        except (KeyError, TypeError, ValueError) as exc:
            notes.append(f"skipped {sp.path}: {exc}")
            continue
        lo, hi = sp.resolve(base_p)
        vals = {}
        for tag, v in (("low", lo), ("high", hi)):
            trial = project.copy()
            try:
                _assign(trial, sp.path, v)
                vals[tag] = _metric_value(trial.run(method), metric)
            except Exception as exc:                      # noqa: BLE001
                notes.append(f"{sp.path} @ {tag}={v:,.4g} failed: {exc}")
                vals[tag] = float("nan")
        lo_v, hi_v = vals["low"], vals["high"]
        swing = abs(hi_v - lo_v)
        rows.append(dict(
            path=sp.path, label=sp.display(), unit=sp.unit,
            base_param=base_p, low_param=lo, high_param=hi,
            low_value=lo_v, high_value=hi_v,
            low_delta=lo_v - base, high_delta=hi_v - base,
            swing=swing, swing_pct=100.0 * swing / base if base else float("nan")))

    rows.sort(key=lambda r: -(r["swing"] if r["swing"] == r["swing"] else -1))
    notes.append("bars are one-at-a-time and assume the inputs are independent; "
                 "where they are correlated the true spread is wider")
    return TornadoResult(metric=metric, base_value=base, rows=rows, notes=notes)


# ============================================================================
# 2. One-way sweep
# ============================================================================
@dataclass
class SweepResult:
    """Output of :func:`sweep` — an x/y series ready to plot."""
    path: str
    label: str
    metric: str
    x: list[float]
    y: list[float]
    base_x: float
    base_y: float
    unit: str = ""
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"path": self.path, "label": self.label, "metric": self.metric,
                "x": self.x, "y": self.y, "base_x": self.base_x,
                "base_y": self.base_y, "unit": self.unit,
                "failures": self.failures}


def sweep(project, path: str, values=None, metric: str = "msp",
          n: int = 11, span: tuple[float, float] | None = None,
          method: str | None = None, label: str = "") -> SweepResult:
    """
    Vary one parameter across a range.

    ``values`` may be given explicitly; otherwise ``n`` points are taken over
    ``span`` (as multipliers of the base value), defaulting to the class range
    from :data:`DEFAULT_RANGES`.

    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import opex, products
    >>> p = Project(dollar_year=2025)
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.products.products = [products.Product("widget", 15_000, "tonne")]
    >>> s = sweep(p, "finance.discount_rate", n=5)
    >>> len(s.x), s.y[0] < s.y[-1]
    (5, True)
    """
    base_p = float(project[path])
    if values is None:
        lo_m, hi_m = span or _range_for(path)
        lo, hi = base_p * lo_m, base_p * hi_m
        values = [lo + (hi - lo) * i / (n - 1) for i in range(n)] if n > 1 else [base_p]
    xs, ys, fails = [], [], []
    for v in values:
        trial = project.copy()
        try:
            _assign(trial, path, v)
            v = trial[path]                    # may have been rounded to an int
            ys.append(_metric_value(trial.run(method), metric))
            xs.append(v)
        except Exception as exc:                          # noqa: BLE001
            fails.append(f"{v:,.4g}: {exc}")
    base_y = _metric_value(project.run(method), metric)
    return SweepResult(path=path, label=label or path.rsplit(".", 1)[-1].replace("_", " "),
                       metric=metric, x=xs, y=ys, base_x=base_p, base_y=base_y,
                       failures=fails)


# ============================================================================
# 3. Two-way grid
# ============================================================================
@dataclass
class GridResult:
    """Output of :func:`two_way` — z[i][j] for y[i], x[j]."""
    x_path: str
    y_path: str
    x: list[float]
    y: list[float]
    z: list[list[float]]
    metric: str
    x_label: str = ""
    y_label: str = ""

    def to_dict(self) -> dict:
        return {"x_path": self.x_path, "y_path": self.y_path, "x": self.x,
                "y": self.y, "z": self.z, "metric": self.metric,
                "x_label": self.x_label, "y_label": self.y_label}


def two_way(project, x_path: str, y_path: str, metric: str = "msp",
            nx: int = 7, ny: int = 7,
            x_values=None, y_values=None,
            method: str | None = None) -> GridResult:
    """
    Grid two parameters against each other.

    ``nx * ny`` full project runs, so keep the grid small on a DCF study — each
    point solves an MSP by iteration.
    """
    def axis(path, values, n):
        if values is not None:
            return list(values)
        b = float(project[path])
        lo_m, hi_m = _range_for(path)
        lo, hi = b * lo_m, b * hi_m
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    xs, ys = axis(x_path, x_values, nx), axis(y_path, y_values, ny)
    z: list[list[float]] = []
    for yv in ys:
        row = []
        for xv in xs:
            trial = project.copy()
            try:
                _assign(trial, x_path, xv)
                _assign(trial, y_path, yv)
                row.append(_metric_value(trial.run(method), metric))
            except Exception:                             # noqa: BLE001
                row.append(float("nan"))
        z.append(row)
    return GridResult(x_path=x_path, y_path=y_path, x=xs, y=ys, z=z, metric=metric,
                      x_label=x_path.rsplit(".", 1)[-1].replace("_", " "),
                      y_label=y_path.rsplit(".", 1)[-1].replace("_", " "))


# ============================================================================
# 4. Monte Carlo
# ============================================================================
@dataclass
class MonteCarloResult:
    """Output of :func:`monte_carlo`."""
    metric: str
    samples: list[float]
    base_value: float
    percentiles: dict[str, float]
    mean: float
    stdev: float
    inputs: list[str]
    n_failed: int = 0
    notes: list[str] = field(default_factory=list)

    def histogram(self, bins: int = 20) -> tuple[list[float], list[int]]:
        """Bin edges and counts, for plotting."""
        if not self.samples:
            return [], []
        lo, hi = min(self.samples), max(self.samples)
        if hi == lo:
            return [lo, hi], [len(self.samples)]
        w = (hi - lo) / bins
        edges = [lo + i * w for i in range(bins + 1)]
        counts = [0] * bins
        for s in self.samples:
            k = min(int((s - lo) / w), bins - 1)
            counts[k] += 1
        return edges, counts

    def report(self) -> str:
        p = self.percentiles
        out = [f"MONTE CARLO — {self.metric}, {len(self.samples):,} successful trials",
               "=" * 60,
               f"  base (deterministic)   {self.base_value:>14,.4g}",
               f"  mean                   {self.mean:>14,.4g}",
               f"  std dev                {self.stdev:>14,.4g}", ""]
        for k in ("P5", "P10", "P25", "P50", "P75", "P90", "P95"):
            if k in p:
                out.append(f"  {k:<22} {p[k]:>14,.4g}")
        if self.n_failed:
            out.append(f"\n  {self.n_failed} trials failed and were discarded")
        out += [""] + [f"  ! {n}" for n in self.notes]
        return "\n".join(out)

    def to_dict(self) -> dict:
        edges, counts = self.histogram()
        return {"metric": self.metric, "base_value": self.base_value,
                "percentiles": self.percentiles, "mean": self.mean,
                "stdev": self.stdev, "n": len(self.samples),
                "n_failed": self.n_failed, "inputs": self.inputs,
                "hist_edges": edges, "hist_counts": counts, "notes": self.notes}


def _draw(rng: random.Random, spec: dict, base: float) -> float:
    """One sample from a distribution spec."""
    dist = spec.get("dist", "triangular")
    if dist == "triangular":
        lo = spec.get("low", base * 0.8)
        hi = spec.get("high", base * 1.2)
        mode = spec.get("mode", base)
        return rng.triangular(lo, hi, mode)
    if dist == "uniform":
        return rng.uniform(spec.get("low", base * 0.8), spec.get("high", base * 1.2))
    if dist == "normal":
        return rng.gauss(spec.get("mean", base), spec.get("sd", base * 0.1))
    if dist == "lognormal":
        import math
        mu = math.log(spec.get("median", base))
        return rng.lognormvariate(mu, spec.get("sigma", 0.25))
    if dist == "pert":
        # Beta-PERT: smoother than triangular, widely used in cost risk work
        lo = spec.get("low", base * 0.8)
        hi = spec.get("high", base * 1.2)
        mode = spec.get("mode", base)
        if hi <= lo:
            return lo
        lam = spec.get("lambda", 4.0)
        a = 1 + lam * (mode - lo) / (hi - lo)
        b = 1 + lam * (hi - mode) / (hi - lo)
        return lo + rng.betavariate(a, b) * (hi - lo)
    raise ValueError(f"Unknown distribution {dist!r}")


def monte_carlo(project, distributions: dict[str, dict], n: int = 500,
                metric: str = "msp", seed: int | None = 0,
                method: str | None = None) -> MonteCarloResult:
    """
    Sample every uncertain input at once.

    Parameters
    ----------
    distributions : dict
        ``{dotted_path: spec}``. Each spec is a dict with ``dist`` in
        ``{"triangular", "pert", "uniform", "normal", "lognormal"}`` and the
        matching parameters. Anything omitted defaults relative to the base
        value, so ``{"finance.discount_rate": {}}`` is legal and gives a
        triangular +/-20%.
    n : int
        Trials. A DCF study runs an MSP solve per trial, so 500 is a reasonable
        ceiling for interactive use and 5,000 for an overnight run.
    seed : int or None
        Fixed by default, because an unreproducible risk analysis is not an
        analysis.

    Examples
    --------
    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import products
    >>> p = Project(dollar_year=2025)
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.products.products = [products.Product("widget", 15_000, "tonne")]
    >>> r = monte_carlo(p, {"finance.discount_rate": {"low": 0.06, "high": 0.15}},
    ...                 n=40, seed=1)
    >>> r.percentiles["P10"] <= r.percentiles["P90"]
    True
    """
    rng = random.Random(seed)
    base_res = project.run(method)
    base = _metric_value(base_res, metric)

    notes: list[str] = []
    bases: dict[str, float] = {}
    for path in distributions:
        if _resolves(project, path):
            bases[path] = float(project[path])
        else:
            notes.append(f"skipped {path}: no numeric base value to perturb")
    distributions = {k: v for k, v in distributions.items() if k in bases}
    if not distributions:
        raise ValueError("no sampleable parameters — every path given resolves to "
                         "None or a non-number on this project")

    samples, failed = [], 0
    for _ in range(n):
        trial = project.copy()
        try:
            for path, spec in distributions.items():
                _assign(trial, path, _draw(rng, spec, bases[path]))
            samples.append(_metric_value(trial.run(method), metric))
        except Exception:                                 # noqa: BLE001
            failed += 1

    samples = [s for s in samples if s == s]              # drop NaN
    pct: dict[str, float] = {}
    if samples:
        ordered = sorted(samples)
        for name, q in (("P5", 0.05), ("P10", 0.10), ("P25", 0.25), ("P50", 0.50),
                        ("P75", 0.75), ("P90", 0.90), ("P95", 0.95)):
            k = min(int(q * (len(ordered) - 1) + 0.5), len(ordered) - 1)
            pct[name] = ordered[k]
    notes += [
        "the output distribution is only as good as the input distributions, "
        "which are usually judgement rather than data — report P10/P50/P90 and "
        "state where the ranges came from",
        "inputs are sampled independently; correlation between prices would "
        "widen the tails",
    ]
    return MonteCarloResult(
        metric=metric, samples=samples, base_value=base, percentiles=pct,
        mean=statistics.fmean(samples) if samples else float("nan"),
        stdev=statistics.pstdev(samples) if len(samples) > 1 else 0.0,
        inputs=list(distributions), n_failed=failed, notes=notes)


# ============================================================================
# 5. Breakeven
# ============================================================================
def breakeven(project, path: str, target: float, metric: str = "msp",
              lo: float | None = None, hi: float | None = None,
              tol: float = 1e-6, max_iter: int = 60,
              method: str | None = None) -> float | None:
    """
    Solve for the value of one parameter that puts ``metric`` at ``target``.

    "What feedstock price do I need for a $2.00/kg product?" or "what carbon
    price makes this NPV-positive?" — both are this function. Bisection, so the
    metric must be monotone in the parameter over the bracket. Returns ``None``
    if the bracket does not contain a sign change.

    >>> from teakit.project import Project, EquipmentItem
    >>> from teakit import opex, products
    >>> p = Project(dollar_year=2025)
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
    >>> p.opex.raw_materials = [opex.Stream("feed", 2.0, "tonne", 300.0)]
    >>> p.products.products = [products.Product("widget", 15_000, "tonne")]
    >>> base = p.run().unit_cost
    >>> x = breakeven(p, "opex.raw_materials.feed.price", base * 0.9)
    >>> x is not None and x < 300
    True
    """
    base_p = float(project[path])
    lo_m, hi_m = _range_for(path)
    lo = lo if lo is not None else base_p * min(lo_m, 0.1)
    hi = hi if hi is not None else base_p * max(hi_m, 5.0)

    def f(v: float) -> float:
        trial = project.copy()
        _assign(trial, path, v)
        return _metric_value(trial.run(method), metric) - target

    try:
        f_lo, f_hi = f(lo), f(hi)
    except Exception:                                     # noqa: BLE001
        return None
    if f_lo != f_lo or f_hi != f_hi or f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        try:
            f_mid = f(mid)
        except Exception:                                 # noqa: BLE001
            return None
        if abs(f_mid) < tol or (hi - lo) < tol * max(1.0, abs(mid)):
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
