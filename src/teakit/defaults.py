"""
teakit.defaults — Editable reference defaults: location, utilities, labour, finance.
===================================================================================

Everything in this module is a **starting value, not an answer**. The capital
correlations in :mod:`teakit.equipment` are regressed from a specific published
data set and carry a defensible provenance. The numbers here are different in
kind: utility prices, wage rates and location factors move with the market, the
region and the contract, and no public source is authoritative for *your* plant.

So the contract of this module is:

* every entry carries a ``source`` string and a vintage year;
* every entry is overridable at the call site;
* the library never silently substitutes a default without recording it in the
  result's ``notes``.

If you publish a number that came from here without replacing it with a quote or
a local tariff, say so in your assumptions table.

CONVENTIONS
-----------
Prices are in **U.S. dollars of the stated ``basis_year``**, on a
**U.S. Gulf Coast** basis unless noted. Escalate them with
:func:`teakit.indices.escalate` (capital goods) or with an appropriate
producer-price index (commodities and labour — CEPCI is a *plant cost* index and
is the wrong deflator for electricity or wages; see the note on
:func:`utility_price`).

SOURCES
-------
U.S. EIA, *Electric Power Monthly* Table 5.3 (average retail price of
    electricity to industrial customers) and *Natural Gas Prices* series
    N3035US3 (industrial). https://www.eia.gov/electricity/monthly/ ,
    https://www.eia.gov/dnav/ng/ng_pri_sum_dcu_nus_a.htm
U.S. BLS, *Occupational Employment and Wage Statistics*, SOC 51-8091 Chemical
    Plant and System Operators; 17-2041 Chemical Engineers.
    https://www.bls.gov/oes/current/oes518091.htm
Humbird, D. et al. (2011), NREL/TP-5100-47764, Table 22 (staffing plan and
    salaries) and §5 (fixed operating cost conventions).
    https://www.osti.gov/biblio/1013269
NETL-PUB-22580, Exhibit 3-1 (global economic assumptions), §2.5 (owner's costs).
Turton, R. et al., *Analysis, Synthesis and Design of Chemical Processes*,
    Ch. 8 — the factored operating-cost method and the utility cost correlations
    reproduced in :data:`UTILITY_CATALOGUE` where no government series exists.
Ulrich, G.D. & Vasudevan, P.T. (2006), "How to estimate utility costs",
    *Chemical Engineering* 113(4), 66-69 — utility prices as a function of fuel
    price and CEPCI.
"""

from __future__ import annotations

from . import currency as _currency
from . import indices

__all__ = [
    "LOCATIONS", "location_factor", "location_names",
    "UTILITY_CATALOGUE", "ELECTRICITY_INDUSTRIAL", "NATURAL_GAS_INDUSTRIAL",
    "UNIT_SETS", "utility_measure", "unit_options", "rate_unit",
    "rate_in_natural_units",
    "utility_price", "steam_price_from_fuel", "default_utility_set",
    "LABOR_ROLES", "NREL_STAFFING", "OPERATOR_WAGE", "labor_burden",
    "TAX_PRESETS", "FINANCE_PRESETS", "OPERATING_PRESETS",
    "CURRENCIES", "DEFAULT_EXCHANGE_RATES",
]


# ============================================================================
# 1. Location
# ============================================================================
#: Location factors relative to U.S. Gulf Coast = 1.00, together with an
#: indicative field-labour productivity/wage multiplier.
#:
#: A location factor bundles three separate effects that move independently:
#: equipment freight and duty, field labour wage and productivity, and local
#: regulatory/permitting burden. A single scalar is an approximation; for a
#: Class 3 estimate or better, split them. The values below are the midpoints
#: of published compilations (AACE 28R-03; Compass International; IHS/Aspen
#: location factor tables) and are provided so a run has *something* defensible
#: to start from. **They are indicative to roughly +/-10 points.**
#:
#: Format: name -> dict(factor, labor_factor, currency, note)
LOCATIONS: dict[str, dict] = {
    "USGC": dict(factor=1.00, labor_factor=1.00, currency="USD",
                 note="U.S. Gulf Coast — the basis of the DOE/NETL correlations"),
    "US Midwest": dict(factor=1.06, labor_factor=1.12, currency="USD",
                       note="higher field wage, similar material cost"),
    "US Northeast": dict(factor=1.12, labor_factor=1.25, currency="USD",
                         note="high wage, high permitting burden"),
    "US West Coast": dict(factor=1.18, labor_factor=1.30, currency="USD",
                          note="high wage, seismic design, permitting"),
    "US Mountain": dict(factor=1.05, labor_factor=1.08, currency="USD", note=""),
    "US Southeast": dict(factor=0.98, labor_factor=0.95, currency="USD", note=""),
    "Canada — Alberta": dict(factor=1.15, labor_factor=1.20, currency="CAD",
                             note="module fabrication offsets some field cost"),
    "Canada — Ontario/Quebec": dict(factor=1.10, labor_factor=1.10, currency="CAD",
                                    note=""),
    "Canada — British Columbia": dict(factor=1.18, labor_factor=1.22, currency="CAD",
                                      note="remote-site premiums common"),
    "Mexico — Gulf": dict(factor=1.00, labor_factor=0.55, currency="MXN",
                          note="low field wage, imported equipment at USGC price"),
    "Western Europe": dict(factor=1.20, labor_factor=1.25, currency="EUR", note=""),
    "Middle East": dict(factor=1.07, labor_factor=0.60, currency="USD", note=""),
    "China": dict(factor=0.75, labor_factor=0.40, currency="CNY",
                  note="domestic supply chain; imported equipment does not benefit"),
    "India": dict(factor=0.80, labor_factor=0.30, currency="INR", note=""),
    "Southeast Asia": dict(factor=0.88, labor_factor=0.40, currency="USD", note=""),
    "Australia": dict(factor=1.35, labor_factor=1.45, currency="AUD",
                      note="high wage, remote sites, thin contractor market"),
    "Brazil": dict(factor=1.10, labor_factor=0.60, currency="BRL", note=""),
}

#: ISO codes and symbols for report headers.
#:
#: The cost engine works in USD throughout -- every correlation and index behind
#: it is a US series. A non-USD currency is applied to the *finished* result as
#: a reporting step; see :mod:`teakit.currency` for the rate, its provenance,
#: and why a converted estimate is still a US-basis estimate.
CURRENCIES = _currency.CURRENCIES

#: Offline fallback rates, in target-currency units per USD. Indicative only --
#: see :data:`teakit.currency.DEFAULT_RATES` for the caveat that matters.
DEFAULT_EXCHANGE_RATES = _currency.DEFAULT_RATES


def location_names() -> list[str]:
    """Sorted list of known location keys.

    >>> "USGC" in location_names()
    True
    """
    return sorted(LOCATIONS)


def location_factor(name: str, kind: str = "capital") -> float:
    """
    Look up a location factor.

    Parameters
    ----------
    name : str
        A key of :data:`LOCATIONS`. Case- and whitespace-insensitive.
    kind : {"capital", "labor"}
        ``"capital"`` returns the overall installed-cost multiplier applied to
        equipment and bulks; ``"labor"`` returns the wage/productivity
        multiplier used by :mod:`teakit.opex` for operating labour.

    >>> location_factor("USGC")
    1.0
    >>> location_factor("US West Coast", "labor")
    1.3
    """
    key = _match_location(name)
    rec = LOCATIONS[key]
    if kind == "capital":
        return rec["factor"]
    if kind == "labor":
        return rec["labor_factor"]
    raise ValueError("kind must be 'capital' or 'labor'")


def _match_location(name: str) -> str:
    if name in LOCATIONS:
        return name
    norm = name.strip().lower().replace("-", "").replace("—", "").replace(" ", "")
    for k in LOCATIONS:
        if k.lower().replace("-", "").replace("—", "").replace(" ", "") == norm:
            return k
    raise KeyError(f"Unknown location {name!r}. Options: {', '.join(location_names())}")


# ============================================================================
# 2. Utilities
# ============================================================================
#: U.S. average retail price of electricity to **industrial** customers,
#: cents/kWh, annual average. Source: EIA Electric Power Monthly Table 5.3.
#: 2025 is a partial-year average and is flagged provisional.
ELECTRICITY_INDUSTRIAL: dict[int, float] = {
    2015: 6.91, 2016: 6.76, 2017: 6.88, 2018: 6.92, 2019: 6.81,
    2020: 6.67, 2021: 7.18, 2022: 8.45, 2023: 8.03, 2024: 8.10,
    2025: 8.35,
}

#: U.S. price of natural gas delivered to **industrial** consumers, $/thousand
#: cubic feet, annual. Source: EIA series N3035US3. Divide by ~1.037 to get
#: $/MMBtu at the standard 1,037 Btu/scf heating value.
NATURAL_GAS_INDUSTRIAL: dict[int, float] = {
    2015: 3.91, 2016: 3.51, 2017: 4.06, 2018: 4.19, 2019: 3.86,
    2020: 3.32, 2021: 5.55, 2022: 8.06, 2023: 5.13, 2024: 4.55,
    2025: 5.10,
}

_PROVISIONAL_PRICE_YEARS = {2025}

#: Utility catalogue. Each entry:
#:   unit          the physical unit the rate is quoted in
#:   price         indicative price, USD of `basis_year`, USGC
#:   basis_year    vintage of `price`
#:   source        provenance string, reproduced into results
#:   category      grouping for charts
#:
#: Electricity and natural gas are overwritten from the EIA series above by
#: :func:`utility_price` when a year is supplied. The rest are engineering
#: estimates from the open literature and **should be replaced** with your own
#: tariff or a utility-system model wherever they matter.
UTILITY_CATALOGUE: dict[str, dict] = {
    "electricity": dict(
        unit="kWh", price=0.0810, basis_year=2024, category="utility",
        source="EIA Electric Power Monthly T5.3, U.S. industrial average"),
    "natural gas": dict(
        unit="MMBtu", price=4.39, basis_year=2024, category="utility",
        source="EIA N3035US3 industrial, converted at 1.037 MMBtu/Mcf"),
    "steam, HP (600 psig)": dict(
        unit="tonne", price=22.0, basis_year=2024, category="utility",
        source="Ulrich & Vasudevan (2006) correlation at 2024 fuel price"),
    "steam, MP (150 psig)": dict(
        unit="tonne", price=19.0, basis_year=2024, category="utility",
        source="Ulrich & Vasudevan (2006) correlation at 2024 fuel price"),
    "steam, LP (50 psig)": dict(
        unit="tonne", price=16.0, basis_year=2024, category="utility",
        source="Ulrich & Vasudevan (2006) correlation at 2024 fuel price"),
    "cooling water": dict(
        unit="m3", price=0.055, basis_year=2024, category="utility",
        source="Turton Ch.8 circulating-water cost, escalated; excludes makeup"),
    "process water": dict(
        unit="m3", price=0.85, basis_year=2024, category="utility",
        source="typical U.S. industrial potable/demin blend; replace with tariff"),
    "boiler feedwater": dict(
        unit="m3", price=2.60, basis_year=2024, category="utility",
        source="demineralised + deaerated; Turton Ch.8"),
    "chilled water": dict(
        unit="GJ", price=6.50, basis_year=2024, category="utility",
        source="Ulrich & Vasudevan (2006), 5 degC supply"),
    "refrigeration (-20 C)": dict(
        unit="GJ", price=13.0, basis_year=2024, category="utility",
        source="Ulrich & Vasudevan (2006)"),
    "instrument air": dict(
        unit="1000 Nm3", price=14.0, basis_year=2024, category="utility",
        source="Turton Ch.8, dried and oil-free"),
    "nitrogen": dict(
        unit="1000 Nm3", price=95.0, basis_year=2024, category="utility",
        source="merchant/on-site blend; highly site-specific"),
    "wastewater treatment": dict(
        unit="m3", price=1.60, basis_year=2024, category="waste",
        source="conventional biological treatment; Turton Ch.8"),
    "solid waste disposal, non-hazardous": dict(
        unit="tonne", price=60.0, basis_year=2024, category="waste",
        source="U.S. average landfill tipping fee"),
    "solid waste disposal, hazardous": dict(
        unit="tonne", price=340.0, basis_year=2024, category="waste",
        source="indicative; varies by waste code and distance to facility"),
}


def utility_price(name: str, year: int | None = None,
                  escalate_with: str = "auto") -> tuple[float, str, list[str]]:
    """
    Indicative price of a utility, with provenance and warnings.

    Returns ``(price, unit, notes)``. ``notes`` is never empty — a utility price
    always carries a caveat, and the caller is expected to surface it.

    Parameters
    ----------
    name : str
        A key of :data:`UTILITY_CATALOGUE`.
    year : int, optional
        Dollar-year wanted. For electricity and natural gas the EIA series is
        used directly when the year is present in it. For everything else the
        price is escalated from its ``basis_year``.
    escalate_with : {"auto", "cepci", "none"}
        ``"auto"`` uses CEPCI only for the equipment-like utilities and leaves
        commodity prices alone when a direct series exists. **CEPCI is a plant
        construction index and is a poor deflator for energy or wages** — it is
        used here only as a last resort and always flagged.

    Examples
    --------
    >>> p, unit, notes = utility_price("electricity", 2022)
    >>> round(p, 4), unit
    (0.0845, 'kWh')
    >>> p, unit, _ = utility_price("cooling water")
    >>> unit
    'm3'
    """
    if name not in UTILITY_CATALOGUE:
        raise KeyError(f"Unknown utility {name!r}. "
                       f"Options: {', '.join(sorted(UTILITY_CATALOGUE))}")
    rec = UTILITY_CATALOGUE[name]
    price = rec["price"]
    unit = rec["unit"]
    notes = [f"source: {rec['source']}"]

    if year is None:
        notes.append(f"price is in {rec['basis_year']} USD, USGC basis")
        return price, unit, notes

    if name == "electricity" and year in ELECTRICITY_INDUSTRIAL:
        price = ELECTRICITY_INDUSTRIAL[year] / 100.0
        notes.append(f"EIA industrial average for {year}")
        if year in _PROVISIONAL_PRICE_YEARS:
            notes.append(f"{year} EIA value is a partial-year average (provisional)")
        return price, unit, notes

    if name == "natural gas" and year in NATURAL_GAS_INDUSTRIAL:
        price = NATURAL_GAS_INDUSTRIAL[year] / 1.037
        notes.append(f"EIA industrial delivered price for {year}, "
                     f"converted at 1.037 MMBtu/Mcf")
        if year in _PROVISIONAL_PRICE_YEARS:
            notes.append(f"{year} EIA value is a partial-year average (provisional)")
        return price, unit, notes

    if escalate_with == "none" or year == rec["basis_year"]:
        notes.append(f"price left on its {rec['basis_year']} basis")
        return price, unit, notes

    price = indices.escalate(price, rec["basis_year"], year)
    notes.append(f"escalated {rec['basis_year']}->{year} by CEPCI, which is a "
                 f"PLANT COST index and only a rough proxy for a consumable "
                 f"price — replace with a local tariff if this line matters")
    return price, unit, notes


def steam_price_from_fuel(fuel_price_per_mmbtu: float,
                          pressure_psig: float = 150.0,
                          boiler_efficiency: float = 0.80,
                          feedwater_and_treatment: float = 2.50) -> float:
    """
    Steam price from a fuel price, rather than from the table.

    This is usually the right way to do it: on a plant that buys gas and makes
    its own steam, the steam price is *derived*, and taking it from a table
    while separately taking the gas price from EIA double-counts the market.

        $/tonne steam = (dH / eta) * fuel$ / 1e6 * 1.0551  +  water & treatment

    with the latent+sensible duty ``dH`` in Btu/lb taken from steam-table values
    at the stated pressure, from saturated feedwater at 100 degC.

    Parameters
    ----------
    fuel_price_per_mmbtu : float
        Delivered fuel price, $/MMBtu (higher heating value basis).
    pressure_psig : float
        Steam header pressure. Interpolated over 15-900 psig.
    boiler_efficiency : float
        HHV basis. 0.80 is a reasonable package-boiler default; a modern
        economised industrial boiler reaches 0.85.
    feedwater_and_treatment : float
        $/tonne for makeup, demineralisation, chemicals and blowdown.

    >>> round(steam_price_from_fuel(4.39, 150), 2)
    13.45

    Note this comes out below the tabulated MP steam price, because the table
    entry carries distribution, condensate return and a share of boiler-house
    fixed cost that this fuel-only calculation does not.
    """
    # Enthalpy rise, Btu/lb, from 100 degC feedwater to saturated steam.
    table = {15: 970, 50: 950, 150: 905, 300: 865, 600: 800, 900: 745}
    ps = sorted(table)
    if pressure_psig <= ps[0]:
        dh = table[ps[0]]
    elif pressure_psig >= ps[-1]:
        dh = table[ps[-1]]
    else:
        for lo, hi in zip(ps, ps[1:]):
            if lo <= pressure_psig <= hi:
                f = (pressure_psig - lo) / (hi - lo)
                dh = table[lo] + f * (table[hi] - table[lo])
                break
    btu_per_tonne = dh * 2204.62 / boiler_efficiency
    return btu_per_tonne / 1e6 * fuel_price_per_mmbtu + feedwater_and_treatment


def default_utility_set(year: int | None = None) -> list[dict]:
    """
    A blank utility sheet: every catalogued utility at zero consumption.

    Handy as the starting state of a UI — the user fills in rates, and the
    prices are already populated and sourced.

    >>> rows = default_utility_set(2024)
    >>> rows[0]["name"], rows[0]["rate"]
    ('electricity', 0.0)
    """
    out = []
    for name, rec in UTILITY_CATALOGUE.items():
        price, unit, notes = utility_price(name, year)
        out.append(dict(name=name, rate=0.0, unit=unit, price=price,
                        category=rec["category"], source=rec["source"],
                        notes=notes))
    return out


# ============================================================================
# 3. Labour
# ============================================================================
#: Indicative U.S. annual base salaries, 2024 USD, **excluding** burden.
#: Source: BLS OEWS national means for the matching SOC code, rounded.
#: Multiply by a location labour factor and add burden — see :func:`labor_burden`.
LABOR_ROLES: dict[str, dict] = {
    "plant manager": dict(salary=185_000, soc="11-3051", shift=False),
    "plant engineer": dict(salary=125_000, soc="17-2041", shift=False),
    "process engineer": dict(salary=115_000, soc="17-2041", shift=False),
    "maintenance supervisor": dict(salary=105_000, soc="49-1011", shift=False),
    "maintenance technician": dict(salary=72_000, soc="49-9041", shift=False),
    "lab manager": dict(salary=98_000, soc="19-4031", shift=False),
    "lab technician": dict(salary=62_000, soc="19-4031", shift=False),
    "shift supervisor": dict(salary=88_000, soc="51-1011", shift=True),
    "shift operator": dict(salary=78_000, soc="51-8091", shift=True),
    "yard employee": dict(salary=52_000, soc="53-7062", shift=True),
    "clerk / secretary": dict(salary=54_000, soc="43-6014", shift=False),
    "EHS specialist": dict(salary=92_000, soc="19-5011", shift=False),
}

#: Mean annual wage, U.S. chemical plant and system operators (BLS SOC 51-8091),
#: 2024. The single most useful number for a first-pass labour estimate.
OPERATOR_WAGE = 78_000.0

#: Shift coverage multiplier for a continuously-manned position. Covering one
#: seat 24/7/365 takes 8,760 h; one employee delivers roughly 1,900 productive
#: hours after holiday, vacation, sickness and training, giving ~4.6. Industry
#: practice rounds to 4.5-5.0. Turton uses 4.5; NREL's staffing plans imply ~4.8.
SHIFT_COVERAGE = 4.8

#: NREL-style staffing template (NREL/TP-5100-47764 Table 22), expressed as
#: counts for a ~2,000 tonne/day biorefinery. Use :func:`scale_staffing` to move
#: it to another plant size — staffing scales far more weakly than capacity.
NREL_STAFFING: dict[str, int] = {
    "plant manager": 1,
    "plant engineer": 1,
    "maintenance supervisor": 1,
    "lab manager": 1,
    "shift supervisor": 5,
    "lab technician": 2,
    "maintenance technician": 8,
    "shift operator": 20,
    "yard employee": 4,
    "clerk / secretary": 3,
}


def labor_burden(base_salary: float, burden_frac: float = 0.35) -> float:
    """
    Fully-loaded cost of an employee.

    Burden covers the employer's payroll taxes, insurance, pension and paid
    leave. 30-40% of base salary is the usual U.S. industrial range; NREL's
    biorefinery reports apply 90% of salary as "labour burden" but that figure
    also carries plant overhead, so do not double-count it against
    :attr:`teakit.opex.OperatingCost.overhead_frac_labor`.

    >>> labor_burden(78_000)
    105300.0
    """
    return base_salary * (1.0 + burden_frac)


def scale_staffing(reference_staff: dict[str, int],
                   size_ratio: float,
                   exponent: float = 0.25) -> dict[str, int]:
    """
    Move a staffing plan to a different plant size.

    Headcount scales very weakly with capacity — a plant twice the size does not
    need twice the operators, because the number of *unit operations* barely
    changes. An exponent of 0.2-0.3 on capacity is the usual observation.
    Non-shift management positions are held at their reference count.

    >>> s = scale_staffing({"shift operator": 20, "plant manager": 1}, 2.0)
    >>> s["shift operator"], s["plant manager"]
    (24, 1)
    """
    out: dict[str, int] = {}
    for role, n in reference_staff.items():
        rec = LABOR_ROLES.get(role, {})
        if rec.get("shift") or n > 2:
            out[role] = max(1, round(n * size_ratio ** exponent))
        else:
            out[role] = n
    return out


# ============================================================================
# 4. Finance, tax and operating presets
# ============================================================================
#: Combined effective income tax rates. Verify before use — these change.
TAX_PRESETS: dict[str, dict] = {
    "NETL (US, 21% fed + state)": dict(
        rate=0.2574, source="NETL-PUB-22580 Exhibit 3-1"),
    "US federal only": dict(rate=0.21, source="IRC §11, post-TCJA"),
    "NREL nth-plant (2011 vintage)": dict(
        rate=0.35, source="NREL/TP-5100-47764 — pre-TCJA, historical only"),
    "Canada — combined federal + provincial (typical)": dict(
        rate=0.265, source="15% federal + ~11.5% provincial general rate"),
    "no tax (pre-tax screening)": dict(rate=0.0, source="screening only"),
}

#: Complete financing/timing presets. Selecting one of these sets every finance
#: field at once against a published basis, which is what you want when
#: benchmarking a result against a published study.
FINANCE_PRESETS: dict[str, dict] = {
    "NREL nth-plant": dict(
        discount_rate=0.10, tax_rate=0.21, depreciation_years=7,
        plant_life_years=30, construction_years=3, debt_frac=0.0,
        startup_revenue_frac=0.50, working_capital_frac=0.05,
        basis="real",
        source="NREL/TP-5100-47764 nth-plant convention, tax rate updated "
               "to the post-2017 federal rate"),
    "NETL investor-owned utility (real)": dict(
        discount_rate=0.0473, tax_rate=0.2574, depreciation_years=20,
        plant_life_years=30, construction_years=3, debt_frac=0.0,
        startup_revenue_frac=1.00, working_capital_frac=0.0,
        basis="real",
        source="NETL-PUB-22580 Exhibit 3-2, real ATWACC 4.73%"),
    "NETL investor-owned utility (nominal)": dict(
        discount_rate=0.0654, tax_rate=0.2574, depreciation_years=20,
        plant_life_years=30, construction_years=3, debt_frac=0.0,
        startup_revenue_frac=1.00, working_capital_frac=0.0,
        basis="nominal",
        source="NETL-PUB-22580 Exhibit 3-2, nominal ATWACC 6.54%"),
    "Merchant chemical project (levered)": dict(
        discount_rate=0.12, tax_rate=0.25, depreciation_years=7,
        plant_life_years=25, construction_years=2, debt_frac=0.60,
        debt_interest_rate=0.075, debt_term_years=12,
        startup_revenue_frac=0.60, working_capital_frac=0.10,
        basis="nominal",
        source="indicative private-equity/project-finance structure — not a "
               "published basis, adjust to your term sheet"),
    "Public / concessional finance": dict(
        discount_rate=0.05, tax_rate=0.0, depreciation_years=20,
        plant_life_years=40, construction_years=4, debt_frac=0.0,
        startup_revenue_frac=0.75, working_capital_frac=0.05,
        basis="real",
        source="social discount rate; OMB Circular A-94 style appraisal"),
}

# ============================================================================
# 2b. Units
# ============================================================================
#: Quantity units teakit offers for a utility, by what is being measured.
#:
#: A :class:`teakit.opex.Stream` always holds a *quantity* unit and prices per
#: that unit; ``basis`` then says whether the rate is that quantity per
#: operating hour or per year. So the sets below are quantity units, not rates:
#: electricity is metered and priced in kWh, and "kWh per operating hour" is
#: what a reader calls kW.
#:
#: ``per_hour`` is that restatement, and it is what the interface *shows* on an
#: hourly line: the unit control offers kW and MW, not kWh and MWh, because a
#: compressor draws 5,200 kW and nobody writes its duty any other way. The
#: stored unit stays kWh, because that is what the price is per and what the
#: annual quantity comes out in — hours x kW = kWh. One convention in the
#: model, the engineer's convention on the screen.
#:
#: :func:`rate_in_natural_units` does the same restatement for a whole rate.
#:
#: The first entry in each list is the conventional default.
UNIT_SETS: dict[str, dict] = {
    "electricity": {
        "label": "Electrical energy",
        "units": ["kWh", "MWh", "GWh", "Wh"],
        #: quantity unit -> the rate unit it becomes when read per hour
        "per_hour": {"Wh": "W", "kWh": "kW", "MWh": "MW", "GWh": "GW"},
    },
    "fuel": {
        "label": "Fuel or heat",
        "units": ["MMBtu", "GJ", "MJ", "therm", "kWh", "MWh"],
        "per_hour": {"MMBtu": "MMBtu/h", "GJ": "GJ/h", "MJ": "MJ/h",
                     "therm": "therm/h", "kWh": "kW", "MWh": "MW"},
    },
    "mass": {
        "label": "Mass",
        "units": ["tonne", "kg", "lb", "ton (US)"],
        "per_hour": {"tonne": "tonne/h", "kg": "kg/h", "lb": "lb/h",
                     "ton (US)": "ton/h"},
    },
    "volume": {
        "label": "Volume",
        "units": ["m3", "L", "gal", "1000 gal", "ft3"],
        # Every entry here restates the *same number* in per-hour form, so a
        # conversion factor has no business in it: 100 gal per operating hour
        # is 100 gal/h, and calling it "100 gpm" would be wrong by sixty.
        "per_hour": {"m3": "m3/h", "L": "L/h", "gal": "gal/h",
                     "1000 gal": "1000 gal/h", "ft3": "ft3/h"},
    },
    "gas_volume": {
        "label": "Gas volume, normalised",
        "units": ["1000 Nm3", "Nm3", "1000 scf", "scf"],
        "per_hour": {"Nm3": "Nm3/h", "1000 Nm3": "1000 Nm3/h",
                     "scf": "scfh", "1000 scf": "1000 scf/h"},
    },
    "other": {
        "label": "Other",
        "units": [],
        "per_hour": {},
    },
}

#: Which unit set a catalogued utility belongs to. Anything absent is matched
#: on its unit by :func:`utility_measure`, and falls back to "other".
UTILITY_MEASURES: dict[str, str] = {
    "electricity": "electricity",
    "natural gas": "fuel",
    "steam, HP (600 psig)": "mass",
    "steam, MP (150 psig)": "mass",
    "steam, LP (50 psig)": "mass",
    "cooling water": "volume",
    "process water": "volume",
    "boiler feedwater": "volume",
    "chilled water": "fuel",
    "refrigeration (-20 C)": "fuel",
    "instrument air": "gas_volume",
    "nitrogen": "gas_volume",
    "wastewater treatment": "volume",
    "solid waste disposal, non-hazardous": "mass",
    "solid waste disposal, hazardous": "mass",
}

#: Reverse lookup: a unit -> the set it belongs to. Built once, so a utility
#: teakit has never seen is still classified by the unit it is quoted in.
_UNIT_TO_MEASURE = {u: k for k, v in UNIT_SETS.items() for u in v["units"]}


def utility_measure(name: str = "", unit: str = "") -> str:
    """
    Which unit set a utility belongs to, by name and then by unit.

    >>> utility_measure("electricity")
    'electricity'
    >>> utility_measure("some new coolant", "m3")
    'volume'
    >>> utility_measure("mystery")
    'other'
    """
    key = str(name or "").strip().lower()
    for k, v in UTILITY_MEASURES.items():
        if k.lower() == key:
            return v
    if unit and unit in _UNIT_TO_MEASURE:
        return _UNIT_TO_MEASURE[unit]
    return "other"


def unit_options(name: str = "", unit: str = "") -> list[str]:
    """
    The units teakit offers for this utility, with anything already in use
    kept at the front so a project never loses a unit it was written with.

    >>> unit_options("electricity")[:2]
    ['kWh', 'MWh']
    """
    opts = list(UNIT_SETS[utility_measure(name, unit)]["units"])
    if unit and unit not in opts:
        opts.insert(0, unit)
    return opts


def rate_unit(unit: str, basis: str = "hour", name: str = "") -> str:
    """
    The unit a rate is *read* in, as against the unit it is priced in.

    A stream holds a quantity unit because that is what the price is per.
    Per operating hour, that quantity is a draw and has a name of its own:
    kWh per hour is kW. Per year it is already an annual total and the
    quantity unit is the right label.

    >>> rate_unit("kWh", "hour")
    'kW'
    >>> rate_unit("kWh", "year")
    'kWh'
    >>> rate_unit("m3", "hour")
    'm3/h'
    >>> rate_unit("widgets", "hour")
    'widgets/h'
    """
    if not unit:
        return ""
    if basis != "hour":
        return unit
    natural = UNIT_SETS[utility_measure(name, unit)]["per_hour"].get(unit)
    return natural or f"{unit}/h"


def rate_in_natural_units(rate: float, unit: str, basis: str = "hour",
                          name: str = "") -> str:
    """
    A rate written the way an engineer would say it aloud.

    A stream of 5,200 kWh per operating hour is 5,200 kW; teakit stores the
    former because the price is per kWh, and shows the latter because that is
    what the number is.

    >>> rate_in_natural_units(5200, "kWh", "hour")
    '5,200 kW'
    >>> rate_in_natural_units(5200, "kWh", "year")
    '5,200 kWh/yr'
    """
    if basis != "hour":
        return f"{rate:,.4g} {unit}/yr" if unit else f"{rate:,.4g}/yr"
    natural = UNIT_SETS[utility_measure(name, unit)]["per_hour"].get(unit)
    if natural:
        return f"{rate:,.4g} {natural}"
    return f"{rate:,.4g} {unit}/h" if unit else f"{rate:,.4g}/h"


#: Operating-time presets. ``capacity_factor`` is output relative to nameplate;
#: ``stream_factor`` (a.k.a. on-stream factor) is the fraction of the year the
#: plant runs. They are not the same thing and both belong in an assumptions
#: table.
OPERATING_PRESETS: dict[str, dict] = {
    "Continuous, 8,000 h/yr (91.3%)": dict(
        operating_hours=8000.0, capacity_factor=1.00,
        source="the conventional chemical-industry default"),
    "Continuous, 8,406 h/yr (96%)": dict(
        operating_hours=8406.0, capacity_factor=1.00,
        source="NREL biorefinery on-stream factor, 0.96"),
    "Continuous, 7,446 h/yr (85%)": dict(
        operating_hours=7446.0, capacity_factor=1.00,
        source="NETL baseline power plant capacity factor, 85%"),
    "Two-shift, 4,000 h/yr": dict(
        operating_hours=4000.0, capacity_factor=1.00, source="batch/campaign plant"),
    "Single-shift, 2,000 h/yr": dict(
        operating_hours=2000.0, capacity_factor=1.00, source="speciality/batch"),
}


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
