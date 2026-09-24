"""
tea.dcf — Discounted cash flow, NPV, IRR and the NPV = 0 selling price.
=======================================================================

This is the rigorous end of the toolkit: a year-by-year after-tax cash flow
over the construction period, start-up and full operating life, solved for the
product price that drives NPV to zero.

WHY NPV = 0
-----------
"Minimum selling price" is defined as the product price at which the project
exactly earns its required rate of return and no more. Formally: the price for
which the net present value of all after-tax cash flows, discounted at the
required IRR, is zero. Every US national-lab TEA is built this way:

    NREL: "a discounted cash flow rate of return (DCFROR) analysis to determine
    a plant gate price ... The plant gate price is also called the minimum fuel
    selling price (MFSP), required to obtain a net present value (NPV) of zero
    for a 10% internal rate of return (IRR) after taxes, associated with an
    nth-plant model."

    DOE/NREL H2A: "The models use a standard discounted cash flow rate of
    return analysis methodology to determine the hydrogen selling cost for the
    desired internal rate of return."

This differs from the formula methods in :mod:`tea.levelized` in ways that
matter: it carries the real depreciation schedule year by year, handles debt
amortisation separately from equity return, respects a start-up year at partial
capacity, and can carry tax losses forward. NETL is explicit that when
technologies go to market "a detailed cash flow estimate is needed for owners
to determine their resource choices".

WHAT "nth-PLANT" MEANS
----------------------
NREL's design reports state their economics are *nth-plant*: the assumption
that several plants using the same technology have already been built and are
operating, so there are no first-of-a-kind risk premiums, no pioneer-plant cost
growth and no learning penalty. A pioneer plant is materially more expensive --
the RAND studies of the 1980s (Merrow et al.) found systematic cost growth and
performance shortfalls in first-of-a-kind process plants. If you are costing a
first commercial unit, an nth-plant MSP is a floor, not an estimate.

SOURCES
-------
NREL/TP-5100-47764 (Humbird et al., 2011), "Process Design and Economics for
    Biochemical Conversion of Lignocellulosic Biomass to Ethanol" -- the
    canonical DCFROR / MESP reference. https://www.osti.gov/biblio/1013269
NREL H2A / H2A-Lite production models. https://www.nrel.gov/hydrogen/h2a-lite.html
NETL-PUB-22580 §3, for the finance structure and tax assumptions.
IRS Publication 946, for MACRS depreciation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .levelized import crf, macrs_schedule, atwacc

__all__ = [
    "npv", "irr", "CashFlowModel", "DCFResult", "NREL_NTH_PLANT",
]


# ============================================================================
# Bare NPV / IRR
# ============================================================================
def npv(rate: float, cash_flows: list[float], t0: int = 0) -> float:
    """
    Net present value.  NPV = sum_t  CF_t / (1 + rate)^(t + t0)

    Convention here: ``cash_flows[0]`` occurs at time ``t0`` (default 0, i.e.
    undiscounted). Costs negative, income positive.

    >>> round(npv(0.10, [-1000, 400, 400, 400]), 2)
    -5.26
    """
    return sum(cf / (1.0 + rate) ** (t + t0) for t, cf in enumerate(cash_flows))


def irr(cash_flows: list[float], guess_lo: float = -0.99, guess_hi: float = 10.0,
        tol: float = 1e-10, max_iter: int = 300) -> float | None:
    """
    Internal rate of return: the discount rate at which NPV = 0.

    Solved by bisection on a bracket. Returns None if no sign change exists in
    the bracket (e.g. an all-positive or all-negative cash flow), and note that
    cash flows changing sign more than once can have multiple IRRs -- this
    returns the one in the bracket.

    >>> round(irr([-1000, 400, 400, 400]), 5)
    0.09701
    """
    f_lo = npv(guess_lo, cash_flows)
    f_hi = npv(guess_hi, cash_flows)
    if f_lo * f_hi > 0:
        return None
    lo, hi = guess_lo, guess_hi
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid, cash_flows)
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


# ============================================================================
# Reference assumption sets
# ============================================================================
#: NREL "nth-plant" financial assumptions as used across the biorefinery design
#: reports (Humbird et al. 2011 and successors). Reproduced here so a run can
#: be labelled against a published basis; check the specific report you are
#: benchmarking, since the tax rate in particular changed after 2017.
NREL_NTH_PLANT = {
    "internal_rate_of_return": 0.10,
    "equity_frac": 0.40,
    "debt_frac": 0.60,
    "debt_interest_rate": 0.08,
    "debt_term_years": 10,
    "plant_life_years": 30,
    "construction_years": 3,
    "construction_profile": [0.08, 0.60, 0.32],
    "startup_months": 6,
    "startup_revenue_frac": 0.50,
    "startup_variable_cost_frac": 0.75,
    "startup_fixed_cost_frac": 1.00,
    "depreciation": "MACRS 7-year (general plant); 20-year for steam/power",
    "on_stream_factor": 0.90,
    "working_capital_frac_of_fci": 0.05,
    "note": (
        "nth-plant basis: no first-of-a-kind risk premium, pioneer-plant cost "
        "growth or learning penalty. Income tax rate varies by report vintage "
        "(35% federal pre-2018, 21% after) -- set it explicitly."
    ),
}


# ============================================================================
# Full cash flow model
# ============================================================================
@dataclass
class DCFResult:
    """Year-by-year output of :meth:`CashFlowModel.run`."""
    price: float
    npv: float
    irr: float | None
    years: list[int]
    periods: list[int]
    capex: list[float]
    revenue: list[float]
    opex: list[float]
    depreciation: list[float]
    interest: list[float]
    principal: list[float]
    taxable_income: list[float]
    tax: list[float]
    net_cash_flow: list[float]
    discounted_cash_flow: list[float]
    cumulative_dcf: list[float]
    discount_rate: float
    total_capital: float
    payback_year: float | None = None
    notes: list[str] = field(default_factory=list)

    def table(self, max_rows: int = 40) -> str:
        """Pretty year-by-year table."""
        hdr = (f"{'yr':>4}{'capex':>14}{'revenue':>14}{'opex':>14}"
               f"{'deprec':>13}{'interest':>13}{'tax':>13}"
               f"{'net CF':>15}{'cum. DCF':>16}")
        rows = [hdr, "-" * len(hdr)]
        n = len(self.years)
        show = range(n) if n <= max_rows else list(range(max_rows - 5)) + list(range(n - 5, n))
        prev = None
        for i in show:
            if prev is not None and i != prev + 1:
                rows.append(f"{'...':>4}")
            rows.append(
                f"{self.years[i]:>4}{-self.capex[i]:>14,.0f}{self.revenue[i]:>14,.0f}"
                f"{-self.opex[i]:>14,.0f}{self.depreciation[i]:>13,.0f}"
                f"{-self.interest[i]:>13,.0f}{-self.tax[i]:>13,.0f}"
                f"{self.net_cash_flow[i]:>15,.0f}{self.cumulative_dcf[i]:>16,.0f}")
            prev = i
        rows += [
            "-" * len(hdr),
            f"discount rate {self.discount_rate:.4%}   "
            f"NPV {self.npv:,.0f}   "
            f"IRR {self.irr:.4%}" if self.irr is not None else
            f"discount rate {self.discount_rate:.4%}   NPV {self.npv:,.0f}",
        ]
        if self.payback_year is not None:
            rows.append(f"discounted payback: year {self.payback_year:.1f}")
        return "\n".join(rows)


@dataclass
class CashFlowModel:
    """
    After-tax discounted cash flow for a process plant.

    Timeline
    --------
        year -C ... -1   construction, capital spent per `construction_profile`
        year  0          (no year zero: construction ends, operation begins)
        year  1          start-up year, at reduced revenue and raised unit cost
        year  2 ... N    full operation
        year  N          working capital and salvage recovered

    All monetary inputs must be on ONE basis: either all real (constant
    dollars, with a real discount rate) or all nominal (with a nominal rate and
    explicit escalation). Mixing them is the most common error in TEA.

    Parameters
    ----------
    total_capital : float
        Fixed capital investment, in base-year dollars. Depreciable.
    annual_production : float
        Output per operating year at full rate, in whatever unit the price is
        quoted in (kg H2, MWh, tonne, gal).
    annual_fixed_opex, annual_variable_opex : float
        Fixed and variable operating costs at full rate.
    discount_rate : float
        Required after-tax return. This is the rate at which NPV is set to
        zero when solving for the minimum selling price. NREL nth-plant uses
        10%; NETL uses an ATWACC (~4.7% real / 6.5% nominal).
    tax_rate : float
        Combined effective income tax rate. NETL: 0.2574 (21% federal + 6%
        state). Check the vintage of any study you are benchmarking against.
    depreciation_years : int
        MACRS GDS recovery period. NREL biorefinery reports use 7-year for
        general plant; NETL uses 20-year 150% DB.
    debt_frac, debt_interest_rate, debt_term_years
        Set ``debt_frac = 0`` for an all-equity / WACC-discounted run, which is
        the cleaner formulation when `discount_rate` is already a WACC. Only
        model debt explicitly if `discount_rate` is a cost of *equity*.

    Examples
    --------
    >>> m = CashFlowModel(total_capital=400e6, annual_production=30e6,
    ...                   annual_fixed_opex=18e6, annual_variable_opex=65e6,
    ...                   discount_rate=0.10, plant_life_years=30)
    >>> msp = m.minimum_selling_price()
    >>> round(msp, 3)
    4.679
    >>> round(m.run(msp).irr, 4)     # by construction, IRR == discount rate
    0.1
    """
    total_capital: float
    annual_production: float
    annual_fixed_opex: float = 0.0
    annual_variable_opex: float = 0.0

    # --- timing ------------------------------------------------------------
    plant_life_years: int = 30
    construction_years: int = 3
    construction_profile: list[float] | None = None
    startup_revenue_frac: float = 0.50
    startup_variable_cost_frac: float = 0.75
    startup_fixed_cost_frac: float = 1.00

    # --- finance and tax ---------------------------------------------------
    discount_rate: float = 0.10
    tax_rate: float = 0.2574
    depreciation_years: int = 7
    depreciation_schedule: list[float] | None = None
    debt_frac: float = 0.0
    debt_interest_rate: float = 0.08
    debt_term_years: int = 10

    # --- other cash items --------------------------------------------------
    working_capital: float = 0.0
    land_cost: float = 0.0                 # non-depreciable, recovered at end
    salvage_value: float = 0.0
    annual_byproduct_revenue: float = 0.0
    #: Real escalation of O&M and revenue. Leave at 0 for a constant-dollar run.
    opex_escalation: float = 0.0
    revenue_escalation: float = 0.0
    #: Carry tax losses forward instead of booking a negative tax (a credit).
    carry_losses_forward: bool = True

    # ------------------------------------------------------------------
    def _profile(self) -> list[float]:
        if self.construction_profile:
            p = list(self.construction_profile)
            if abs(sum(p) - 1.0) > 1e-9:
                raise ValueError("construction_profile must sum to 1.0")
            return p
        c = self.construction_years
        if c == 1:
            return [1.0]
        if c == 2:
            return [0.40, 0.60]
        if c == 3:
            return [0.08, 0.60, 0.32]          # NREL nth-plant profile
        if c == 5:
            return [0.10, 0.30, 0.25, 0.20, 0.15]   # NETL 5-year profile
        return [1.0 / c] * c

    def _depreciation(self) -> list[float]:
        if self.depreciation_schedule is not None:
            return list(self.depreciation_schedule)
        return macrs_schedule(self.depreciation_years)

    # ------------------------------------------------------------------
    def run(self, price: float) -> DCFResult:
        """Build the full cash flow at a given product price."""
        prof = self._profile()
        c = len(prof)
        dep_sched = self._depreciation()
        life = self.plant_life_years

        years, periods, capex, revenue, opex = [], [], [], [], []
        deprec, interest, principal = [], [], []
        taxable, tax, ncf = [], [], []

        # --- debt amortisation (level payment) ---
        debt = self.total_capital * self.debt_frac
        if debt > 0:
            pay = debt * crf(self.debt_interest_rate, self.debt_term_years)
        else:
            pay = 0.0
        balance = debt

        # --- construction years: -c .. -1 ---
        for k, frac in enumerate(prof):
            yr = -c + k
            spend = self.total_capital * frac
            equity_spend = spend * (1.0 - self.debt_frac)
            years.append(yr)
            periods.append(k)          # t = 0 at the first construction year
            capex.append(equity_spend)
            revenue.append(0.0); opex.append(0.0); deprec.append(0.0)
            interest.append(0.0); principal.append(0.0)
            taxable.append(0.0); tax.append(0.0)
            ncf.append(-equity_spend)

        # working capital + land at the start of operation (year 0 outflow,
        # placed at the last construction year so it is spent before revenue)
        wc_land = self.working_capital + self.land_cost
        if wc_land:
            capex[-1] += wc_land
            ncf[-1] -= wc_land

        # --- operating years: 1 .. life ---
        loss_carryforward = 0.0
        for y in range(1, life + 1):
            startup = (y == 1)
            esc_r = (1.0 + self.revenue_escalation) ** (y - 1)
            esc_o = (1.0 + self.opex_escalation) ** (y - 1)

            # Start-up year: output is reduced, but unit costs are worse, so
            # variable cost falls by less than revenue does (NREL convention:
            # 50% revenue, 75% variable cost, 100% fixed cost).
            rev_frac = self.startup_revenue_frac if startup else 1.0
            prod = self.annual_production * rev_frac
            rev = (prod * price + self.annual_byproduct_revenue * rev_frac) * esc_r

            vom_frac = self.startup_variable_cost_frac if startup else 1.0
            fom_frac = self.startup_fixed_cost_frac if startup else 1.0
            op = (self.annual_variable_opex * vom_frac
                  + self.annual_fixed_opex * fom_frac) * esc_o

            d = (dep_sched[y - 1] * self.total_capital) if y - 1 < len(dep_sched) else 0.0

            if balance > 1e-9 and y <= self.debt_term_years:
                intr = balance * self.debt_interest_rate
                prin = min(pay - intr, balance)
                balance -= prin
            else:
                intr = prin = 0.0

            ti = rev - op - d - intr
            if self.carry_losses_forward:
                ti_after = ti - loss_carryforward
                if ti_after < 0:
                    loss_carryforward = -ti_after
                    t = 0.0
                else:
                    loss_carryforward = 0.0
                    t = ti_after * self.tax_rate
            else:
                t = ti * self.tax_rate

            cf = rev - op - intr - prin - t

            if y == life:
                cf += wc_land + self.salvage_value * (1.0 - self.tax_rate)

            # Operation follows straight on from construction: the first
            # operating year is t = c, with no phantom "year zero" gap.
            years.append(y); periods.append(c + y - 1)
            capex.append(0.0); revenue.append(rev); opex.append(op)
            deprec.append(d); interest.append(intr); principal.append(prin)
            taxable.append(ti); tax.append(t); ncf.append(cf)

        # --- discount ---
        # t = 0 at the first year of capital expenditure. Construction occupies
        # t = 0 .. c-1; the first operating year is t = c. There is deliberately
        # no year 0 in the `years` labels (the calendar jumps -1 -> 1), which is
        # the usual TEA convention, so `periods` carries the real exponent.
        dcf = [cf / (1.0 + self.discount_rate) ** t for t, cf in zip(periods, ncf)]
        cum, running = [], 0.0
        for v in dcf:
            running += v
            cum.append(running)

        payback = None
        for i in range(1, len(cum)):
            if cum[i - 1] < 0 <= cum[i]:
                span = cum[i] - cum[i - 1]
                payback = years[i - 1] + (0 - cum[i - 1]) / span if span else years[i]
                break

        return DCFResult(
            price=price, npv=sum(dcf), irr=irr(ncf),
            years=years, periods=periods, capex=capex, revenue=revenue, opex=opex,
            depreciation=deprec, interest=interest, principal=principal,
            taxable_income=taxable, tax=tax,
            net_cash_flow=ncf, discounted_cash_flow=dcf, cumulative_dcf=cum,
            discount_rate=self.discount_rate,
            total_capital=self.total_capital,
            payback_year=payback,
        )

    # ------------------------------------------------------------------
    def npv_at(self, price: float) -> float:
        """NPV at a given product price."""
        return self.run(price).npv

    def minimum_selling_price(self, tol: float = 1e-9,
                              max_iter: int = 200) -> float:
        """
        Solve for the product price giving NPV = 0 -- the MSP / MFSP / MESP,
        or equivalently the levelised cost of the product.

        The NPV is very nearly linear in price (exactly linear absent a loss
        carry-forward), so a secant step converges immediately; a bisection
        fallback handles the carry-forward kink.

        Returns
        -------
        float
            Price in $ per unit of `annual_production`.

        Examples
        --------
        >>> m = CashFlowModel(total_capital=400e6, annual_production=30e6,
        ...                   annual_fixed_opex=18e6, annual_variable_opex=65e6,
        ...                   discount_rate=0.10, plant_life_years=30)
        >>> round(m.minimum_selling_price(), 3)
        4.679
        """
        p0, p1 = 0.0, 1.0
        f0, f1 = self.npv_at(p0), self.npv_at(p1)
        if abs(f1 - f0) < 1e-30:
            raise RuntimeError("NPV does not respond to price; check annual_production")
        # secant / linear extrapolation
        p = p0 - f0 * (p1 - p0) / (f1 - f0)
        for _ in range(max_iter):
            f = self.npv_at(p)
            if abs(f) <= tol * max(1.0, abs(self.total_capital)):
                return p
            fp = self.npv_at(p * 1.0000001 + 1e-9)
            slope = (fp - f) / (p * 1e-7 + 1e-9)
            if slope == 0:
                break
            step = f / slope
            p -= step
            if abs(step) < 1e-12:
                return p
        return p

    def sensitivity(self, parameter: str,
                    multipliers: list[float] | None = None) -> list[tuple[float, float]]:
        """
        One-at-a-time sensitivity of the MSP to a model parameter.

        Returns [(multiplier, MSP), ...]. A tornado chart of these is the single
        most informative figure in a TEA -- it tells the reader which
        assumptions the answer actually depends on.

        Examples
        --------
        >>> m = CashFlowModel(total_capital=400e6, annual_production=30e6,
        ...                   annual_variable_opex=65e6, discount_rate=0.10)
        >>> s = m.sensitivity("total_capital", [0.8, 1.0, 1.2])
        >>> len(s)
        3
        """
        multipliers = multipliers or [0.7, 0.85, 1.0, 1.15, 1.3]
        base = getattr(self, parameter)
        if not isinstance(base, (int, float)):
            raise TypeError(f"{parameter} is not numeric")
        out = []
        try:
            for m in multipliers:
                setattr(self, parameter, base * m)
                out.append((m, self.minimum_selling_price()))
        finally:
            setattr(self, parameter, base)
        return out
