"""
tea.equipment — Equipment cost scaling (the "six-tenths rule" and friends).
==========================================================================

THE SCALING LAW
---------------
The purchased cost of a piece of equipment rises more slowly than its capacity,
because cost tracks surface area (~L^2) while capacity tracks volume (~L^3).
The standard correlation is a power law::

    C2 / C1 = (S2 / S1) ** n

where

    C1  = base cost         -- known cost of a reference unit
    S1  = base size         -- the *scaled parameter* of that reference unit
    S2  = scaled parameter  -- the size you actually want
    n   = scale factor / scaling exponent / cost exponent

The famous default is **n = 0.6** ("six-tenths rule", Williams 1947), which is
what you use when you have nothing better. Every entry in
:mod:`tea.equipment_data` gives you something better: an `n` regressed from
actual tabulated cost data, plus the size range over which it was fitted.

Estrup (1972) gives a critical review of the six-tenths rule; the short version
is that it is a decent central value but individual equipment types scatter
from about 0.3 to 1.0, so use a fitted exponent when one exists.

FULL SCALING CHAIN
------------------
A cost you can actually use in an estimate needs four corrections applied in
order — this is what :func:`purchased_cost` does::

    C = C_base
        * (S / S_base) ** n          # 1. size          (this module)
        * (I_now / I_base)           # 2. dollar-year   (tea.indices)
        * F_M                        # 3. material      (MATERIAL_FACTORS)
        * F_L                        # 4. location      (caller-supplied)

then :mod:`tea.capital` turns purchased cost into installed and total capital.

SOURCES
-------
Correlations and material factors: DOE/NETL-2002/1169 (Loh, Lyons & White,
2002), https://www.osti.gov/servlets/purl/797810

Scaling-exponent philosophy and the exponent cross-check table: NETL Quality
Guidelines for Energy System Studies, "Capital Cost Scaling Methodology",
https://www.osti.gov/biblio/1893821 — NETL notes that its account-level
exponents are "similar to a six tenth factor approach, however, the exponents
have been trained using several vendor quotes."
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import warnings

from . import indices
from .equipment_data import (
    EQUIPMENT, ALIASES, COLUMNS, PACKING_COST, ADSORBENT_COST, resolve,
    BASIS_YEAR, BASIS_CEPCI, SOURCE, SOURCE_URL,
)

__all__ = [
    "SIX_TENTHS", "MATERIAL_FACTORS", "HX_MATERIAL_FACTORS", "material_factor",
    "LITERATURE_EXPONENTS", "LOCATION_FACTORS_NOTE",
    "EQUIPMENT_TYPES", "type_exponent", "type_installation_basis",
    "equipment_types",
    "scale_cost", "purchased_cost", "n_units_scaling",
    "column_cost", "packing_cost", "adsorbent_cost",
    "Equipment", "catalogue", "describe",
]

#: The default exponent when nothing better is available (Williams, 1947).
SIX_TENTHS = 0.6


# ============================================================================
# Material of construction factors
# ============================================================================
#: Multipliers converting a carbon-steel purchased cost to an alloy cost.
#: Source: DOE/NETL-2002/1169, Table 7 (after Perry's Chemical Engineers'
#: Handbook, 7th ed., 1999).
MATERIAL_FACTORS: dict[str, dict[str, float]] = {
    #  material              pumps etc.   other equipment
    "carbon steel":        {"pump": 1.00, "other": 1.00},
    "ss410":               {"pump": 1.43, "other": 2.00},
    "ss304":               {"pump": 1.70, "other": 2.80},
    "ss316":               {"pump": 1.80, "other": 2.90},
    "ss310":               {"pump": 2.00, "other": 3.33},
    "rubber-lined steel":  {"pump": 1.43, "other": 1.25},
    "bronze":              {"pump": 1.54, "other": 1.54},
    "monel":               {"pump": 3.33, "other": 3.33},
}

#: Shell-and-tube exchanger material factors (shell/tube combinations).
#: Source: DOE/NETL-2002/1169, Table 7.
HX_MATERIAL_FACTORS: dict[str, float] = {
    "cs shell / cs tubes":       1.00,
    "cs shell / al tubes":       1.25,
    "cs shell / monel tubes":    2.08,
    "cs shell / ss304 tubes":    1.67,
    "ss304 shell / ss304 tubes": 2.86,
}

#: Independent cross-check on the fitted exponents. These are the ranges
#: reported across the standard design texts (Peters & Timmerhaus; Towler &
#: Sinnott; Turton et al.) and are given here so you can sanity-check a fitted
#: value before trusting it. Format: (typical, low, high).
LITERATURE_EXPONENTS: dict[str, tuple[float, float, float]] = {
    "centrifugal pump":            (0.60, 0.30, 0.80),
    "reciprocating pump":          (0.70, 0.60, 0.80),
    "centrifugal compressor":      (0.60, 0.50, 0.80),
    "reciprocating compressor":    (0.60, 0.50, 0.85),
    "blower / fan":                (0.60, 0.50, 0.80),
    "shell & tube heat exchanger": (0.65, 0.55, 0.80),
    "air cooler":                  (0.60, 0.50, 0.70),
    "fired heater / furnace":      (0.75, 0.70, 0.85),
    "pressure vessel / drum":      (0.60, 0.30, 0.70),
    "distillation column shell":   (0.60, 0.55, 0.75),
    "storage tank":                (0.60, 0.50, 0.70),
    "reactor":                     (0.60, 0.50, 0.75),
    "cooling tower":               (0.60, 0.55, 0.90),
    "package boiler":              (0.70, 0.60, 0.80),
    "centrifuge":                  (0.70, 0.60, 0.90),
    "rotary dryer":                (0.45, 0.40, 0.60),
    "cyclone separator":           (0.70, 0.60, 0.80),
    "whole plant / process area":  (0.60, 0.50, 0.90),
}

LOCATION_FACTORS_NOTE = """\
LOCATION FACTORS -- supply your own, do not guess.

All correlations here are US Gulf Coast (USGC) basis, F_L = 1.00. Costs
elsewhere in North America differ because of labour rates, productivity,
freight, duty and local content rules. Canadian sites in particular typically
run above USGC, and remote or northern sites substantially so.

Published location-factor sets are proprietary (IHS Markit / S&P Global
International Construction Cost Factors, AACE International RP 28R-03,
Compass International). Get a factor from one of those, from your own
historical projects, or from a contractor -- and record which source you used.
Then pass it as `location_factor` to purchased_cost().
"""

# ============================================================================
# Equipment types
# ============================================================================
#: The equipment-type vocabulary, and where each type's numbers come from.
#:
#: A type is *what kind of machine this is* -- a pump, a fired heater. It is
#: not the correlation (which is one specific machine) and not the plant
#: section (which is where it sits). It is what lets teakit offer a scaling
#: exponent and an installation factor for an item that has no catalogue entry
#: behind it: a vendor quote, or your own correlation.
#:
#: Each entry says:
#:
#: ``family``
#:     the catalogue key prefix whose fitted exponents describe this type, or
#:     ``None`` when the catalogue does not cover it.
#: ``keys``
#:     specific catalogue keys, when the type is narrower than a family (an
#:     air cooler is one entry inside the ``hx`` family).
#: ``literature``
#:     the :data:`LITERATURE_EXPONENTS` entry to quote as a cross-check.
#: ``loh_service``, ``loh_setting``
#:     the DOE/NETL-2002/1169 service regime (Tables 2-5) and setting-labour
#:     class (Table 6) that describe installing this kind of machine. Together
#:     they give the type its installation factor. ``None`` means the report
#:     does not name this type and the plant-level default is used instead.
#:
#: SCALING EXPONENTS -- two independent sources, and this table keeps both so
#: a reviewer sees the disagreement rather than one number with no provenance:
#:
#: *fitted*  the median of the DOE/NETL-2002/1169 Appendix B correlations of
#:           this type, regressed from real vendor quotes. Correlations the
#:           report itself flags as unreliable are excluded.
#: *typical* what the design texts quote (Peters & Timmerhaus; Towler &
#:           Sinnott; Turton), with the range they give.
#:
#: The default offered is the fitted value where there is one, because it
#: comes from cost data rather than from a rule of thumb, and because it is
#: the same data every catalogue correlation in this package is built on.
#: Failing that the literature typical, and failing that 0.60 -- the
#: six-tenths rule (Williams 1947), which is a fallback and not a default.
#: The two can disagree sharply: a rotary dryer fits at 0.95 against a quoted
#: 0.45. Both are shown, and neither is hidden.
EQUIPMENT_TYPES: dict[str, dict] = {
    "agitator":           dict(family="agitator", keys=(), literature=None,
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting="mixer"),
    "air cooler":         dict(family=None, keys=("hx_air_cooler",),
                               literature="air cooler",
                               loh_service="gas_lt400F_lt150psig",
                               loh_setting="cooler"),
    "blower":             dict(family="blower", keys=(),
                               literature="blower / fan",
                               loh_service="gas_lt400F_lt150psig",
                               loh_setting=None),
    "boiler":             dict(family="boiler", keys=(),
                               literature="package boiler",
                               loh_service="gas_gt400F_gt150psig",
                               loh_setting=None),
    "centrifuge":         dict(family="centrifuge", keys=(),
                               literature="centrifuge",
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting="centrifuge"),
    "compressor":         dict(family="compressor", keys=(),
                               literature="centrifugal compressor",
                               loh_service="gas_lt400F_gt150psig",
                               loh_setting=None),
    "conveyor":           dict(family=None, keys=(), literature=None,
                               loh_service="solids_lt400F", loh_setting=None),
    "cooling tower":      dict(family="cooling", keys=(),
                               literature="cooling tower",
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting=None),
    "crusher":            dict(family="crusher", keys=(), literature=None,
                               loh_service="solids_lt400F",
                               loh_setting="crusher"),
    "cyclone":            dict(family=None, keys=(),
                               literature="cyclone separator",
                               loh_service="solids_gas_lt400F_lt150psig",
                               loh_setting="cyclone"),
    "distillation column": dict(family=None, keys=(),
                                literature="distillation column shell",
                                loh_service="gas_lt400F_lt150psig",
                                loh_setting="distillation column"),
    "dryer":              dict(family="dryer", keys=(),
                               literature="rotary dryer",
                               loh_service="solids_gas_lt400F_lt150psig",
                               loh_setting=None),
    "electrolyser":       dict(family=None, keys=(), literature=None,
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting=None),
    "evaporator":         dict(family="evaporator", keys=(), literature=None,
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting="evaporator"),
    "fan":                dict(family="fan", keys=(),
                               literature="blower / fan",
                               loh_service="gas_lt400F_lt150psig",
                               loh_setting=None),
    "filter":             dict(family="filter", keys=(), literature=None,
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting="filter"),
    "fired heater":       dict(family="furnace", keys=(),
                               literature="fired heater / furnace",
                               loh_service="gas_gt400F_gt150psig",
                               loh_setting="furnace"),
    "gasifier":           dict(family=None, keys=(), literature="reactor",
                               loh_service="solids_gas_gt400F_gt150psig",
                               loh_setting="gasifier"),
    "heat exchanger":     dict(family="hx", keys=(),
                               literature="shell & tube heat exchanger",
                               loh_service="gas_lt400F_gt150psig",
                               loh_setting="heat exchanger"),
    "mill":               dict(family="mill", keys=(), literature=None,
                               loh_service="solids_lt400F",
                               loh_setting="ball mill"),
    "pump":               dict(family="pump", keys=(),
                               literature="centrifugal pump",
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting=None),
    "reactor":            dict(family=None, keys=(), literature="reactor",
                               loh_service="gas_gt400F_gt150psig",
                               loh_setting="shift converter"),
    "screen":             dict(family=None, keys=(), literature=None,
                               loh_service="solids_lt400F",
                               loh_setting="screen"),
    "scrubber":           dict(family=None, keys=(), literature=None,
                               loh_service="gas_lt400F_lt150psig",
                               loh_setting="scrubber"),
    "tank":               dict(family="tank", keys=(),
                               literature="storage tank",
                               loh_service="liquid_slurry_lt150psig",
                               loh_setting="storage tank"),
    "turbine":            dict(family="turbine", keys=(), literature=None,
                               loh_service="gas_gt400F_gt150psig",
                               loh_setting=None),
    "vessel":             dict(family="vessel", keys=(),
                               literature="pressure vessel / drum",
                               loh_service="gas_lt400F_gt150psig",
                               loh_setting=None),
}


def _fitted_exponent(spec: dict) -> tuple[float | None, int]:
    """
    Median fitted exponent for a type, and how many correlations it came from.

    Correlations the source report flags unreliable are dropped: a vibratory
    centrifuge fitted at n = 3.16 over a 1.2x size span is an artefact of the
    regression, not a statement about centrifuges.
    """
    keys = list(spec.get("keys") or ())
    fam = spec.get("family")
    if fam:
        keys += [k for k in EQUIPMENT if k.split("_")[0] == fam]
    vals = sorted(EQUIPMENT[k]["exponent"] for k in set(keys)
                  if k in EQUIPMENT and EQUIPMENT[k].get("reliable", True))
    if not vals:
        return None, 0
    n = len(vals)
    mid = n // 2
    return (vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0), n


def type_exponent(equipment_type: str) -> dict:
    """
    Everything known about the scaling exponent for an equipment type.

    Returns ``exponent`` (what to use), ``basis`` (where it came from),
    ``fitted``/``n_fitted``, ``typical``/``low``/``high``, and a ``source``
    sentence fit to show a user.

    An unknown type is not an error -- you are allowed to write "quench
    tower" -- it simply falls back to the six-tenths rule and says so.

    Examples
    --------
    >>> r = type_exponent("pump")
    >>> round(r["exponent"], 4), r["n_fitted"]
    (0.5722, 7)
    >>> round(type_exponent("reactor")["exponent"], 2)
    0.6
    >>> type_exponent("quench tower")["basis"]
    'six-tenths rule'
    """
    spec = EQUIPMENT_TYPES.get((equipment_type or "").strip().lower())
    lit = LITERATURE_EXPONENTS.get((spec or {}).get("literature") or "")
    fitted, n_fitted = _fitted_exponent(spec) if spec else (None, 0)
    typical, low, high = lit if lit else (None, None, None)

    if fitted is not None:
        exponent, basis = fitted, "fitted"
        source = (f"median of {n_fitted} {equipment_type} correlation"
                  f"{'s' if n_fitted != 1 else ''} regressed from "
                  f"DOE/NETL-2002/1169 Appendix B")
    elif typical is not None:
        exponent, basis = typical, "literature"
        source = ("typical value across Peters & Timmerhaus, Towler & Sinnott "
                  "and Turton")
    else:
        exponent, basis = SIX_TENTHS, "six-tenths rule"
        source = ("no published exponent for this type — the six-tenths rule "
                  "(Williams 1947). It is a fallback, not a default: fit your "
                  "own from two quoted sizes if the cost matters")
    return {"type": equipment_type, "exponent": exponent, "basis": basis,
            "fitted": fitted, "n_fitted": n_fitted, "typical": typical,
            "low": low, "high": high, "source": source}


def type_installation_basis(equipment_type: str) -> dict:
    """
    The DOE/NETL service regime and setting-labour class for an equipment type.

    ``service`` and ``setting`` are ``None`` where the report does not name
    this type, and the caller supplies the plant-level default instead.

    >>> type_installation_basis("fired heater")["setting"]
    'furnace'
    >>> type_installation_basis("quench tower")["service"] is None
    True
    """
    spec = EQUIPMENT_TYPES.get((equipment_type or "").strip().lower()) or {}
    return {"type": equipment_type, "service": spec.get("loh_service"),
            "setting": spec.get("loh_setting")}


def equipment_types() -> list[dict]:
    """Every known type with its exponent evidence, for the interface."""
    out = []
    for name in EQUIPMENT_TYPES:
        rec = type_exponent(name)
        rec.update(type_installation_basis(name))
        out.append(rec)
    return out


# ============================================================================
# Core scaling
# ============================================================================
def scale_cost(base_cost: float,
               base_size: float,
               new_size: float,
               exponent: float = SIX_TENTHS) -> float:
    """
    The power law, bare. C2 = C1 * (S2/S1) ** n

    Parameters
    ----------
    base_cost : float
        Known cost C1 of the reference unit, in some dollar-year.
    base_size : float
        Scaled parameter S1 of the reference unit.
    new_size : float
        Scaled parameter S2 you want a cost for. Same units as `base_size`.
    exponent : float
        Scale factor n. Defaults to the six-tenths rule.

    Returns
    -------
    float
        Cost C2, in the same dollar-year as `base_cost`.

    Examples
    --------
    A 1,000 gal/min pump costs $50k; what does 4,000 gal/min cost at n = 0.6?

    >>> round(scale_cost(50_000, 1_000, 4_000, 0.6))
    114870
    """
    if base_size <= 0 or new_size <= 0:
        raise ValueError("sizes must be positive")
    if base_cost < 0:
        raise ValueError("base_cost must be non-negative")
    return base_cost * (new_size / base_size) ** exponent


def n_units_scaling(base_cost: float,
                    base_size: float,
                    new_size: float,
                    exponent: float,
                    max_size: float) -> tuple[float, int, float]:
    """
    Cost a duty that exceeds the largest available single unit by installing
    N identical trains.

    Economy of scale stops at the vendor's maximum shop-fabricable size. Beyond
    it, cost becomes *linear* in capacity (N units at the same unit cost), which
    is why extrapolating a power law past `valid_max` is one of the most common
    ways to badly under-estimate a large plant.

    Returns
    -------
    (total_cost, n_units, size_each)

    Examples
    --------
    >>> total, n, each = n_units_scaling(66_278, 3_455, 200_000, 0.708, 70_000)
    >>> n
    3
    """
    if new_size <= max_size:
        return scale_cost(base_cost, base_size, new_size, exponent), 1, new_size
    n_units = math.ceil(new_size / max_size)
    size_each = new_size / n_units
    each = scale_cost(base_cost, base_size, size_each, exponent)
    return each * n_units, n_units, size_each


def material_factor(equipment: str, material: str = "carbon steel") -> float:
    """
    Material factor F_M for one equipment key.

    Rotating machinery takes a smaller alloy penalty than static equipment
    because a smaller fraction of its cost is wetted metal: an all-316 pump is
    1.8x carbon steel, an all-316 vessel is 2.9x.

    Source: DOE/NETL-2002/1169, Table 7.

    >>> material_factor("pump", "ss316")
    1.8
    >>> material_factor("separator", "ss316")
    2.9
    """
    key = resolve(equipment) if equipment in ALIASES or equipment in EQUIPMENT else equipment
    mat = material.strip().lower()
    if mat not in MATERIAL_FACTORS:
        raise KeyError(f"Unknown material {material!r}. "
                       f"Options: {', '.join(MATERIAL_FACTORS)}")
    group = "pump" if key.startswith(("pump_", "compressor_", "blower_", "fan_")) \
        else "other"
    return MATERIAL_FACTORS[mat][group]


def purchased_cost(equipment: str,
                   size: float,
                   year: int = 2025,
                   quarter: int | None = None,
                   material: str = "carbon steel",
                   location_factor: float = 1.0,
                   allow_extrapolation: bool = False,
                   use_multiple_units: bool = True,
                   quiet: bool = False) -> "CostResult":
    """
    Full purchased-equipment cost: size scaling + escalation + material + location.

    Parameters
    ----------
    equipment : str
        An EQUIPMENT key or an alias, e.g. "pump", "separator", "hx_shell_tube".
    size : float
        Scaled parameter, in the correlation's `size_unit` (see describe()).
    year, quarter : int
        Target dollar-year (and optionally quarter) for the result.
    material : str
        Key into MATERIAL_FACTORS. Correlations are carbon steel.
    location_factor : float
        USGC = 1.0. See LOCATION_FACTORS_NOTE.
    allow_extrapolation : bool
        Permit sizes outside the fitted range. Off by default.
    use_multiple_units : bool
        If `size` exceeds `valid_max`, split into N parallel units rather than
        extrapolating the power law.
    quiet : bool
        Suppress warnings.

    Returns
    -------
    CostResult
        Dataclass with `.cost` and the full breakdown of how it was reached.

    Examples
    --------
    >>> r = purchased_cost("hx_shell_tube", 5000, year=2022, quiet=True)
    >>> round(r.cost, -3)
    180000.0
    """
    key = resolve(equipment)
    rec = EQUIPMENT[key]
    notes: list[str] = []

    if not rec["reliable"]:
        # `quiet` suppresses the Python warning, never the note. The note is the
        # audit trail, and teakit.project always calls with quiet=True — dropping
        # it here would let an unreliable fit reach a report unflagged.
        notes.append(f"UNRELIABLE FIT: {rec.get('caution')}")
        if not quiet:
            warnings.warn(
                f"{key}: correlation flagged unreliable ({rec.get('caution')}). "
                "Use the raw tabulated points in DOE/NETL-2002/1169 instead.",
                stacklevel=2,
            )

    lo, hi = rec["valid_min"], rec["valid_max"]
    n_units = 1
    size_each = size

    if size > hi and use_multiple_units:
        base, n_units, size_each = n_units_scaling(
            rec["base_cost"], rec["base_size"], size, rec["exponent"], hi)
        notes.append(
            f"size {size:g} exceeds fitted max {hi:g} {rec['size_unit']}; "
            f"costed as {n_units} parallel units of {size_each:.4g} each")
    else:
        if (size < lo or size > hi):
            msg = (f"size {size:g} is outside the fitted range "
                   f"{lo:g}-{hi:g} {rec['size_unit']} for {key}")
            if not allow_extrapolation:
                raise ValueError(
                    msg + ". Pass allow_extrapolation=True to override, or "
                          "use_multiple_units=True for oversize duties.")
            if not quiet:
                warnings.warn(msg + " (extrapolating)", stacklevel=2)
            notes.append("EXTRAPOLATED beyond fitted range")
        base = scale_cost(rec["base_cost"], rec["base_size"], size, rec["exponent"])

    # 2. escalate to the requested dollar-year
    i_target = indices.cepci(year, quarter=quarter)
    escalated = base * (i_target / BASIS_CEPCI)
    prov = indices.is_provisional(year)
    if prov:
        notes.append(f"CEPCI {year} is provisional: {prov.splitlines()[0]}")

    # 3. material
    mat = material.strip().lower()
    f_m = material_factor(key, mat)

    # 4. location
    final = escalated * f_m * location_factor

    return CostResult(
        equipment=key,
        description=rec["description"],
        size=size,
        size_unit=rec["size_unit"],
        exponent=rec["exponent"],
        base_size=rec["base_size"],
        base_cost=rec["base_cost"],
        cost_1998=base,
        index_from=BASIS_CEPCI,
        index_to=i_target,
        dollar_year=year,
        material=material,
        material_factor=f_m,
        location_factor=location_factor,
        n_units=n_units,
        cost=final,
        notes=notes,
    )


@dataclass
class CostResult:
    """Result of :func:`purchased_cost`, with every intermediate step retained."""
    equipment: str
    description: str
    size: float
    size_unit: str
    exponent: float
    base_size: float
    base_cost: float
    cost_1998: float
    index_from: float
    index_to: float
    dollar_year: int
    material: str
    material_factor: float
    location_factor: float
    n_units: int
    cost: float
    notes: list[str] = field(default_factory=list)

    def __float__(self) -> float:
        return self.cost

    def report(self) -> str:
        """Human-readable audit trail — paste this into an appendix."""
        w = 34
        out = [
            f"{self.equipment}  ({self.description})",
            f"{'size':<{w}} {self.size:>14,.4g} {self.size_unit}",
            f"{'reference size S_base':<{w}} {self.base_size:>14,.4g} {self.size_unit}",
            f"{'reference cost C_base (1998$)':<{w}} {self.base_cost:>14,.0f}",
            f"{'scale factor n':<{w}} {self.exponent:>14.3f}",
            f"{'scaled cost (1998$)':<{w}} {self.cost_1998:>14,.0f}",
            f"{'CEPCI 1998 -> ' + str(self.dollar_year):<{w}} "
            f"{self.index_from:>7.1f} ->{self.index_to:>6.1f}",
            f"{'material factor (' + self.material + ')':<{w}} {self.material_factor:>14.2f}",
            f"{'location factor':<{w}} {self.location_factor:>14.2f}",
        ]
        if self.n_units > 1:
            out.append(f"{'parallel units':<{w}} {self.n_units:>14d}")
        out.append(f"{'PURCHASED COST (' + str(self.dollar_year) + '$)':<{w}} {self.cost:>14,.0f}")
        for note in self.notes:
            out.append(f"  ! {note}")
        return "\n".join(out)


# ============================================================================
# Columns — two-parameter correlations
# ============================================================================
def column_cost(column_type: str,
                diameter_ft: float,
                stages_or_height: float,
                year: int = 2025,
                quarter: int | None = None,
                material: str = "carbon steel",
                location_factor: float = 1.0,
                allow_extrapolation: bool = False,
                quiet: bool = False) -> CostResult:
    """
    Purchased cost of a distillation or absorption column.

        C = C_base * (D/D_base)**n1 * (S/S_base)**n2

    A column has two independent size dimensions and they scale very
    differently, so a single-parameter power law will mislead you. Fitted
    diameter exponents run 1.37-1.68 for tray columns — **above 1.0**, because
    the shell wall must thicken with diameter at a fixed design pressure, so
    mass grows faster than area. Stage count is a much weaker lever (~0.5).
    Practically: shaving trays saves little; shaving diameter saves a lot.

    Parameters
    ----------
    column_type : str
        A COLUMNS key, e.g. "column_sieve_tray_150psig", or a short alias:
        "sieve", "valve", "packed" (defaults to the 150 psig variant),
        or "sieve 15", "packed 15" for the low-pressure variants.
    diameter_ft : float
        Shell inside diameter, ft.
    stages_or_height : float
        Number of trays (tray columns) or packed height in ft (packed columns).

    Returns
    -------
    CostResult
        Trays ARE included for tray columns. Packing is NOT included for
        packed columns — add it with :func:`packing_cost`.

    Examples
    --------
    >>> r = column_cost("sieve", 12, 30, year=2025, quiet=True)
    >>> round(r.cost, -4)
    950000.0
    """
    aliases = {
        "valve": "column_valve_tray_150psig", "sieve": "column_sieve_tray_150psig",
        "packed": "column_packed_150psig",
        "valve 15": "column_valve_tray_15psig", "sieve 15": "column_sieve_tray_15psig",
        "packed 15": "column_packed_15psig",
        "distillation column": "column_sieve_tray_150psig",
        "absorber": "column_packed_150psig", "stripper": "column_packed_150psig",
        "tray column": "column_sieve_tray_150psig",
    }
    key = column_type if column_type in COLUMNS else aliases.get(
        column_type.strip().lower().replace("psig", "").strip())
    if key is None or key not in COLUMNS:
        raise KeyError(f"Unknown column type {column_type!r}. "
                       f"Options: {', '.join(COLUMNS)} or aliases "
                       f"{', '.join(sorted(aliases))}")
    rec = COLUMNS[key]
    notes: list[str] = []

    for val, (lo, hi), what in ((diameter_ft, rec["valid_1"], "diameter"),
                                (stages_or_height, rec["valid_2"], rec["size_unit_2"])):
        if not (lo <= val <= hi):
            msg = f"{what} {val:g} outside fitted range {lo:g}-{hi:g} for {key}"
            if not allow_extrapolation:
                raise ValueError(msg + ". Pass allow_extrapolation=True to override.")
            if not quiet:
                warnings.warn(msg + " (extrapolating)", stacklevel=2)
            notes.append(f"EXTRAPOLATED on {what}")

    base = (rec["base_cost"]
            * (diameter_ft / rec["base_size_1"]) ** rec["exponent_1"]
            * (stages_or_height / rec["base_size_2"]) ** rec["exponent_2"])

    i_target = indices.cepci(year, quarter=quarter)
    escalated = base * (i_target / BASIS_CEPCI)
    if indices.is_provisional(year):
        notes.append(f"CEPCI {year} is provisional")

    mat = material.strip().lower()
    if mat not in MATERIAL_FACTORS:
        raise KeyError(f"Unknown material {material!r}")
    f_m = MATERIAL_FACTORS[mat]["other"]

    if rec["kind"] == "packed":
        notes.append("packing NOT included — add it with packing_cost()")

    return CostResult(
        equipment=key, description=rec["description"],
        size=diameter_ft, size_unit=f"{rec['size_unit_1']} x "
                                   f"{stages_or_height:g} {rec['size_unit_2']}",
        exponent=rec["exponent_1"], base_size=rec["base_size_1"],
        base_cost=rec["base_cost"], cost_1998=base,
        index_from=BASIS_CEPCI, index_to=i_target, dollar_year=year,
        material=material, material_factor=f_m,
        location_factor=location_factor, n_units=1,
        cost=escalated * f_m * location_factor, notes=notes,
    )


def packing_cost(packing_type: str,
                 nominal_size_in: float,
                 volume_ft3: float,
                 year: int = 2025) -> float:
    """
    Cost of column packing, escalated to `year`.

    Source: DOE/NETL-2002/1169, Table 1 (1st Quarter 1998 US$/ft³).

    Note the extreme spread by material: 2-inch Pall rings are $8/ft³ in
    polypropylene and $76/ft³ in stainless — nearly 10x. Packing material is a
    first-order cost decision, not a detail.

    Examples
    --------
    >>> round(packing_cost("pall rings stainless", 2.0, 500, 2025))
    79054
    """
    key = packing_type.strip().lower()
    if key not in PACKING_COST:
        raise KeyError(f"Unknown packing {packing_type!r}. "
                       f"Options: {', '.join(PACKING_COST)}")
    table = PACKING_COST[key]
    if nominal_size_in not in table:
        raise KeyError(f"{packing_type} not tabulated at {nominal_size_in} in. "
                       f"Sizes available: {sorted(table)}")
    return (table[nominal_size_in] * volume_ft3
            * indices.cepci(year) / BASIS_CEPCI)


def adsorbent_cost(adsorbent: str, volume_ft3: float, year: int = 2025) -> float:
    """
    Cost of an adsorbent bed fill, escalated to `year`.
    Source: DOE/NETL-2002/1169, Table 1 (1st Quarter 1998 US$/ft³).

    >>> round(adsorbent_cost("activated carbon", 1000, 2025))
    52009
    """
    key = adsorbent.strip().lower()
    if key not in ADSORBENT_COST:
        raise KeyError(f"Unknown adsorbent {adsorbent!r}. "
                       f"Options: {', '.join(ADSORBENT_COST)}")
    return ADSORBENT_COST[key] * volume_ft3 * indices.cepci(year) / BASIS_CEPCI


@dataclass
class Equipment:
    """
    One line item on an equipment list.

    Examples
    --------
    >>> e = Equipment("P-101", "pump", 1200, quantity=2, spare=1)
    >>> e.total_quantity
    3
    """
    tag: str
    kind: str
    size: float
    quantity: int = 1
    spare: int = 0
    material: str = "carbon steel"
    note: str = ""

    @property
    def total_quantity(self) -> int:
        return self.quantity + self.spare

    def cost(self, year: int = 2025, location_factor: float = 1.0, **kw) -> float:
        """Total purchased cost of all units of this item."""
        r = purchased_cost(self.kind, self.size, year=year,
                           material=self.material,
                           location_factor=location_factor, **kw)
        return r.cost * self.total_quantity


def equipment_list_cost(items: list[Equipment],
                        year: int = 2025,
                        location_factor: float = 1.0,
                        **kw) -> tuple[float, list[tuple[str, float]]]:
    """
    Total purchased cost of an equipment list.

    Returns
    -------
    (total, [(tag, cost), ...])
    """
    rows = [(it.tag, it.cost(year=year, location_factor=location_factor, **kw))
            for it in items]
    return sum(c for _, c in rows), rows


# ============================================================================
# Catalogue helpers
# ============================================================================
def catalogue(group: str | None = None) -> list[str]:
    """List available equipment keys, optionally filtered by prefix."""
    keys = sorted(EQUIPMENT)
    if group:
        keys = [k for k in keys if k.startswith(group)]
    return keys


def describe(equipment: str) -> str:
    """Print everything known about one correlation."""
    key = resolve(equipment)
    r = EQUIPMENT[key]
    lines = [
        f"{key}",
        f"  {r['description']}",
        f"  scaled parameter : {r['size_unit']}",
        f"  valid range      : {r['valid_min']:g} to {r['valid_max']:g} {r['size_unit']}",
        f"  scale factor n   : {r['exponent']:.3f}",
        f"  base size        : {r['base_size']:g} {r['size_unit']}",
        f"  base cost        : ${r['base_cost']:,.0f}  (1998 Q1 US$, carbon steel, USGC)",
        f"  fit quality      : R2 = {r['r_squared']:.3f}, rel. RMSE = {r['rel_rmse']:.1%}, "
        f"n = {r['n_points']} points",
        f"  source           : {SOURCE}",
    ]
    if not r["reliable"]:
        lines.append(f"  !! CAUTION       : {r['caution']}")
    return "\n".join(lines)


def exponent_table() -> str:
    """Side-by-side table of every fitted exponent, for a report appendix."""
    hdr = f"{'equipment':<34}{'n':>7}{'range':>28}  {'unit':<22}{'R2':>6}"
    rows = [hdr, "-" * len(hdr)]
    for k in sorted(EQUIPMENT):
        r = EQUIPMENT[k]
        rng = f"{r['valid_min']:g} - {r['valid_max']:g}"
        flag = "" if r["reliable"] else "  (!)"
        rows.append(f"{k:<34}{r['exponent']:>7.3f}{rng:>28}  "
                    f"{r['size_unit']:<22}{r['r_squared']:>6.3f}{flag}")
    rows.append("")
    rows.append("(!) = flagged unreliable, see describe() for the reason")
    return "\n".join(rows)
