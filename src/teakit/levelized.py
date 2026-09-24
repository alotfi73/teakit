"""
tea.levelized — Levelised cost metrics: LCOE, LCOH, LCOC, LCO-anything.
=======================================================================

This module covers the *formula* methods -- annuity-style calculations that
give you a levelised cost without running a year-by-year cash flow. They come
in two flavours:

SIMPLE METHODS (no interest rate)  ->  see the "SIMPLE" section
    Capital is spread evenly over the plant life with no time value of money.
    These are what you use for a first screen, for teaching, or when you want
    a number that does not depend on a financing assumption. They will always
    be optimistic relative to a discounted result.

DISCOUNTED METHODS (interest rate over plant years)  ->  "ANNUITY" section
    Capital is converted to an annual charge through a Capital Recovery Factor
    or a Fixed Charge Rate, which embeds the cost of capital and (for FCR) the
    tax shield from depreciation.

For the third flavour -- a full year-by-year discounted cash flow solved for
NPV = 0 -- use :mod:`tea.dcf`. The formula methods here are approximations of
that; NETL is explicit that "the formulaic calculations presented here provide
reasonable estimates for research and development comparisons", but that when
technologies go to market "a detailed cash flow estimate is needed".

NAMING
------
LCOE  levelised cost of electricity   $/MWh
LCOH  levelised cost of hydrogen      $/kg
LCOC  levelised cost of CO2 captured  $/tonne
LCOA  levelised cost of ammonia       $/tonne
LCOM  levelised cost of methanol      $/tonne
MSP / MFSP / MESP  minimum (fuel/ethanol) selling price -- the NPV = 0 metric

They are all the same calculation with a different denominator, which is why
:func:`lcox` handles all of them.

SOURCES
-------
NETL (2021), NETL-PUB-22580, "Cost Estimation Methodology for NETL Assessments
    of Power Plant Performance", §3.4 and §3.5, Equations 1-15.
    https://www.netl.doe.gov/projects/files/QGESSCostEstMethodforNETLAssessmentsofPowerPlantPerformance_022621.pdf

NREL Annual Technology Baseline, "Equations & Variables".
    https://atb.nrel.gov/electricity/2024/equations_&_variables

DOE/NREL H2A and H2A-Lite production models (LCOH by DCFROR).
    https://www.nrel.gov/hydrogen/h2a-lite.html
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "wacc", "atwacc", "wacc_atb", "crf", "fcr", "pv_depreciation",
    "simple_levelized_cost", "simple_payback", "simple_roi",
    "capital_charge_method", "annualized_capital",
    "lcox", "netl_coe", "atb_lcoe", "levelization_factor",
    "levelized_fuel_price", "netl_lcoe",
    "NETL_GLOBAL_ASSUMPTIONS", "NETL_FINANCE_IOU",
    "MACRS", "macrs_schedule",
]


# ============================================================================
# NETL reference assumptions, for reproducibility
# ============================================================================
#: NETL-PUB-22580 Exhibit 3-1, global economic assumptions.
NETL_GLOBAL_ASSUMPTIONS = {
    "federal_income_tax": 0.21,
    "state_income_tax": 0.06,
    "effective_tax_rate": 0.2574,
    "depreciation": "20 years, 150% declining balance",
    "investment_tax_credit": 0.0,
    "capex_period_years_gas": 3,
    "capex_period_years_coal": 5,
    "operational_period_years": 30,
    "capital_escalation_real": 0.0,
    "capital_escalation_nominal": 0.03,
    "om_escalation_real": 0.0,
    "om_escalation_nominal": 0.03,
    "working_capital": 0.0,
    "debt_repayment_term": "equal to operational period (formula method)",
}

#: NETL-PUB-22580 Exhibit 3-2, investor-owned-utility finance structure.
NETL_FINANCE_IOU = {
    "nominal": {"debt_frac": 0.55, "cost_of_debt": 0.05, "return_on_equity": 0.10,
                "wacc": 0.0725, "atwacc": 0.0654},
    "real":    {"debt_frac": 0.55, "cost_of_debt": 0.0294, "return_on_equity": 0.0784,
                "wacc": 0.0514, "atwacc": 0.0473},
    "gdp_deflator_1990_2018": 0.0201,
}

#: NETL reference FCR / CRF (Exhibits 3-5, 3-6), IOU, 30-year operation.
NETL_REFERENCE = {"fcr_nominal": 0.0886, "fcr_real": 0.0707,
                  "crf_nominal": 0.0769, "crf_real": 0.0630}


# ============================================================================
# Cost of capital
# ============================================================================
def wacc(debt_frac: float, cost_of_debt: float, return_on_equity: float) -> float:
    """
    Pre-tax weighted average cost of capital (NETL Eq. 1).

        WACC = %Equity * ROE + %Debt * CostOfDebt

    >>> round(wacc(0.55, 0.05, 0.10), 4)
    0.0725
    """
    return (1.0 - debt_frac) * return_on_equity + debt_frac * cost_of_debt


def atwacc(debt_frac: float, cost_of_debt: float, return_on_equity: float,
           effective_tax_rate: float) -> float:
    """
    After-tax WACC (NETL Eq. 2). Interest on debt is tax-deductible.

        ATWACC = %Equity * ROE + %Debt * CostOfDebt * (1 - ETR)

    This -- not the pre-tax WACC -- is the discount rate that belongs in the
    CRF used for a levelised cost, because the levelised cost is a revenue
    requirement on which tax is paid.

    >>> round(atwacc(0.55, 0.05, 0.10, 0.2574), 4)
    0.0654
    """
    return ((1.0 - debt_frac) * return_on_equity
            + debt_frac * cost_of_debt * (1.0 - effective_tax_rate))


def wacc_atb(debt_frac: float, real_roe: float, real_interest: float,
             tax_rate: float, inflation: float) -> float:
    """
    Nominal WACC in the NREL ATB formulation.

        WACC = ( 1 + (1-DF)*[(1+RROE)(1+i) - 1]
                   + DF*[(1+IR)(1+i) - 1]*(1-TR) ) / (1+i) - 1

    Source: NREL ATB, "Equations & Variables".
    Note the ATB convention differs from NETL: the ATB grosses real rates up to
    nominal with the Fisher relation inside the weighting, then divides the
    whole expression by (1+i).
    """
    nom_equity = (1.0 + real_roe) * (1.0 + inflation) - 1.0
    nom_debt = (1.0 + real_interest) * (1.0 + inflation) - 1.0
    top = 1.0 + (1.0 - debt_frac) * nom_equity + debt_frac * nom_debt * (1.0 - tax_rate)
    return top / (1.0 + inflation) - 1.0


def crf(rate: float, years: int) -> float:
    """
    Capital Recovery Factor -- the annuity that repays 1 unit of capital over
    `years` at `rate` (NETL Eq. 10; identical in the NREL ATB).

        CRF = i (1+i)^y / [ (1+i)^y - 1 ]

    Pass a real rate with real cash flows, a nominal rate with nominal ones.

    Examples
    --------
    NETL reference: real ATWACC 4.73%, 30-year operation (Exhibit 3-6).

    >>> round(crf(0.0473, 30), 5)
    0.06306

    (NETL reports 0.0630 to four places -- same number, rounded.)

    Nominal ATWACC 6.54%, 30 years:

    >>> round(crf(0.0654, 30), 4)
    0.0769

    Zero interest degenerates to straight amortisation:

    >>> round(crf(0.0, 20), 4)
    0.05
    """
    if years <= 0:
        raise ValueError("years must be positive")
    if rate == 0:
        return 1.0 / years
    f = (1.0 + rate) ** years
    return rate * f / (f - 1.0)


#: Modified Accelerated Cost Recovery System depreciation fractions, GDS,
#: half-year convention. Source: IRS Publication 946, Table A-1 (3/5/7/10-year
#: are 200% declining balance switching to straight line; 15/20-year are 150%
#: declining balance switching to straight line). NETL uses the 20-year, 150%
#: declining balance schedule.
MACRS: dict[int, list[float]] = {
    3:  [.3333, .4445, .1481, .0741],
    5:  [.2000, .3200, .1920, .1152, .1152, .0576],
    7:  [.1429, .2449, .1749, .1249, .0893, .0892, .0893, .0446],
    10: [.1000, .1800, .1440, .1152, .0922, .0737, .0655, .0655, .0656, .0655,
         .0328],
    15: [.0500, .0950, .0855, .0770, .0693, .0623, .0590, .0590, .0591, .0590,
         .0591, .0590, .0591, .0590, .0591, .0295],
    20: [.03750, .07219, .06677, .06177, .05713, .05285, .04888, .04522, .04462,
         .04461, .04462, .04461, .04462, .04461, .04462, .04461, .04462, .04461,
         .04462, .04461, .02231],
}


def macrs_schedule(recovery_years: int) -> list[float]:
    """Return the MACRS fraction list for a GDS recovery period."""
    if recovery_years not in MACRS:
        raise KeyError(f"MACRS available for {sorted(MACRS)} year property")
    return list(MACRS[recovery_years])


def pv_depreciation(rate: float, schedule: list[float] | int = 20) -> float:
    """
    Present value of the tax depreciation stream, discounted at `rate`
    (the D term in NETL Eq. 11, without the leading CRF).

        PV = sum_n  d_n / (1 + rate)^n

    Parameters
    ----------
    schedule : list of float, or int
        Depreciation fractions by year, or a MACRS recovery period.
    """
    if isinstance(schedule, int):
        schedule = macrs_schedule(schedule)
    return sum(d / (1.0 + rate) ** (n + 1) for n, d in enumerate(schedule))


def fcr(rate: float, years: int,
        effective_tax_rate: float,
        depreciation: list[float] | int | None = 20) -> float:
    """
    Fixed Charge Rate -- revenue per dollar of investment that must be
    collected annually to cover the carrying charges (NETL Eq. 9).

        FCR = CRF / (1 - ETR)  -  ETR * D / (1 - ETR)
        D   = CRF * sum_n  d_n / (1 + rate)^n

    The first term grosses the capital recovery up so that it survives income
    tax; the second gives back the value of the depreciation tax shield.

    Parameters
    ----------
    rate : float
        ATWACC, real or nominal.
    years : int
        Capital recovery period (NETL: 30, equal to the operational period).
    effective_tax_rate : float
        Combined federal + state. NETL: 0.2574.
    depreciation : list, int or None
        Depreciation fractions, a MACRS recovery period, or None for no shield.

    Examples
    --------
    NETL reference values (Exhibit 3-5): FCR real 0.0707, nominal 0.0886.

    >>> round(fcr(0.0473, 30, 0.2574, 20), 5)
    0.07074
    >>> round(fcr(0.0654, 30, 0.2574, 20), 5)
    0.08854

    With no depreciation shield the FCR is just the grossed-up CRF:

    >>> round(fcr(0.0473, 30, 0.2574, None), 4)
    0.0849
    """
    c = crf(rate, years)
    if depreciation is None:
        return c / (1.0 - effective_tax_rate)
    d = c * pv_depreciation(rate, depreciation)
    return c / (1.0 - effective_tax_rate) - effective_tax_rate * d / (1.0 - effective_tax_rate)


# ============================================================================
# SIMPLE methods — no interest rate
# ============================================================================
def simple_levelized_cost(total_capital: float,
                          annual_fixed_opex: float,
                          annual_variable_opex: float,
                          annual_production: float,
                          plant_life_years: int,
                          salvage_value: float = 0.0,
                          byproduct_revenue: float = 0.0) -> dict[str, float]:
    """
    Levelised cost with NO time value of money. The simplest defensible metric.

        LC = [ (CAPEX - salvage) / life + FOM + VOM - byproducts ] / production

    Capital is simply divided by the plant life. There is no discounting, no
    interest, no tax. This is the number to quote when you want to strip out
    every financing assumption -- and the number to caveat when you compare it
    against anything discounted, because it is systematically low. For a
    30-year life, a discounted CRF at 8% is 0.0888 versus 0.0333 here: the
    capital charge is 2.7x larger once you charge for capital.

    Returns
    -------
    dict with the capital, fixed, variable and byproduct contributions
    separately, so you can build a cost-breakdown chart.

    Examples
    --------
    $500M plant, $20M/yr fixed, $30M/yr variable, 100,000 t/yr, 25-year life:

    >>> r = simple_levelized_cost(500e6, 20e6, 30e6, 100_000, 25)
    >>> round(r["levelized_cost"], 2)
    700.0
    """
    if annual_production <= 0:
        raise ValueError("annual_production must be positive")
    if plant_life_years <= 0:
        raise ValueError("plant_life_years must be positive")
    cap_annual = (total_capital - salvage_value) / plant_life_years
    total_annual = cap_annual + annual_fixed_opex + annual_variable_opex - byproduct_revenue
    return {
        "annual_capital_charge": cap_annual,
        "annual_fixed_opex": annual_fixed_opex,
        "annual_variable_opex": annual_variable_opex,
        "annual_byproduct_revenue": byproduct_revenue,
        "total_annual_cost": total_annual,
        "capital_component": cap_annual / annual_production,
        "fixed_component": annual_fixed_opex / annual_production,
        "variable_component": annual_variable_opex / annual_production,
        "byproduct_component": -byproduct_revenue / annual_production,
        "levelized_cost": total_annual / annual_production,
        "method": "simple (undiscounted); capital straight-lined over plant life",
    }


def simple_payback(total_capital: float, annual_net_cash_flow: float) -> float:
    """
    Simple payback period, years. No discounting.

        payback = CAPEX / annual net cash flow

    A screening filter, not a decision metric: it ignores everything that
    happens after payback and ignores the time value of money entirely.

    >>> round(simple_payback(500e6, 80e6), 2)
    6.25
    """
    if annual_net_cash_flow <= 0:
        return float("inf")
    return total_capital / annual_net_cash_flow


def simple_roi(annual_profit: float, total_capital: float) -> float:
    """
    Return on investment, as a fraction per year.

        ROI = annual profit / total capital investment

    >>> round(simple_roi(80e6, 500e6), 3)
    0.16
    """
    return annual_profit / total_capital


def annualized_capital(total_capital: float,
                       plant_life_years: int,
                       rate: float | None = None) -> float:
    """
    Annual capital charge, with or without interest.

    ``rate=None`` or ``rate=0`` gives the simple straight-line charge
    (CAPEX / life); any positive rate applies the CRF.

    >>> round(annualized_capital(500e6, 25))
    20000000
    >>> round(annualized_capital(500e6, 25, 0.08))
    46839390
    """
    if not rate:
        return total_capital / plant_life_years
    return total_capital * crf(rate, plant_life_years)


def capital_charge_method(total_capital: float,
                          annual_capital_charge_rate: float,
                          annual_fixed_opex: float,
                          annual_variable_opex: float,
                          annual_production: float,
                          byproduct_revenue: float = 0.0) -> dict[str, float]:
    """
    The "capital charge factor" shortcut: an all-in percentage of capital per
    year, applied without any explicit financing model.

        LC = (CCF * CAPEX + FOM + VOM - byproducts) / production

    Typical CCF values in North American process industry practice run 10-20%
    of capital per year (covering capital recovery, tax, insurance and local
    property tax). NETL's revision-3 studies used capital charge factors of
    0.105-0.124 (Exhibit B-3). If you use this method, state the CCF you used
    and where it came from -- it hides every financing assumption inside one
    number.
    """
    cap = total_capital * annual_capital_charge_rate
    total = cap + annual_fixed_opex + annual_variable_opex - byproduct_revenue
    return {
        "annual_capital_charge": cap,
        "total_annual_cost": total,
        "capital_component": cap / annual_production,
        "fixed_component": annual_fixed_opex / annual_production,
        "variable_component": annual_variable_opex / annual_production,
        "levelized_cost": total / annual_production,
        "method": f"capital charge factor = {annual_capital_charge_rate:.4f}/yr",
    }


# ============================================================================
# ANNUITY methods — interest rate over plant years
# ============================================================================
@dataclass
class LevelizedResult:
    """Breakdown of a levelised cost, so the contributions can be charted."""
    levelized_cost: float
    unit: str
    capital_component: float
    fixed_component: float
    variable_component: float
    fuel_component: float = 0.0
    byproduct_component: float = 0.0
    charge_rate: float = 0.0
    charge_rate_name: str = "FCR"
    annual_production: float = 0.0
    capital_basis: float = 0.0
    notes: list[str] = field(default_factory=list)

    def __float__(self) -> float:
        return self.levelized_cost

    def report(self) -> str:
        w = 34
        rows = [
            f"{self.charge_rate_name:<{w}}{self.charge_rate:>16.5f} /yr",
            f"{'capital basis':<{w}}{self.capital_basis:>16,.0f}",
            f"{'annual production':<{w}}{self.annual_production:>16,.0f}",
            "-" * (w + 22),
            f"{'capital':<{w}}{self.capital_component:>16,.3f}  {self.unit}",
            f"{'fixed O&M':<{w}}{self.fixed_component:>16,.3f}  {self.unit}",
            f"{'variable O&M':<{w}}{self.variable_component:>16,.3f}  {self.unit}",
        ]
        if self.fuel_component:
            rows.append(f"{'fuel / feedstock':<{w}}{self.fuel_component:>16,.3f}  {self.unit}")
        if self.byproduct_component:
            rows.append(f"{'byproduct credit':<{w}}{self.byproduct_component:>16,.3f}  {self.unit}")
        rows += ["-" * (w + 22),
                 f"{'LEVELISED COST':<{w}}{self.levelized_cost:>16,.3f}  {self.unit}"]
        for n in self.notes:
            rows.append(f"  ! {n}")
        return "\n".join(rows)


def lcox(capital: float,
         annual_fixed_opex: float,
         annual_variable_opex: float,
         annual_production: float,
         charge_rate: float,
         annual_fuel_cost: float = 0.0,
         annual_byproduct_revenue: float = 0.0,
         unit: str = "$/unit",
         charge_rate_name: str = "FCR") -> LevelizedResult:
    """
    The general levelised cost of anything.

        LCOX = (charge_rate * CAPEX + FOM + VOM + FUEL - byproducts) / production

    Set the denominator and you have named the metric:
        MWh net       -> LCOE   ($/MWh)
        kg H2         -> LCOH   ($/kg)
        tonne CO2     -> LCOC   ($/t)
        tonne product -> LCOA, LCOM, ...

    `charge_rate` is the FCR from :func:`fcr` (tax-aware) or the bare CRF from
    :func:`crf` (pre-tax). Whichever you use, the capital argument must be on
    the matching basis -- TASC for a NETL-style FCR, CAPEX/TOC for an ATB-style
    one -- and the result carries that basis with it.

    Examples
    --------
    LCOH: $400M TASC, $18M/yr fixed, $65M/yr electricity, 30,000 t H2/yr:

    >>> f = fcr(0.0473, 30, 0.2574, 20)
    >>> r = lcox(400e6, 18e6, 65e6, 30_000e3, f, unit="$/kg H2")
    >>> round(r.levelized_cost, 2)
    3.71
    """
    if annual_production <= 0:
        raise ValueError("annual_production must be positive")
    cap = charge_rate * capital
    total = cap + annual_fixed_opex + annual_variable_opex + annual_fuel_cost \
        - annual_byproduct_revenue
    return LevelizedResult(
        levelized_cost=total / annual_production,
        unit=unit,
        capital_component=cap / annual_production,
        fixed_component=annual_fixed_opex / annual_production,
        variable_component=annual_variable_opex / annual_production,
        fuel_component=annual_fuel_cost / annual_production,
        byproduct_component=-annual_byproduct_revenue / annual_production,
        charge_rate=charge_rate,
        charge_rate_name=charge_rate_name,
        annual_production=annual_production,
        capital_basis=capital,
    )


def netl_coe(tasc: float,
             fixed_charge_rate: float,
             annual_fixed_opex: float,
             annual_variable_opex_at_full_load: float,
             capacity_factor: float,
             annual_mwh_at_full_load: float) -> LevelizedResult:
    """
    First-year cost of electricity, NETL Equation 4.

        COE = [ FCR*TASC + OC_fix + CF*OC_var ] / ( CF * MWH )

    where OC_var is at 100% capacity factor (so it scales with CF) and OC_fix
    does not. MWH is the annual net generation at 100% capacity factor.

    Note two NETL conventions:
      * TASC, not TOC. Use :class:`tea.capital.NETLCapitalCost`.
      * The interest rate inside the FCR "must by necessity be the ATWACC".

    Under NETL's assumption of 0% real escalation, the real LCOE equals the
    base-year COE, which is why NETL's revision-4 baselines report them
    interchangeably.

    Examples
    --------
    650 MW net coal plant, 85% CF, TASC $2.4B, FOM $60M/yr, VOM+fuel $110M/yr:

    >>> f = fcr(0.0473, 30, 0.2574, 20)
    >>> mwh = 650 * 8760
    >>> r = netl_coe(2.4e9, f, 60e6, 110e6, 0.85, mwh)
    >>> round(r.levelized_cost, 2)
    66.79
    """
    if not 0 < capacity_factor <= 1:
        raise ValueError("capacity_factor must be in (0, 1]")
    denom = capacity_factor * annual_mwh_at_full_load
    cap = fixed_charge_rate * tasc
    var = capacity_factor * annual_variable_opex_at_full_load
    total = cap + annual_fixed_opex + var
    return LevelizedResult(
        levelized_cost=total / denom,
        unit="$/MWh",
        capital_component=cap / denom,
        fixed_component=annual_fixed_opex / denom,
        variable_component=var / denom,
        charge_rate=fixed_charge_rate,
        charge_rate_name="FCR (NETL)",
        annual_production=denom,
        capital_basis=tasc,
        notes=["NETL Eq. 4; capital basis is TASC, not TOC"],
    )


def atb_lcoe(capex: float,
             fixed_charge_rate: float,
             fom_per_kw_yr: float,
             capacity_factor: float,
             capacity_kw: float,
             vom_per_mwh: float = 0.0,
             fuel_per_mwh: float = 0.0,
             ptc_per_mwh: float = 0.0) -> LevelizedResult:
    """
    LCOE in the NREL Annual Technology Baseline formulation.

        LCOE = (FCR * CAPEX + FOM) / (CF * 8760) + VOM + FUEL - PTC

    with CAPEX and FOM expressed per kW, so the result is $/MWh directly.
    In the ATB, ``FCR = CRF x ProFinFactor`` and
    ``CAPEX = ConFinFactor x (OCC + GCC)`` -- i.e. the ATB folds construction
    financing into CAPEX rather than carrying a separate TASC, which is the
    main structural difference from the NETL formulation.

    Parameters
    ----------
    capex : float
        Total capital, $ (already including construction financing).
    fom_per_kw_yr : float
        Fixed O&M, $/kW-yr.
    capacity_kw : float
        Net plant capacity, kW.

    Examples
    --------
    >>> f = fcr(0.05, 30, 0.26, 5)
    >>> r = atb_lcoe(1.5e9, f, 30.0, 0.55, 500_000, vom_per_mwh=2.0)
    >>> round(r.levelized_cost, 2)
    50.52
    """
    mwh = capacity_factor * 8760.0 * capacity_kw / 1000.0
    cap = fixed_charge_rate * capex
    fom = fom_per_kw_yr * capacity_kw
    lcoe = (cap + fom) / mwh + vom_per_mwh + fuel_per_mwh - ptc_per_mwh
    return LevelizedResult(
        levelized_cost=lcoe,
        unit="$/MWh",
        capital_component=cap / mwh,
        fixed_component=fom / mwh,
        variable_component=vom_per_mwh,
        fuel_component=fuel_per_mwh,
        byproduct_component=-ptc_per_mwh,
        charge_rate=fixed_charge_rate,
        charge_rate_name="FCR (ATB)",
        annual_production=mwh,
        capital_basis=capex,
        notes=["NREL ATB formulation; CAPEX includes construction financing"],
    )


def levelization_factor(rate: float, escalation: float, years: int) -> float:
    """
    Factor converting a first-year O&M cost to a levelised O&M cost when the
    cost escalates at a constant rate (NETL Eq. 12, the part multiplying AOM).

        LF = CRF * [ 1 - ((1+i)/(1+r))^y ] / (r - i)

    With zero real escalation (NETL's assumption) LF = 1 and the levelised
    value equals the annual value. With 3% nominal escalation over 30 years at
    the nominal ATWACC, NETL reports LF = 1.384.

    >>> round(levelization_factor(0.0654, 0.03, 30), 3)
    1.384
    >>> round(levelization_factor(0.0473, 0.0, 30), 3)
    1.0
    """
    c = crf(rate, years)
    if abs(rate - escalation) < 1e-12:
        return c * years / (1.0 + rate) * (1.0 + rate)  # limit case
    return c * (1.0 - ((1.0 + escalation) / (1.0 + rate)) ** years) / (rate - escalation)


def levelized_fuel_price(prices: list[float], rate: float) -> float:
    """
    Levelise a fuel price forecast (NETL Eq. 13 and 14).

        PV   = sum_n  P_n / (1 + r)^n
        LFP  = PV * CRF(r, y)

    Use this instead of a flat escalation rate when you have an actual price
    forecast -- e.g. the EIA Annual Energy Outlook, which is what NETL's
    companion QGESS on fuel prices is built from.

    Parameters
    ----------
    prices : list of float
        Fuel price in each operating year, in the same $ basis as `rate`
        (real prices with a real rate, nominal with nominal).
    """
    if not prices:
        raise ValueError("prices must be non-empty")
    y = len(prices)
    pv = sum(p / (1.0 + rate) ** (n + 1) for n, p in enumerate(prices))
    return pv * crf(rate, y)


def netl_lcoe(levelized_capital: float,
              levelized_om: float,
              levelized_fuel: float) -> float:
    """
    NETL Equation 15:  LCOE = LCC + LOM + LFP.

    All three terms in $/MWh, all real or all nominal.
    """
    return levelized_capital + levelized_om + levelized_fuel
