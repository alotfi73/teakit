"""
teakit — Techno-economic analysis of chemical process plants.
=============================================================

A documented, dependency-free Python toolkit for costing process plants, built
on public U.S. government methodology: DOE/NETL for capital, NREL for
discounted cash flow, and the Chemical Engineering Plant Cost Index for
escalation. Every correlation and every formula carries its citation in the
docstring of the function that uses it.

    import teakit as tea

QUICK START
-----------
The whole pipeline, in one object::

    import teakit as tea

    p = tea.Project(name="Methanol plant", dollar_year=2025, location="USGC")

    p.equipment = [
        tea.EquipmentItem("R-101", kind="reactor_jacketed", size=3_000),
        tea.EquipmentItem("E-101", kind="hx_shell_tube", size=8_000, material="ss316"),
        tea.EquipmentItem("K-101", kind="compressor_centrifugal_150psia", size=12_000),
        tea.EquipmentItem("P-101", kind="pump", size=900, quantity=2, spare=1),
    ]
    p.opex.raw_materials = [tea.Stream("natural gas", 45.0, "MMBtu", 4.39)]
    p.opex.utilities     = [tea.Stream("electricity", 6_000, "kWh", 0.081,
                                       category="utility")]
    p.opex.labor         = tea.LaborModel(operators_per_shift=5)
    p.products.products  = [tea.Product("methanol", 330_000, "tonne")]
    p.apply_finance_preset("NREL nth-plant")

    r = p.run()
    print(r.report())
    print(f"{r.unit_cost:,.2f} {p.currency}/{r.unit}")

Or use the pieces on their own, which is what you want when checking one
number::

    tea.purchased_cost("hx_shell_tube", 5_000, year=2025).report()
    tea.fcr(0.0473, 30, 0.2574, 20)
    tea.escalate(1_000_000, 1998, 2025)

And the graphical application, for people who do not write Python::

    $ teakit app

MODULE MAP
----------
========================  ====================================================
:mod:`teakit.indices`     CEPCI, RSMeans, escalation between dollar-years
:mod:`teakit.equipment`   power-law scaling, materials, columns, packing
:mod:`teakit.capital`     purchased -> installed -> BEC -> EPCC -> TPC -> TOC -> TASC
:mod:`teakit.opex`        labour, utilities, feedstock, factored fixed costs
:mod:`teakit.products`    product slate, byproduct credits, allocation
:mod:`teakit.levelized`   CRF, FCR, NETL COE, ATB LCOE, generic LCOX
:mod:`teakit.dcf`         after-tax cash flow, NPV, IRR, MSP at NPV = 0
:mod:`teakit.plant_sections`  account-level NETL scaling exponents
:mod:`teakit.project`     the whole pipeline in one serialisable object
:mod:`teakit.sensitivity` tornado, sweep, two-way grid, Monte Carlo, breakeven
:mod:`teakit.charts`      chart specs, SVG renderer, optional matplotlib bridge
:mod:`teakit.report`      text, Markdown, standalone HTML, CSV
:mod:`teakit.defaults`    editable location, utility, labour and finance data
:mod:`teakit.datasets`    the bundled reference CSVs
========================  ====================================================

WHAT THIS IS NOT
----------------
It is not a flowsheet simulator: it will not close a mass or energy balance, and
the consumption rates you feed :class:`~teakit.opex.Stream` have to come from
somewhere else. It is not a substitute for a vendor quote on the equipment that
defines your process. And a correlation-based capital estimate escalated from a
1998 data set is AACE Class 5-4 — good for screening and comparison, not for
sanctioning a project. See the README for the full limitations list, which
belongs in any report built on this.
"""

from __future__ import annotations

__version__ = "2.0.0"
__author__ = "A. Lotfollahzade Moghaddam"
__license__ = "PolyForm-Noncommercial-1.0.0"
__url__ = "https://github.com/alotfi73/teakit"

# --- indices ---------------------------------------------------------------
from .indices import (
    CEPCI_ANNUAL, CEPCI_MONTHLY, CEPCI_PROVISIONAL, CEPCI_SUBINDEX_2024_06,
    RSMEANS_QUARTERLY,
    cepci, is_provisional, escalate, escalate_by_index, index_ratio, inflate,
    real_to_nominal, nominal_to_real,
    CEPCI_USER, set_user_cepci, user_cepci, available_years, has_cepci,
)

# --- equipment -------------------------------------------------------------
from .equipment_data import EQUIPMENT, ALIASES, resolve
from .equipment_data import COLUMNS, PACKING_COST, ADSORBENT_COST
from .equipment import (
    SIX_TENTHS, MATERIAL_FACTORS, HX_MATERIAL_FACTORS, LITERATURE_EXPONENTS,
    LOCATION_FACTORS_NOTE, material_factor,
    scale_cost, purchased_cost, n_units_scaling, equipment_list_cost,
    column_cost, packing_cost, adsorbent_cost,
    Equipment, CostResult, catalogue, describe, exponent_table,
)

# --- capital ---------------------------------------------------------------
from .capital import (
    AACE_CLASSES, PROCESS_CONTINGENCY_AACE, LANG_FACTORS,
    LOH_DISTRIBUTIVE_FACTORS, LOH_SETTING_FACTORS,
    NETL_TASC_TOC, NETL_SPEND_PROFILE,
    lang_factor_capital, installed_cost_loh, tasc_over_toc,
    NETLCapitalCost, CapitalResult,
)

# --- operating cost --------------------------------------------------------
from .opex import (
    Stream, LaborItem, LaborModel, LaborResult, OperatingCost, OpexResult,
    NREL_FIXED, PT_FIXED, NETL_FIXED, FIXED_CONVENTIONS,
    turton_com, operators_turton,
)

# --- products --------------------------------------------------------------
from .products import Product, ProductSlate, AllocationResult, ALLOCATION_METHODS

# --- levelised costs -------------------------------------------------------
from .levelized import (
    NETL_GLOBAL_ASSUMPTIONS, NETL_FINANCE_IOU, NETL_REFERENCE, MACRS,
    wacc, atwacc, wacc_atb, crf, fcr, pv_depreciation, macrs_schedule,
    simple_levelized_cost, simple_payback, simple_roi, annualized_capital,
    capital_charge_method,
    lcox, netl_coe, atb_lcoe, levelization_factor, levelized_fuel_price,
    netl_lcoe, LevelizedResult,
)

# --- plant-section (account-level) scaling ---------------------------------
from .plant_sections import (
    CATEGORIES, ACCOUNTS, TECHNOLOGY_CATEGORIES,
    scale_account, scale_case, accounts_for, account_table,
    derive_exponent, contingency_percent, AccountResult,
)

# --- discounted cash flow --------------------------------------------------
from .dcf import npv, irr, CashFlowModel, DCFResult, NREL_NTH_PLANT

# --- project orchestration -------------------------------------------------
from .project import (
    Project, ProjectResult, EquipmentItem, CapitalConfig, FinanceConfig,
    COSTING_METHODS,
)

# --- sensitivity -----------------------------------------------------------
from .sensitivity import (
    SensitivityParam, tornado, sweep, two_way, monte_carlo, breakeven,
    suggest_params, METRICS, DEFAULT_RANGES,
)

# --- charts, reports, defaults, data ---------------------------------------
from .charts import ChartSpec, default_charts, PALETTE
from . import charts, report, defaults, datasets, currency
from .defaults import (
    LOCATIONS, UTILITY_CATALOGUE, LABOR_ROLES, FINANCE_PRESETS, TAX_PRESETS,
    OPERATING_PRESETS, location_factor, utility_price, steam_price_from_fuel,
)
from .currency import CURRENCIES, RateQuote, RateTable, fetch_rates, cached_rates


#: The licence in one sentence, for the application to print. LICENSE is
#: what binds; an SPDX identifier on its own tells a user nothing.
LICENSE_NOTE = ("free for any noncommercial purpose, including academic research "
                "and teaching — you may use it, change it and pass it on. Commercial "
                "use needs a separate licence from the author. See LICENSE.")


#: How to cite teakit: ``software`` for the toolkit, ``paper`` for the study
#: it was written for. The interface and the reports render from here, and
#: CITATION.cff repeats it in the form GitHub reads.
CITATION = {
    "software": {
        "authors": __author__,
        "title": "teakit: techno-economic analysis of chemical process plants",
        "version": __version__,
        "year": 2026,
        "url": __url__,
    },
    "paper": {
        "authors": ("A. Lotfollahzade Moghaddam, S. Hejazi, M. Fattahi, "
                    "M. Kibria, M. A. Khan"),
        "title": ("Molten metal methane pyrolysis for distributed hydrogen "
                  "production: Reactor design, hydrodynamics, and "
                  "technoeconomic insights"),
        "journal": "Chemical Engineering Journal",
        "year": 2025,
        "doi": "10.1016/j.cej.2025.169812",
        "url": "https://doi.org/10.1016/j.cej.2025.169812",
    },
}


def citation(kind: str = "paper") -> str:
    """
    One line of reference text, ``kind`` being ``"paper"`` or ``"software"``.

    >>> citation("paper").startswith("A. Lotfollahzade Moghaddam")
    True
    >>> "10.1016/j.cej.2025.169812" in citation("paper")
    True
    >>> citation("software").startswith("A. Lotfollahzade Moghaddam. teakit:")
    True
    """
    try:
        c = CITATION[kind]
    except KeyError:
        raise ValueError(
            f"kind must be one of {list(CITATION)}, not {kind!r}") from None
    if kind == "software":
        return (f"{c['authors']}. {c['title']}, version {c['version']}, "
                f"{c['year']}. {c['url']}")
    return (f"{c['authors']}. {c['title']}. {c['journal']}, "
            f"{c['year']}. https://doi.org/{c['doi']}")


def demo(kind: str = "methanol") -> "Project":
    """
    A fully populated example project, for exploring the API without typing an
    equipment list first.

    >>> p = demo()
    >>> r = p.run()
    >>> r.unit_cost > 0
    True
    """
    from .examples import build_demo
    return build_demo(kind)


__all__ = [n for n in dir() if not n.startswith("_")]
