"""
tea.capital — From purchased equipment cost to total capital investment.
========================================================================

Purchased equipment is typically only 15-30% of what a plant actually costs.
This module implements three ways of getting from there to a capital number,
in increasing order of rigour:

1. :func:`lang_factor_capital`   -- one multiplier, order-of-magnitude
2. :func:`installed_cost_loh`    -- DOE/NETL distributive factors, per item
3. :class:`NETLCapitalCost`      -- the full BEC -> EPCC -> TPC -> TOC -> TASC
                                    cascade used in every NETL baseline study

THE NETL CAPITAL COST LADDER
----------------------------
Verbatim from NETL-PUB-22580 §2.1 (see SOURCES):

BEC   Bare Erected Cost. Process equipment, on-site facilities and
      infrastructure that support the plant (shops, offices, labs, roads), and
      the direct and indirect labour required for construction/installation.

EPCC  Engineering, Procurement and Construction Cost = BEC + EPC contractor
      services (detailed design, contractor permitting, project/construction
      management). NETL uses 15-20% of BEC.

TPC   Total Plant Cost = EPCC + process contingency + project contingency.

TOC   Total Overnight Cost = TPC + all other "overnight" costs, including
      owner's costs. An overnight cost: no escalation, no construction
      financing.

TASC  Total As-Spent Capital = sum of all capital expenditures as incurred
      across the capital expenditure period, *including* escalation and
      interest during construction (interest on debt plus return on equity).
      Expressed in mixed, current-year dollars.

BEC, EPCC, TPC and TOC are overnight costs in base-year dollars. TASC is not.
This distinction is the single most common source of confusion when comparing
published capital numbers: always ask "TOC or TASC?".

WHY IT MATTERS FOR THE LEVELISED COST
-------------------------------------
The NETL COE formula multiplies **TASC** (not TOC) by the fixed charge rate.
If you multiply an FCR by a TOC you will understate the capital charge by the
TASC/TOC factor -- 9% for a 3-year build in real terms, 15% for a 5-year build,
and 24-29% in nominal terms. See :func:`tasc_over_toc`.

SOURCES
-------
NETL (2021), "Quality Guidelines for Energy System Studies: Cost Estimation
    Methodology for NETL Assessments of Power Plant Performance", NETL-PUB-22580.
    https://www.netl.doe.gov/projects/files/QGESSCostEstMethodforNETLAssessmentsofPowerPlantPerformance_022621.pdf
    -- capital cost levels (§2.1), contingencies (§2.4), owner's costs (§2.5),
       global economic assumptions (Exhibit 3-1), TASC/TOC (§3.4.2, Eq. 5-7).

Loh, H.P., Lyons, J., White, C.W. III (2002), "Process Equipment Cost
    Estimation, Final Report", DOE/NETL-2002/1169, Tables 2-7 and Appendix A.
    https://www.osti.gov/servlets/purl/797810

AACE International RP 16R-90, "Conducting Technical and Economic Evaluations --
    As Applied for the Process and Utility Industries" (contingency and owner's
    cost guidance that NETL follows).
AACE International RP 18R-97, "Cost Estimate Classification System ... for the
    Process Industries" (the Class 1-5 framework).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AACE_CLASSES", "PROCESS_CONTINGENCY_AACE", "LANG_FACTORS",
    "LOH_DISTRIBUTIVE_FACTORS", "LOH_SETTING_FACTORS",
    "lang_factor_capital", "installed_cost_loh",
    "tasc_over_toc", "NETLCapitalCost", "CapitalResult",
]


# ============================================================================
# Estimate classification (AACE RP 18R-97, as summarised by NETL)
# ============================================================================
#: class -> (project definition % of full scope, typical use, expected accuracy)
AACE_CLASSES: dict[int, tuple[str, str, str]] = {
    5: ("0-2%",   "Concept screening",       "-25% to +50% (NETL uses this for IGCC)"),
    4: ("1-15%",  "Feasibility study",       "-15% to +30% (most NETL studies)"),
    3: ("10-40%", "Budget authorisation",    "-10% to +20%"),
    2: ("30-70%", "Control / bid",           "-5% to +15%"),
    1: ("50-100%","Check estimate / bid",    "-3% to +10%"),
}

#: Process contingency as % of the associated process capital, by technology
#: maturity. Source: AACE 16R-90, reproduced in NETL-PUB-22580 Exhibit 2-3.
PROCESS_CONTINGENCY_AACE: dict[str, tuple[float, float]] = {
    "new concept with limited data":     (0.40, 0.60),   # "40+"
    "concept with bench-scale data":     (0.30, 0.70),
    "small pilot plant data":            (0.20, 0.35),
    "full-sized modules operated":       (0.05, 0.20),
    "commercial":                        (0.00, 0.10),
}

#: Project contingency for a budget-type (AACE Class 4/5) estimate is 15-30%
#: of (BEC + EPC fee + process contingency). Source: AACE 16R-90 via NETL.
PROJECT_CONTINGENCY_RANGE = (0.15, 0.30)

#: EPC/EPCM contractor services, as a fraction of BEC. Source: NETL §2.3.
EPC_FEE_RANGE = (0.15, 0.20)


# ============================================================================
# 1. Lang factor — order-of-magnitude only
# ============================================================================
#: Lang factors: fixed capital investment as a multiple of *delivered*
#: equipment cost. Original values from Lang, H.J. (1948), "Simplified
#: Approach to Preliminary Cost Estimates", Chem. Eng. 55(6), 112-113.
#:
#: These are blunt instruments -- a single number standing in for piping,
#: instruments, electrical, civil, steel, insulation, buildings, engineering
#: and contingency all at once. Expect +/-30-50%. Use them for a first pass
#: and to sanity-check a factored estimate, not for a decision.
LANG_FACTORS: dict[str, float] = {
    "solid processing":       3.10,
    "solid-fluid processing": 3.63,
    "fluid processing":       4.74,
}


def lang_factor_capital(purchased_equipment_cost: float,
                        plant_type: str = "fluid processing",
                        delivery_factor: float = 1.10,
                        working_capital_frac: float = 0.15) -> dict[str, float]:
    """
    Order-of-magnitude capital from a single Lang factor.

    Parameters
    ----------
    purchased_equipment_cost : float
        Sum of FOB purchased costs (what tea.equipment gives you).
    plant_type : str
        Key into LANG_FACTORS.
    delivery_factor : float
        FOB -> delivered. ~1.10 is customary (freight, insurance, duty).
    working_capital_frac : float
        Working capital as a fraction of fixed capital. 10-20% is typical;
        note that NETL sets working capital to zero and instead carries
        inventory capital explicitly as an owner's cost.

    Returns
    -------
    dict with purchased, delivered, fixed_capital, working_capital, total_capital.

    Examples
    --------
    >>> r = lang_factor_capital(10_000_000)
    >>> round(r["fixed_capital"], -5)
    52100000.0
    """
    if plant_type not in LANG_FACTORS:
        raise KeyError(f"plant_type must be one of {list(LANG_FACTORS)}")
    delivered = purchased_equipment_cost * delivery_factor
    fci = delivered * LANG_FACTORS[plant_type]
    wc = fci * working_capital_frac
    return {
        "purchased": purchased_equipment_cost,
        "delivered": delivered,
        "lang_factor": LANG_FACTORS[plant_type],
        "fixed_capital": fci,
        "working_capital": wc,
        "total_capital": fci + wc,
    }


# ============================================================================
# 2. Loh distributive factors — item-by-item installed cost
# ============================================================================
#: Bulk material and labour factors, by process type and service conditions.
#: Source: DOE/NETL-2002/1169, Tables 2-5 (after AACE RP 16R-90).
#:
#: Read as: material % is applied to the BARE EQUIPMENT cost; labour % is then
#: applied to that MATERIAL cost. This two-step application is exactly how the
#: worked example in Loh Appendix A does it.
LOH_DISTRIBUTIVE_FACTORS: dict[str, dict[str, tuple[float, float]]] = {
    # ---- Table 4: liquid and slurry systems --------------------------------
    "liquid_slurry_lt150psig": {
        "foundations": (0.05, 1.33), "structural steel": (0.04, 0.50),
        "buildings": (0.03, 1.00),   "insulation": (0.01, 1.50),
        "instruments": (0.06, 0.40), "electrical": (0.08, 0.75),
        "piping": (0.30, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.04, 0.80),
    },
    "liquid_slurry_gt150psig": {
        "foundations": (0.06, 1.33), "structural steel": (0.05, 0.50),
        "buildings": (0.03, 1.00),   "insulation": (0.03, 1.50),
        "instruments": (0.07, 0.40), "electrical": (0.09, 0.75),
        "piping": (0.35, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.05, 0.80),
    },
    # ---- Table 5: gas processes --------------------------------------------
    "gas_lt400F_lt150psig": {
        "foundations": (0.05, 1.33), "structural steel": (0.05, 0.50),
        "buildings": (0.03, 1.00),   "insulation": (0.01, 1.50),
        "instruments": (0.06, 0.40), "electrical": (0.08, 0.75),
        "piping": (0.45, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.03, 0.80),
    },
    "gas_lt400F_gt150psig": {
        "foundations": (0.06, 1.33), "structural steel": (0.05, 0.50),
        "buildings": (0.03, 1.00),   "insulation": (0.01, 1.50),
        "instruments": (0.07, 0.40), "electrical": (0.09, 0.75),
        "piping": (0.40, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.04, 0.80),
    },
    "gas_gt400F_lt150psig": {
        "foundations": (0.06, 1.33), "structural steel": (0.05, 0.50),
        "buildings": (0.03, 1.00),   "insulation": (0.02, 1.50),
        "instruments": (0.07, 0.75), "electrical": (0.06, 0.40),
        "piping": (0.40, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.04, 0.80),
    },
    "gas_gt400F_gt150psig": {
        "foundations": (0.05, 1.33), "structural steel": (0.06, 0.50),
        "buildings": (0.04, 1.00),   "insulation": (0.03, 1.50),
        "instruments": (0.07, 0.40), "electrical": (0.09, 0.75),
        "piping": (0.40, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.05, 0.80),
    },
    # ---- Table 2: solids handling ------------------------------------------
    "solids_lt400F": {
        "foundations": (0.04, 1.33), "structural steel": (0.04, 0.50),
        "buildings": (0.02, 1.00),   "insulation": (0.00, 0.00),
        "instruments": (0.06, 0.10), "electrical": (0.09, 0.75),
        "piping": (0.05, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.03, 0.80),
    },
    "solids_gt400F": {
        "foundations": (0.05, 1.33), "structural steel": (0.02, 1.00),
        "buildings": (0.02, 1.00),   "insulation": (0.015, 1.50),
        "instruments": (0.06, 0.40), "electrical": (0.09, 0.75),
        "piping": (0.05, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.04, 0.80),
    },
    # ---- Table 3: solids-gas processes -------------------------------------
    "solids_gas_lt400F_lt150psig": {
        "foundations": (0.05, 1.33), "structural steel": (0.04, 1.00),
        "buildings": (0.02, 1.00),   "insulation": (0.01, 1.50),
        "instruments": (0.02, 0.40), "electrical": (0.06, 0.75),
        "piping": (0.35, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.035, 0.80),
    },
    "solids_gas_gt400F_gt150psig": {
        "foundations": (0.06, 1.33), "structural steel": (0.06, 0.50),
        "buildings": (0.04, 1.00),   "insulation": (0.02, 1.50),
        "instruments": (0.08, 0.75), "electrical": (0.08, 0.75),
        "piping": (0.40, 0.50),      "painting": (0.005, 3.00),
        "miscellaneous": (0.045, 0.80),
    },
}

#: Labour for setting equipment, as % of delivered equipment cost.
#: Source: DOE/NETL-2002/1169, Table 6.
#: Note Loh's own caution: "the factors do not work well for very large pieces
#: of equipment. If available, historical work hours provide more accurate costs."
LOH_SETTING_FACTORS: dict[str, float] = {
    "absorber": 0.20, "ammonia still": 0.20, "ball mill": 0.30,
    "briquetting machine": 0.25, "centrifuge": 0.20, "clarifier": 0.15,
    "coke cutter": 0.15, "coke drum": 0.15, "condenser": 0.20,
    "conditioner": 0.20, "cooler": 0.20, "crusher": 0.30, "cyclone": 0.20,
    "decanter": 0.15, "distillation column": 0.30, "evaporator": 0.20,
    "filter": 0.15, "fractionator": 0.25, "furnace": 0.30, "gasifier": 0.30,
    "hammermill": 0.25, "heater": 0.20, "heat exchanger": 0.20,
    "lime leg": 0.15, "methanator": 0.30, "mixer": 0.20,
    "precipitator": 0.25, "regenerator": 0.20, "retort": 0.30,
    "rotoclone": 0.25, "screen": 0.20, "scrubber": 0.15, "settler": 0.15,
    "shift converter": 0.25, "splitter": 0.15, "storage tank": 0.20,
    "stripper": 0.20, "tank": 0.20, "vaporizer": 0.20,
}


def installed_cost_loh(bare_equipment_cost: float,
                       service: str = "liquid_slurry_lt150psig",
                       setting_factor: float | str = 0.20) -> dict[str, float]:
    """
    Installed cost of ONE item by the DOE/NETL distributive-factor method.

    total installed = bare equipment
                    + setting labour
                    + sum over bulks of (material + labour on that material)

    Parameters
    ----------
    bare_equipment_cost : float
        Purchased (FOB) cost of the item.
    service : str
        Key into LOH_DISTRIBUTIVE_FACTORS -- pick by process type, temperature
        and pressure.
    setting_factor : float or str
        Fraction of equipment cost for handling/placing labour, or a key into
        LOH_SETTING_FACTORS.

    Returns
    -------
    dict with a line for each bulk, plus 'setting_labor', 'total_material',
    'total_labor', 'installed_cost' and 'installation_factor'.

    Examples
    --------
    Reproduces the worked example in Loh Appendix A: a 5,000 ft2 gas-gas
    shell-and-tube exchanger, 650 F, 150 psig, bare cost $62,000.

    >>> r = installed_cost_loh(62_000, "gas_gt400F_lt150psig", "heat exchanger")
    >>> round(r["installed_cost"])
    150245
    """
    if service not in LOH_DISTRIBUTIVE_FACTORS:
        raise KeyError(f"service must be one of {list(LOH_DISTRIBUTIVE_FACTORS)}")
    if isinstance(setting_factor, str):
        k = setting_factor.strip().lower()
        if k not in LOH_SETTING_FACTORS:
            raise KeyError(f"Unknown equipment type {setting_factor!r} for setting "
                           f"factor. Options: {', '.join(sorted(LOH_SETTING_FACTORS))}")
        setting_factor = LOH_SETTING_FACTORS[k]

    out: dict[str, float] = {"bare_equipment": bare_equipment_cost}
    setting = bare_equipment_cost * setting_factor
    out["setting_labor"] = setting

    tot_mat = 0.0
    tot_lab = setting
    for bulk, (f_mat, f_lab) in LOH_DISTRIBUTIVE_FACTORS[service].items():
        mat = bare_equipment_cost * f_mat
        lab = mat * f_lab
        out[f"{bulk}_material"] = mat
        out[f"{bulk}_labor"] = lab
        tot_mat += mat
        tot_lab += lab

    out["total_material"] = tot_mat
    out["total_labor"] = tot_lab
    out["installed_cost"] = bare_equipment_cost + tot_mat + tot_lab
    out["installation_factor"] = out["installed_cost"] / bare_equipment_cost
    return out


# ============================================================================
# 3. NETL capital cost cascade
# ============================================================================
def tasc_over_toc(wacc: float,
                  escalation: float,
                  spend_profile: list[float],
                  escalation_offset: int = 0) -> dict[str, float]:
    """
    TASC/TOC factor from first principles (NETL-PUB-22580 Eq. 5, 6 and 7).

        TASC/TOC   = Escalation + Cost of Funding

        Escalation      = sum_n (1+i)^(n-1+offset) * %Capital_n
        Cost of Funding = sum_n WACC * (y-n+1) * (1+i)^(n-1+offset) * %Capital_n

    The Cost of Funding term is simple (not compounded) interest accruing on
    the running balance of escalated spend: money committed in year n sits in
    the project for (y-n+1) years before the plant goes online.

    Parameters
    ----------
    wacc : float
        Pre-tax weighted average cost of capital, nominal or real to match
        `escalation`. NETL uses the PRE-TAX WACC here (not ATWACC) because no
        revenue is being earned during construction.
    escalation : float
        Capital cost escalation during the expenditure period. NETL assumes
        0% real / 3% nominal.
    spend_profile : list of float
        Fraction of TOC spent in each year, first year first, summing to 1.
        NETL defaults: 3-year [0.10, 0.60, 0.30]; 5-year [0.10, 0.30, 0.25,
        0.20, 0.15].
    escalation_offset : int
        Extra years of escalation applied before the first spend year.

        This exists because NETL fixes a single base year (2018 in the
        revision-4 baselines) for BOTH the 5-year coal build and the 3-year
        gas build, so that the two are directly comparable. The gas plant
        spends in the LAST three of those five years, so its first spend year
        already carries two years of escalation: Exhibit 3-8 shows escalated
        costs of 0.10609 = 0.10 x 1.03^2, 0.65564 = 0.60 x 1.03^3 and
        0.33765 = 0.30 x 1.03^4. Hence ``escalation_offset=2`` reproduces the
        published 1.242, whereas offset 0 gives 1.171.

        Use 0 if your base year is the first year of capital expenditure --
        which is the more natural convention for a standalone study. Real
        cases (escalation = 0) are unaffected either way.

    Returns
    -------
    dict with 'escalation', 'cost_of_funding', 'tasc_over_toc'.

    Examples
    --------
    NETL Exhibit 3-7/3-8: three-year nominal case, WACC 7.25%, escalation 3%,
    base year two years ahead of first spend.

    >>> r = tasc_over_toc(0.0725, 0.03, [0.10, 0.60, 0.30], escalation_offset=2)
    >>> round(r["tasc_over_toc"], 3)
    1.242
    >>> round(r["escalation"], 5), round(r["cost_of_funding"], 5)
    (1.09938, 0.14262)

    Exhibit 3-9, five-year nominal (base year = first spend year, offset 0):

    >>> round(tasc_over_toc(0.0725, 0.03, [0.10,0.30,0.25,0.20,0.15])["tasc_over_toc"], 3)
    1.289

    Five-year real case, WACC 5.14%, escalation 0%:

    >>> round(tasc_over_toc(0.0514, 0.0, [0.10,0.30,0.25,0.20,0.15])["tasc_over_toc"], 3)
    1.154
    """
    if abs(sum(spend_profile) - 1.0) > 1e-9:
        raise ValueError(f"spend_profile must sum to 1.0, got {sum(spend_profile)}")
    y = len(spend_profile)
    esc = 0.0
    cof = 0.0
    for idx, frac in enumerate(spend_profile):
        n = idx + 1
        infl = (1.0 + escalation) ** (n - 1 + escalation_offset)
        esc += infl * frac
        cof += wacc * (y - n + 1) * infl * frac
    return {"escalation": esc, "cost_of_funding": cof, "tasc_over_toc": esc + cof}


#: NETL reference TASC/TOC factors (Exhibit 3-7), for a BBB+ or better company
#: under the Exhibit 3-1 / 3-2 assumptions.
NETL_TASC_TOC = {
    (3, "nominal"): 1.242,
    (5, "nominal"): 1.289,
    (3, "real"):    1.093,
    (5, "real"):    1.154,
}

#: NETL default capital expenditure profiles (Exhibit 3-1).
NETL_SPEND_PROFILE = {
    3: [0.10, 0.60, 0.30],                 # natural gas plants
    5: [0.10, 0.30, 0.25, 0.20, 0.15],     # coal plants
}


@dataclass
class CapitalResult:
    """Output of :meth:`NETLCapitalCost.evaluate`."""
    bec: float
    epc_fee: float
    epcc: float
    process_contingency: float
    project_contingency: float
    tpc: float
    owners_costs: dict[str, float]
    total_owners_cost: float
    toc: float
    tasc_toc_factor: float
    tasc: float

    def report(self) -> str:
        w = 40
        rows = [
            "NETL CAPITAL COST CASCADE",
            "=" * 58,
            f"{'Bare Erected Cost (BEC)':<{w}}{self.bec:>18,.0f}",
            f"{'  + EPC contractor services':<{w}}{self.epc_fee:>18,.0f}",
            f"{'= EPC Cost (EPCC)':<{w}}{self.epcc:>18,.0f}",
            f"{'  + process contingency':<{w}}{self.process_contingency:>18,.0f}",
            f"{'  + project contingency':<{w}}{self.project_contingency:>18,.0f}",
            f"{'= Total Plant Cost (TPC)':<{w}}{self.tpc:>18,.0f}",
        ]
        for k, v in self.owners_costs.items():
            rows.append(f"{'  + ' + k:<{w}}{v:>18,.0f}")
        rows += [
            f"{'= Total Overnight Cost (TOC)':<{w}}{self.toc:>18,.0f}",
            f"{'  x TASC/TOC factor':<{w}}{self.tasc_toc_factor:>18.4f}",
            f"{'= Total As-Spent Capital (TASC)':<{w}}{self.tasc:>18,.0f}",
            "",
            "TOC is an overnight cost in base-year dollars.",
            "TASC is mixed current-year dollars over the build period and is",
            "the quantity that the NETL COE/LCOE formula multiplies by the FCR.",
        ]
        return "\n".join(rows)


@dataclass
class NETLCapitalCost:
    """
    Build TASC from BEC following NETL-PUB-22580.

    Every default below is the NETL default, cited in the field comment.
    Override any of them, but record that you did.

    Examples
    --------
    BEC 500 -> EPCC 587.5 (17.5% fee) -> TPC 705.0 (20% project contingency).

    >>> m = NETLCapitalCost(bec=500e6, construction_years=3, basis="real")
    >>> r = m.evaluate()
    >>> round(r.tpc / 1e6, 1)
    705.0
    >>> round(r.tasc_toc_factor, 3)
    1.093
    """
    bec: float

    # --- EPC and contingencies ---------------------------------------------
    #: EPCM contractor services, 15-20% of BEC (NETL §2.3).
    epc_fee_frac: float = 0.175
    #: Process contingency as a fraction of BEC. Set from PROCESS_CONTINGENCY_AACE
    #: according to technology maturity; 0 for fully commercial technology.
    process_contingency_frac: float = 0.0
    #: Project contingency, 15-30% of (BEC + EPC fee + process contingency)
    #: for a budget-type estimate (AACE 16R-90).
    project_contingency_frac: float = 0.20

    # --- Owner's costs, as fractions of TPC unless noted (NETL Exhibit 2-4) --
    #: Pre-production / start-up: NETL's 2% of TPC component. The labour,
    #: maintenance-material, consumables, waste and fuel components are
    #: plant-specific -- add them via `extra_owners_costs`.
    preproduction_frac_tpc: float = 0.02
    #: Inventory capital: 0.5% of TPC for spare parts (plus 60-day supplies of
    #: fuel and non-fuel consumables, which you add explicitly).
    spare_parts_frac_tpc: float = 0.005
    #: Financing cost (securing finance, fees, closing costs; NOT interest
    #: during construction): 2.7% of TPC.
    financing_frac_tpc: float = 0.027
    #: Other owner's costs (feasibility/FEED, economic development, off-site
    #: roads, legal, permitting, owner's engineering, owner's contingency):
    #: 15% of TPC.
    other_owners_frac_tpc: float = 0.15
    #: Land. NETL uses $3,000/acre rural: 300 acres for IGCC/PC, 100 for NGCC.
    land_cost: float = 0.0
    #: Anything plant-specific: 60-day fuel and consumable inventory, start-up
    #: operating labour, first fill of catalyst/solvent, spare rotors, etc.
    extra_owners_costs: dict[str, float] = field(default_factory=dict)

    # --- Construction financing --------------------------------------------
    construction_years: int = 3
    basis: str = "real"                 # "real" or "nominal"
    #: Pre-tax WACC. NETL: 7.25% nominal / 5.14% real (Exhibit 3-2).
    wacc_pretax: float | None = None
    #: Capital escalation during construction. NETL: 0% real / 3% nominal.
    capital_escalation: float | None = None
    spend_profile: list[float] | None = None
    #: See tasc_over_toc(). Only matters for nominal runs.
    escalation_offset: int = 0

    def evaluate(self) -> CapitalResult:
        epc_fee = self.bec * self.epc_fee_frac
        epcc = self.bec + epc_fee
        proc_cont = self.bec * self.process_contingency_frac
        # AACE base for project contingency: BEC + EPC fee + process contingency
        proj_cont = (self.bec + epc_fee + proc_cont) * self.project_contingency_frac
        tpc = epcc + proc_cont + proj_cont

        owners: dict[str, float] = {
            "pre-production (start-up)": tpc * self.preproduction_frac_tpc,
            "inventory capital (spares)": tpc * self.spare_parts_frac_tpc,
            "financing cost": tpc * self.financing_frac_tpc,
            "other owner's costs": tpc * self.other_owners_frac_tpc,
        }
        if self.land_cost:
            owners["land"] = self.land_cost
        owners.update(self.extra_owners_costs)
        total_owners = sum(owners.values())
        toc = tpc + total_owners

        if self.basis not in ("real", "nominal"):
            raise ValueError("basis must be 'real' or 'nominal'")
        wacc = self.wacc_pretax
        esc = self.capital_escalation
        if wacc is None:
            wacc = 0.0514 if self.basis == "real" else 0.0725
        if esc is None:
            esc = 0.0 if self.basis == "real" else 0.03
        profile = self.spend_profile or NETL_SPEND_PROFILE.get(self.construction_years)
        if profile is None:
            profile = [1.0 / self.construction_years] * self.construction_years
        factor = tasc_over_toc(wacc, esc, profile,
                               self.escalation_offset)["tasc_over_toc"]

        return CapitalResult(
            bec=self.bec, epc_fee=epc_fee, epcc=epcc,
            process_contingency=proc_cont, project_contingency=proj_cont,
            tpc=tpc, owners_costs=owners, total_owners_cost=total_owners,
            toc=toc, tasc_toc_factor=factor, tasc=toc * factor,
        )
