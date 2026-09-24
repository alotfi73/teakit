"""
teakit.opex — Annual operating cost: what the plant spends every year.
=====================================================================

Capital estimating gets the attention, but for most chemical plants the
levelised product cost is dominated by operating cost, and within that by one or
two feed or utility lines. A capital estimate good to -15/+30% sitting on top of
a feedstock price guessed to a factor of two is not a Class 4 estimate.

STRUCTURE
---------
This module splits annual cost the way an operator would, not the way an
accountant would::

    VARIABLE   scales with production rate
      raw materials, catalysts and chemicals
      utilities (electricity, fuel, steam, water, refrigeration, ...)
      waste disposal and effluent treatment
      royalties

    FIXED      incurred whether or not the plant runs
      operating labour + supervision (headcount x loaded salary)
      maintenance (materials + labour, as a fraction of installed capital)
      operating supplies, laboratory charges
      property tax and insurance
      plant overhead, general & administrative

    NOT AN OPERATING COST
      depreciation           -- handled in teakit.dcf, never here
      interest / return      -- handled by the discount rate, never here
      working capital        -- a capital item, recovered at end of life

Double-counting depreciation or financing inside OPEX and *again* in the
levelised-cost formula is the most common single error in a first TEA. This
module refuses to hold either.

FIXED-COST CONVENTIONS
----------------------
Two established conventions are implemented, and you should pick one and say
which:

* **NREL** (:data:`NREL_FIXED`) — maintenance at 3% of installed equipment
  cost, property tax and insurance at 0.7% of fixed capital investment,
  and an explicit staffing plan. Sparse, transparent, and the basis of every
  NREL biorefinery design report.
* **Peters & Timmerhaus / Turton** (:data:`PT_FIXED`) — the classic factored
  set with plant overhead at 50-70% of labour-plus-maintenance, laboratory at
  10-20% of operating labour, and so on. More lines, more places to
  double-count.

:func:`turton_com` implements Turton's one-line cost of manufacture as an
independent cross-check on whatever you build up line by line. If the two
disagree by more than ~20% you have made an error in one of them.

SOURCES
-------
Humbird, D. et al. (2011), "Process Design and Economics for Biochemical
    Conversion of Lignocellulosic Biomass to Ethanol", NREL/TP-5100-47764,
    §5 (variable and fixed operating costs), Table 22 (staffing).
    https://www.osti.gov/biblio/1013269
NETL-PUB-22580, §2.5 and §4 — the O&M cost categories used in NETL baselines,
    and the fixed/variable split that feeds the COE equation.
Turton, R., Bailie, R.C., Whiting, W.B., Shaeiwitz, J.A., Bhattacharyya, D.,
    "Analysis, Synthesis and Design of Chemical Processes", 4th/5th ed., Ch. 8:
    COM_d = 0.180*FCI + 2.73*C_OL + 1.23*(C_UT + C_WT + C_RM).
Peters, M.S., Timmerhaus, K.D., West, R.E., "Plant Design and Economics for
    Chemical Engineers", 5th ed., Ch. 6 — the factored fixed-cost table.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from . import defaults

__all__ = [
    "Stream", "LaborItem", "LaborModel", "LaborResult",
    "OperatingCost", "OpexResult",
    "NREL_FIXED", "PT_FIXED", "NETL_FIXED", "FIXED_CONVENTIONS",
    "turton_com", "operators_turton",
]


# ============================================================================
# 1. Line items
# ============================================================================
@dataclass
class Stream:
    """
    One variable-cost (or credit) line: a rate, a unit and a price.

    A *credit* is a negative price or a negative rate — do not invent a separate
    class for it. Byproducts that you intend to price into the levelised cost
    belong in :mod:`teakit.products`, not here; use a ``Stream`` credit only for
    material you are genuinely paid to take away (e.g. a tipping fee received).

    Parameters
    ----------
    name : str
        Free text; used as the chart label.
    rate : float
        Consumption per hour (``basis="hour"``) or per operating year
        (``basis="year"``). Rates are quoted at **full production rate** and are
        scaled down by the capacity factor.
    unit : str
        Physical unit matching ``price``.
    price : float
        Cost per unit, in project dollars.
    category : {"raw_material", "utility", "waste", "catalyst", "royalty", "other"}
        Grouping for rollups and charts.
    basis : {"hour", "year"}
        Whether ``rate`` is hourly or annual.
    scales_with_rate : bool
        ``False`` pins the line to a fixed annual amount regardless of capacity
        factor — e.g. a take-or-pay gas contract, or an annual catalyst charge
        that is replaced on a calendar schedule.
    source : str
        Provenance for the price, carried into the report.

    Examples
    --------
    >>> s = Stream("methanol feed", rate=12.5, unit="tonne", price=420.0,
    ...            category="raw_material", basis="hour")
    >>> round(s.annual_cost(8000, 1.0))
    42000000
    >>> round(s.annual_cost(8000, 0.90))
    37800000
    """
    name: str
    rate: float
    unit: str = ""
    price: float = 0.0
    category: str = "raw_material"
    basis: str = "hour"
    scales_with_rate: bool = True
    source: str = ""
    note: str = ""

    def annual_quantity(self, operating_hours: float, capacity_factor: float = 1.0) -> float:
        """Physical quantity consumed per year."""
        cf = capacity_factor if self.scales_with_rate else 1.0
        if self.basis == "hour":
            return self.rate * operating_hours * cf
        if self.basis == "year":
            return self.rate * cf
        raise ValueError("basis must be 'hour' or 'year'")

    def annual_cost(self, operating_hours: float, capacity_factor: float = 1.0) -> float:
        """Annual cost of this line, in project dollars."""
        return self.annual_quantity(operating_hours, capacity_factor) * self.price

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Stream":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class LaborItem:
    """One row of the staffing plan."""
    role: str
    count: float
    annual_salary: float
    shift_position: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LaborResult:
    """Output of :meth:`LaborModel.evaluate`."""
    headcount: float
    base_payroll: float
    burden: float
    supervision: float
    total_labor: float
    by_role: dict[str, float]
    notes: list[str] = field(default_factory=list)


@dataclass
class LaborModel:
    """
    Operating labour, built either from an explicit staffing plan or from a
    headcount-per-shift rule.

    Two ways in:

    1. **Explicit plan** — pass ``staff`` as a list of :class:`LaborItem`. This
       is what a real estimate does, and what NREL publishes.
    2. **Rule of thumb** — set ``operators_per_shift`` and let the model apply
       the shift-coverage multiplier. Use :func:`operators_turton` to get the
       per-shift number from the process configuration.

    Parameters
    ----------
    staff : list of LaborItem
        Explicit plan. Takes precedence over ``operators_per_shift``.
    operators_per_shift : float
        Operators needed to man the plant at any instant.
    shift_coverage : float
        Employees required per continuously-manned seat. 4.8 by default; see
        :data:`teakit.defaults.SHIFT_COVERAGE`.
    operator_salary : float
        Base annual salary of one operator, before burden.
    supervision_frac : float
        Direct supervision as a fraction of operating labour. 15-25% typical.
        Set to 0 if supervisors are already itemised in ``staff``.
    burden_frac : float
        Payroll tax, insurance, pension and paid leave, as a fraction of base
        salary. 30-40% typical in the U.S.
    location : str
        Applies the regional wage multiplier from
        :data:`teakit.defaults.LOCATIONS`.

    Examples
    --------
    >>> m = LaborModel(operators_per_shift=4, operator_salary=78_000)
    >>> r = m.evaluate()
    >>> r.headcount
    19.2
    >>> round(r.total_labor)
    2396160
    """
    staff: list[LaborItem] = field(default_factory=list)
    operators_per_shift: float = 0.0
    shift_coverage: float = defaults.SHIFT_COVERAGE
    operator_salary: float = defaults.OPERATOR_WAGE
    supervision_frac: float = 0.25
    burden_frac: float = 0.35
    location: str = "USGC"

    def evaluate(self) -> LaborResult:
        notes: list[str] = []
        wage_mult = defaults.location_factor(self.location, "labor")
        if wage_mult != 1.0:
            notes.append(f"wages x{wage_mult:.2f} for {self.location}")

        by_role: dict[str, float] = {}
        headcount = 0.0
        base = 0.0

        if self.staff:
            for it in self.staff:
                n = it.count * (self.shift_coverage if it.shift_position else 1.0)
                pay = n * it.annual_salary * wage_mult
                by_role[it.role] = by_role.get(it.role, 0.0) + pay
                headcount += n
                base += pay
            notes.append(f"explicit staffing plan, {len(self.staff)} roles")
        elif self.operators_per_shift:
            headcount = self.operators_per_shift * self.shift_coverage
            base = headcount * self.operator_salary * wage_mult
            by_role["shift operator"] = base
            notes.append(f"{self.operators_per_shift:g} operators/shift "
                         f"x {self.shift_coverage:g} coverage = "
                         f"{headcount:.1f} employees")
        else:
            notes.append("no labour defined")

        burden = base * self.burden_frac
        supervision = base * self.supervision_frac
        if supervision:
            by_role["supervision"] = supervision
        total = base + burden + supervision
        if burden:
            notes.append(f"burden at {self.burden_frac:.0%} of base salary")
        return LaborResult(headcount=headcount, base_payroll=base, burden=burden,
                           supervision=supervision, total_labor=total,
                           by_role=by_role, notes=notes)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["staff"] = [s.to_dict() if hasattr(s, "to_dict") else s for s in self.staff]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LaborModel":
        d = dict(d)
        d["staff"] = [LaborItem(**s) for s in d.get("staff", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def operators_turton(n_non_particulate: int, n_particulate: int = 0) -> float:
    """
    Operators required per shift, from the process configuration.

        N_OL = sqrt(6.29 + 31.7 * P**2 + 0.23 * N_np)

    where ``P`` is the number of processing steps handling **particulate**
    solids (transport, distribution, particulate removal) and ``N_np`` is the
    number of non-particulate steps — compressors, towers, reactors, heaters,
    exchangers. Pumps and vessels are *not* counted; they are assumed to be
    attended as part of the units they serve.

    Source: Turton et al., Ch. 8, from Alkhayat & Gerrard (1984).

    Examples
    --------
    A plant with 12 non-particulate steps and no solids handling:

    >>> round(operators_turton(12), 2)
    3.01

    Add two solids-handling steps and the requirement more than doubles:

    >>> round(operators_turton(12, 2), 2)
    11.66
    """
    return (6.29 + 31.7 * n_particulate ** 2 + 0.23 * n_non_particulate) ** 0.5


# ============================================================================
# 2. Fixed-cost conventions
# ============================================================================
#: NREL biorefinery convention (NREL/TP-5100-47764 §5.2). Sparse and explicit:
#: an itemised staffing plan, maintenance as a fraction of installed equipment
#: cost, and a single combined property-tax-and-insurance line.
NREL_FIXED = dict(
    maintenance_frac_capital=0.030,
    maintenance_basis="installed",
    insurance_tax_frac_capital=0.007,
    insurance_tax_basis="fci",
    overhead_frac_labor=0.90,
    lab_frac_labor=0.0,
    supplies_frac_maintenance=0.0,
    ga_frac_labor=0.0,
    source="NREL/TP-5100-47764 §5.2 — 3% of ISBL for maintenance, 0.7% of FCI "
           "for property insurance and local tax, 90% of labour for overhead "
           "and benefits",
)

#: Peters & Timmerhaus / Turton factored convention. More lines and a higher
#: total; watch for double-counting between ``overhead_frac_labor`` and the
#: labour burden inside :class:`LaborModel`.
PT_FIXED = dict(
    maintenance_frac_capital=0.050,
    maintenance_basis="fci",
    insurance_tax_frac_capital=0.020,
    insurance_tax_basis="fci",
    overhead_frac_labor=0.60,
    lab_frac_labor=0.15,
    supplies_frac_maintenance=0.15,
    ga_frac_labor=0.20,
    source="Peters & Timmerhaus 5th ed. Ch.6 midpoints: maintenance 2-10% FCI, "
           "local taxes 1-4% FCI plus insurance 0.4-1%, plant overhead 50-70% "
           "of labour+supervision+maintenance, laboratory 10-20% of labour",
)

#: NETL power-plant convention: fixed O&M is dominated by labour and
#: maintenance material, with administrative labour taken as a fraction of
#: total labour. NETL reports fixed and variable O&M separately because the
#: COE equation treats them differently.
NETL_FIXED = dict(
    maintenance_frac_capital=0.020,
    maintenance_basis="tpc",
    insurance_tax_frac_capital=0.020,
    insurance_tax_basis="tpc",
    overhead_frac_labor=0.30,
    lab_frac_labor=0.0,
    supplies_frac_maintenance=0.0,
    ga_frac_labor=0.25,
    source="NETL-PUB-22580 §4 — property taxes and insurance at 2% of TPC/yr, "
           "administrative and support labour at 25% of operating and "
           "maintenance labour",
)

FIXED_CONVENTIONS = {
    "NREL": NREL_FIXED,
    "Peters & Timmerhaus": PT_FIXED,
    "NETL": NETL_FIXED,
}


# ============================================================================
# 3. The operating cost model
# ============================================================================
@dataclass
class OpexResult:
    """Output of :meth:`OperatingCost.evaluate`."""
    operating_hours: float
    capacity_factor: float
    variable_total: float
    fixed_total: float
    total: float
    variable_items: dict[str, float]
    fixed_items: dict[str, float]
    by_category: dict[str, float]
    #: ``{line name: category}`` for every variable line, so a reader can be
    #: shown the utility subtotal, the feed subtotal and the waste subtotal
    #: beside the lines that make them up. :attr:`by_category` has the totals
    #: but not the membership, and re-deriving membership from a name is
    #: guesswork the moment two lines are called the same thing.
    variable_categories: dict[str, str] = field(default_factory=dict)
    labor: LaborResult | None = None
    quantities: dict[str, tuple[float, str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # -- convenience ------------------------------------------------------
    @property
    def items(self) -> dict[str, float]:
        """Every line, variable then fixed, in one dict."""
        return {**self.variable_items, **self.fixed_items}

    def unit_cost(self, annual_production: float) -> float:
        """Total OPEX per unit of product."""
        if annual_production <= 0:
            raise ValueError("annual_production must be positive")
        return self.total / annual_production

    def largest(self, n: int = 5) -> list[tuple[str, float]]:
        """The ``n`` biggest lines — where to spend your next hour of work.

        >>> r = OperatingCost(fci=1e8, raw_materials=[Stream("feed", 10, "t", 500)]
        ...                  ).evaluate()
        >>> r.largest(1)[0][0]
        'feed'
        """
        return sorted(self.items.items(), key=lambda kv: -abs(kv[1]))[:n]

    def report(self, currency: str = "$", width: int = 46) -> str:
        """Human-readable annual operating cost sheet."""
        w = width
        out = ["ANNUAL OPERATING COST", "=" * (w + 18)]
        out.append(f"{'operating hours per year':<{w}}{self.operating_hours:>18,.0f}")
        out.append(f"{'capacity factor':<{w}}{self.capacity_factor:>18.1%}")
        out.append("")
        out.append("VARIABLE")
        for k, v in sorted(self.variable_items.items(), key=lambda kv: -abs(kv[1])):
            q = self.quantities.get(k)
            label = f"  {k}" + (f"  [{q[0]:,.0f} {q[1]}/yr]" if q else "")
            out.append(f"{label:<{w}}{v:>18,.0f}")
        out.append(f"{'  subtotal variable':<{w}}{self.variable_total:>18,.0f}")
        out.append("")
        out.append("FIXED")
        for k, v in sorted(self.fixed_items.items(), key=lambda kv: -abs(kv[1])):
            out.append(f"{'  ' + k:<{w}}{v:>18,.0f}")
        out.append(f"{'  subtotal fixed':<{w}}{self.fixed_total:>18,.0f}")
        out.append("-" * (w + 18))
        out.append(f"{'TOTAL ANNUAL OPERATING COST':<{w}}{self.total:>18,.0f}")
        if self.labor:
            out.append(f"{'  (headcount)':<{w}}{self.labor.headcount:>18,.1f}")
        out.append("")
        out.append("Excludes depreciation, interest and return on capital by "
                   "construction.")
        for n in self.notes:
            out.append(f"  ! {n}")
        return "\n".join(out)


@dataclass
class OperatingCost:
    """
    Annual operating cost of a plant.

    Parameters
    ----------
    fci : float
        Fixed capital investment used as the basis for factored fixed costs.
        Feed it the TOC (or TPC — say which) from :class:`teakit.capital.NETLCapitalCost`.
    installed_equipment_cost : float
        ISBL / installed equipment cost, used when ``maintenance_basis`` is
        ``"installed"``. Defaults to ``fci`` if not given, which will overstate
        maintenance — set it.
    tpc : float
        Total plant cost, used when a basis of ``"tpc"`` is selected.
    operating_hours : float
        Hours per year the plant runs. 8,000 is the conventional default.
    capacity_factor : float
        Output relative to nameplate *while running*. Multiplies every line
        flagged ``scales_with_rate``.
    raw_materials, utilities, waste, other_variable : list of Stream
        Variable cost lines. Kept in separate lists so the report and the charts
        can roll them up without guessing from the ``category`` field.
    labor : LaborModel
        Operating labour.
    convention : {"NREL", "Peters & Timmerhaus", "NETL", "custom"}
        Selects a coherent set of factored fixed-cost fractions. Any fraction
        set explicitly on the instance overrides the convention.
    royalty_frac_revenue : float
        Royalties as a fraction of revenue, applied by
        :class:`teakit.project.Project` where revenue is known. Left at 0 here.
    extra_fixed : dict
        Any named fixed cost the factored set does not cover — a land lease, a
        licence fee, a fixed take-or-pay charge.

    Examples
    --------
    A 100 MUSD plant burning 10 t/h of feed at 500 $/t, four operators a shift:

    >>> op = OperatingCost(
    ...     fci=100e6, installed_equipment_cost=60e6,
    ...     raw_materials=[Stream("feed", 10, "tonne", 500)],
    ...     utilities=[Stream("electricity", 5000, "kWh", 0.081)],
    ...     labor=LaborModel(operators_per_shift=4),
    ...     convention="NREL")
    >>> r = op.evaluate()
    >>> round(r.variable_total)
    43240000
    >>> round(r.fixed_total)
    7052704
    >>> round(r.total)
    50292704
    """
    fci: float = 0.0
    installed_equipment_cost: float | None = None
    tpc: float | None = None

    operating_hours: float = 8000.0
    capacity_factor: float = 1.0

    raw_materials: list[Stream] = field(default_factory=list)
    utilities: list[Stream] = field(default_factory=list)
    waste: list[Stream] = field(default_factory=list)
    other_variable: list[Stream] = field(default_factory=list)

    #: One price per named utility for the whole study, in $/unit. Equipment
    #: consumption is charged through this, so a tariff is set once and every
    #: machine drawing on it moves together — see
    #: :meth:`teakit.project.Project.utility_price_book`. Anything absent
    #: falls back to the plant-level line of that name, then to the shipped
    #: catalogue.
    utility_prices: dict[str, float] = field(default_factory=dict)

    labor: LaborModel | None = None
    convention: str = "NREL"

    # Factored fixed costs. None means "take it from the convention".
    maintenance_frac_capital: float | None = None
    maintenance_basis: str | None = None          # fci | installed | tpc
    insurance_tax_frac_capital: float | None = None
    insurance_tax_basis: str | None = None
    overhead_frac_labor: float | None = None
    lab_frac_labor: float | None = None
    supplies_frac_maintenance: float | None = None
    ga_frac_labor: float | None = None

    royalty_frac_revenue: float = 0.0
    extra_fixed: dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def _conv(self, key: str):
        explicit = getattr(self, key)
        if explicit is not None:
            return explicit
        conv = FIXED_CONVENTIONS.get(self.convention)
        if conv is None:
            return 0.0 if key.endswith("_frac_capital") or "frac" in key else "fci"
        return conv[key]

    def _capital_basis(self, which: str) -> float:
        if which == "installed":
            return self.installed_equipment_cost or self.fci
        if which == "tpc":
            return self.tpc or self.fci
        return self.fci

    # ------------------------------------------------------------------
    def all_streams(self) -> list[Stream]:
        """Every variable line in one list."""
        return [*self.raw_materials, *self.utilities, *self.waste, *self.other_variable]

    def evaluate(self) -> OpexResult:
        """Compute the annual operating cost."""
        notes: list[str] = []
        h, cf = self.operating_hours, self.capacity_factor
        if not 0 < cf <= 1.5:
            raise ValueError("capacity_factor must be in (0, 1.5]")
        if h <= 0 or h > 8784:
            raise ValueError("operating_hours must be in (0, 8784]")

        variable: dict[str, float] = {}
        var_cat: dict[str, str] = {}
        quantities: dict[str, tuple[float, str]] = {}
        by_cat: dict[str, float] = {}

        for s in self.all_streams():
            c = s.annual_cost(h, cf)
            key = s.name
            n = 2
            while key in variable:                    # keep duplicate names distinct
                key, n = f"{s.name} ({n})", n + 1
            variable[key] = c
            var_cat[key] = s.category or "other"
            if s.unit:
                quantities[key] = (s.annual_quantity(h, cf), s.unit)
            by_cat[s.category] = by_cat.get(s.category, 0.0) + c
        variable_total = sum(variable.values())

        # --- fixed ---------------------------------------------------------
        fixed: dict[str, float] = {}
        lab_res = self.labor.evaluate() if self.labor else None
        labor_cost = lab_res.total_labor if lab_res else 0.0
        if lab_res:
            fixed["operating labour (loaded)"] = labor_cost
            notes.extend(lab_res.notes)

        m_frac = self._conv("maintenance_frac_capital")
        m_basis = self._conv("maintenance_basis")
        maintenance = self._capital_basis(m_basis) * m_frac
        if maintenance:
            fixed[f"maintenance ({m_frac:.1%} of {m_basis.upper()})"] = maintenance

        it_frac = self._conv("insurance_tax_frac_capital")
        it_basis = self._conv("insurance_tax_basis")
        ins_tax = self._capital_basis(it_basis) * it_frac
        if ins_tax:
            fixed[f"property tax + insurance ({it_frac:.1%} of {it_basis.upper()})"] = ins_tax

        supplies = maintenance * self._conv("supplies_frac_maintenance")
        if supplies:
            fixed["operating supplies"] = supplies
        lab_charge = labor_cost * self._conv("lab_frac_labor")
        if lab_charge:
            fixed["laboratory charges"] = lab_charge
        overhead = labor_cost * self._conv("overhead_frac_labor")
        if overhead:
            fixed["plant overhead"] = overhead
        ga = labor_cost * self._conv("ga_frac_labor")
        if ga:
            fixed["general & administrative"] = ga

        for k, v in self.extra_fixed.items():
            fixed[k] = v

        fixed_total = sum(fixed.values())
        by_cat["labour"] = labor_cost
        by_cat["maintenance"] = maintenance + supplies
        by_cat["overhead & admin"] = overhead + ga + lab_charge
        by_cat["insurance & tax"] = ins_tax
        if self.extra_fixed:
            by_cat["other fixed"] = sum(self.extra_fixed.values())

        conv = FIXED_CONVENTIONS.get(self.convention)
        if conv:
            notes.append(f"fixed-cost convention: {self.convention} — {conv['source']}")
        if self.installed_equipment_cost is None and m_basis == "installed":
            notes.append("installed_equipment_cost not set; maintenance was taken "
                         "against FCI, which overstates it")
        if not self.labor:
            notes.append("no labour model — fixed cost excludes payroll entirely")

        return OpexResult(
            operating_hours=h, capacity_factor=cf,
            variable_total=variable_total, fixed_total=fixed_total,
            total=variable_total + fixed_total,
            variable_items=variable, fixed_items=fixed,
            by_category={k: v for k, v in by_cat.items() if v},
            variable_categories=var_cat,
            labor=lab_res, quantities=quantities, notes=notes,
        )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        for k in ("raw_materials", "utilities", "waste", "other_variable"):
            d[k] = [s.to_dict() for s in d[k]]
        d["labor"] = self.labor.to_dict() if self.labor else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "OperatingCost":
        d = dict(d)
        for k in ("raw_materials", "utilities", "waste", "other_variable"):
            d[k] = [Stream.from_dict(s) for s in d.get(k) or []]
        if d.get("labor"):
            d["labor"] = LaborModel.from_dict(d["labor"])
        else:
            d["labor"] = None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ============================================================================
# 4. Independent cross-check
# ============================================================================
def turton_com(fci: float,
               operating_labor: float,
               utilities: float,
               waste_treatment: float,
               raw_materials: float,
               with_depreciation: bool = False) -> dict[str, float]:
    """
    Turton's one-line cost of manufacture, as a check on a built-up estimate.

        COM_d = 0.180*FCI + 2.73*C_OL + 1.23*(C_UT + C_WT + C_RM)

    The three multipliers absorb everything the factored method itemises: the
    0.180 covers maintenance, taxes, insurance and plant overhead against
    capital; the 2.73 covers supervision, benefits, laboratory and
    administration against labour; the 1.23 covers packaging, distribution and
    a share of overhead against materials.

    ``COM`` (with depreciation) adds 0.10*FCI. **For a levelised-cost or DCF
    calculation use** ``COM_d`` — the depreciation is handled by the cash flow
    model, and including it here would charge for capital twice.

    Returns a dict of the components and the total, so you can see which term
    is driving the difference from your line-by-line build-up.

    Examples
    --------
    >>> r = turton_com(100e6, 2.5e6, 4e6, 1e6, 40e6)
    >>> round(r["COM_d"])
    80175000
    >>> round(r["capital_term"])
    18000000
    """
    cap = 0.180 * fci
    lab = 2.73 * operating_labor
    mat = 1.23 * (utilities + waste_treatment + raw_materials)
    com_d = cap + lab + mat
    out = {
        "capital_term": cap,
        "labor_term": lab,
        "material_term": mat,
        "COM_d": com_d,
    }
    if with_depreciation:
        out["depreciation_term"] = 0.10 * fci
        out["COM"] = com_d + 0.10 * fci
    return out


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
