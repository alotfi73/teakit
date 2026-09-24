"""
tea.plant_sections — NETL account-level capital cost scaling.
=============================================================

:mod:`tea.equipment` scales one machine at a time. This module scales whole
**plant sections** — "Coal Handling", "Syngas Cleanup", "Cooling Water System",
"Instrumentation & Control" — against a published reference plant.

That is usually what you actually want. If you have a NETL baseline case that
resembles your plant and you need it at a different capacity, scaling 100-odd
accounts against their own process parameters is far more defensible than
scaling a bottom-up equipment list, because NETL's exponents were regressed
from real vendor quotes rather than assumed:

    "This equation is similar to a six tenth factor approach, however, the
    exponents have been trained using several vendor quotes."

THE EQUATION
------------
For nearly every account (QGESS Equation 3 / 5)::

    SC = RC * (SP / RP) ** Exp

    SC  = scaled cost           RC  = reference cost
    SP  = scaling parameter     RP  = reference parameter
    Exp = exponent

A handful of IGCC accounts carry a coefficient instead and use Equation 4::

    SC = (RC / RTPC) * C * SP ** Exp

and the air separation unit and Cansolv accounts blend two parameters
(Equation 6). All of these are handled by :func:`scale_account`.

Cost levels are scaled *separately*: run the equation once with the reference
equipment cost, once with the material cost, once with the labour cost. Their
sum is the scaled BEC. Contingencies are then applied as the reference plant's
percentages of BEC (QGESS Equation 2), and the sum is the scaled TPC.

WHAT THE EXPONENTS TELL YOU
---------------------------
Read down the tables and the physics is visible:

* **0.62-0.79** — the classic economy-of-scale band. Coal handling, feedwater,
  FGD, gasifier auxiliaries, cooling towers, HRSG. Close to the six-tenths rule.
* **~0.13** — all Instrumentation & Control accounts. A control system is
  mostly fixed cost; doubling plant size barely moves it.
* **0.00** — combustion turbines, boiler buildings, machine shops, warehouses,
  protective equipment. These are *discrete or fixed*: "Combustion turbines are
  manufactured in discrete sizes. As such, certain cost accounts become fixed
  costs for a given combustion turbine size." A gas turbine does not scale —
  you buy a different frame, or you buy two.
* **>1.0** — a few genuinely diseconomic accounts: PC condenser (1.04), IGCC
  mercury carbon bed (1.64), NGCC HRSG accessories (1.40) and main power
  transformers (1.36). Not errors; check them against your own case.

The spread from 0.00 to 1.64 is exactly why a single plant-wide six-tenths
factor mis-allocates cost, even when it lands near the right total.

LIMITATIONS (from the source document, and they matter)
-------------------------------------------------------
* Technologies must match closely: coal type, oxidant, elevation, plant type,
  emissions controls. Do not scale a capture case from a non-capture case.
* Single-parameter scaling is an approximation — many accounts really depend
  on more than one parameter, and on pressure and temperature.
* Ranges given are where the exponent has *already been used*. NETL expects
  validity over roughly the median ± 25%.
* Step changes in vendor pricing at certain sizes are not captured.
* Train count and redundancy (2 x 100% vs 3 x 50%) must be adjusted separately.
* Cost basis is **December 2018 dollars**. Escalate with :mod:`tea.indices`.
* "In general, the approach presented in this report is valid for high-level
  evaluation only. The accuracy of the factored estimate will be less than or
  equal to that for a reference estimate."

SOURCE
------
NETL (2022), "Quality Guidelines for Energy System Studies: Capital Cost
Scaling Methodology: Revision 4a Report", DOE/NETL-2022/3340, October 2022.
https://www.osti.gov/servlets/purl/1893821  (OSTI record: /biblio/1893821)

Reference cases come from "Cost and Performance Baseline for Fossil Energy
Plants Volume 1: Bituminous Coal and Natural Gas to Electricity Revision 4a".
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CATEGORIES", "ACCOUNTS", "scale_account", "scale_case",
    "accounts_for", "account_table", "derive_exponent", "AccountResult",
]


# ============================================================================
# Category matrix (Exhibits 2-1, 3-1, 3-15, 3-30)
# ============================================================================
CATEGORIES: dict[int, str] = {
    1: "Supercritical PC, air-fired, with and without CO2 capture, Illinois No. 6 coal",
    2: "Subcritical PC, air-fired, with and without CO2 capture, Illinois No. 6 coal",
    3: "IGCC: two-stage, slurry-feed, oxygen-blown gasifier, +/- CO2 capture, Illinois No. 6",
    4: "IGCC: single-stage, slurry-feed, oxygen-blown gasifier, +/- CO2 capture, Illinois No. 6",
    5: "IGCC: single-stage, dry-feed, oxygen-blown up-flow gasifier, +/- CO2 capture, Illinois No. 6",
    6: "NGCC: natural gas, air-fired, with and without CO2 capture",
}

TECHNOLOGY_CATEGORIES = {"PC": (1, 2), "IGCC": (3, 4, 5), "NGCC": (6,)}

#: Dollar-year basis of every reference cost these exponents apply to.
BASIS_YEAR = 2018
BASIS_NOTE = ("Developed from and intended for use with December 2018 cost data "
              "(Fossil Energy Baseline Revision 4a).")


# ============================================================================
# Account tables (Exhibits 3-2 to 3-40)
# ============================================================================
# Each entry: (account, item description, scaling parameter, unit,
#              exponent, range, note)
# `exponent` is a float when it applies to every category in the technology,
# or a dict {category: exponent} when NETL distinguishes them.
def _a(acct, name, param, unit, exp, lo, hi, note=""):
    return dict(account=acct, name=name, parameter=param, unit=unit,
                exponent=exp, valid=(lo, hi), note=note)


_PC = [
    # --- 1 COAL & SORBENT HANDLING (Exhibit 3-2) ---------------------------
    _a("1.1", "Coal Receive & Unload", "Coal feed rate", "lb/h", 0.62, 472_000, 635_000),
    _a("1.2", "Coal Stackout & Reclaim", "Coal feed rate", "lb/h", 0.62, 472_000, 635_000),
    _a("1.3", "Coal Conveyors & Yard Crushing", "Coal feed rate", "lb/h", 0.62, 472_000, 635_000),
    _a("1.4", "Other Coal Handling", "Coal feed rate", "lb/h", 0.62, 472_000, 635_000),
    _a("1.5", "Sorbent Receive & Unload", "Limestone feed rate", "lb/h", {1: 0.66, 2: 0.62}, 45_600, 61_400),
    _a("1.6", "Sorbent Stackout & Reclaim", "Limestone feed rate", "lb/h", 0.64, 45_600, 61_400),
    _a("1.7", "Sorbent Conveyors", "Limestone feed rate", "lb/h", {1: 0.65, 2: 0.64}, 45_600, 61_400),
    _a("1.8", "Other Sorbent Handling", "Limestone feed rate", "lb/h", 0.64, 45_600, 61_400),
    _a("1.9", "Coal & Sorbent Handling Foundations", "Coal + limestone feed rate", "lb/h", 0.62, 517_700, 695_800),
    # --- 2 COAL & SORBENT PREPARATION & FEED (Exhibit 3-3) -----------------
    _a("2.1", "Coal Crushing & Drying", "Coal feed rate", "lb/h", 0.66, 472_000, 635_000),
    _a("2.2", "Prepared Coal Storage & Feed", "Coal feed rate", "lb/h", 0.66, 472_000, 635_000),
    _a("2.5", "Sorbent Preparation Equipment", "Limestone feed rate", "lb/h", 0.65, 45_600, 61_400),
    _a("2.6", "Sorbent Storage & Feed", "Limestone feed rate", "lb/h", 0.65, 45_600, 61_400),
    _a("2.9", "Coal & Sorbent Feed Foundation", "Coal + limestone feed rate", "lb/h", 0.64, 517_700, 695_800),
    # --- 3 FEEDWATER & MISC BOP (Exhibit 3-4) ------------------------------
    _a("3.1", "Feedwater System", "Feedwater flow (HP only)", "lb/h", {1: 0.69, 2: 0.68}, 4_120_000, 5_317_000),
    _a("3.2", "Water Makeup & Pretreating", "Raw water withdrawal", "gpm", {1: 0.73, 2: 0.75}, 6_000, 10_700),
    _a("3.3", "Other Feedwater Subsystems", "Feedwater flow (HP only)", "lb/h", 0.89, 4_120_000, 5_317_000),
    _a("3.4", "Service Water Systems", "Raw water withdrawal", "gpm", 0.80, 6_000, 10_700),
    _a("3.5", "Other Boiler Plant Systems", "Feedwater flow (HP only)", "lb/h", 0.90, 4_120_000, 5_317_000),
    _a("3.6", "Natural Gas Pipeline and Start-up System", "Total fuel feed", "lb/h", {1: 0.49, 2: 0.51}, 472_000, 635_000),
    _a("3.7", "Waste Water Treatment Equipment", "Process water discharge", "gpm", {1: 0.71, 2: 0.73}, 1_200, 3_100),
    _a("3.8", "Spray Dryer Evaporator", "Gas flow to SDE", "acfm", 0.75, 123_000, 166_000),
    _a("3.9", "Miscellaneous Plant Equipment", "Total fuel feed", "lb/h", 0.25, 472_000, 635_000),
    # --- 4 PC BOILER & ACCESSORIES (Exhibit 3-5) ---------------------------
    _a("4.9", "PC Boiler & Accessories (air-fired)", "Feedwater flow (HP only)", "lb/h", {1: 0.76, 2: 0.78}, 4_120_000, 5_317_000,
       "No Rev-4 guidance exists for CFBC, oxy-fired PC or PC with biomass."),
    _a("4.10", "SCR System", "Gas flow to DSI", "acfm", 0.69, 2_489_900, 3_346_700),
    _a("4.11", "Boiler Balance of Plant", "Coal feed rate", "lb/h", 0.69, 472_000, 635_000),
    _a("4.12", "Primary Air System", "Primary air flow rate", "acfm", 0.69, 249_300, 335_200),
    _a("4.13", "Secondary Air System", "Forced draft air flow rate", "acfm", 0.69, 811_700, 1_091_100),
    _a("4.14", "Induced Draft Fans", "Gas flow from baghouse", "acfm", 0.69, 1_717_500, 2_308_500),
    _a("4.15", "Major Component Rigging", "Coal feed rate", "lb/h", 0.69, 472_000, 635_000),
    _a("4.16", "Boiler Foundations", "Coal feed rate", "lb/h", 0.69, 472_000, 635_000),
    # --- 5 FLUE GAS CLEANUP (Exhibit 3-6) ----------------------------------
    _a("5.1", "Cansolv CO2 Removal System", "CO2 product flow rate / gas flow to CO2 absorber", "lb/h, acfm", 0.60, 1_281_000, 1_348_000,
       "BLENDED: 60% of cost scales on CO2 product flow (lb/h, 1,281,000-1,348,000); "
       "40% on gas flow to CO2 absorber (acfm, 1,865,000-1,962,000). Use blend=True."),
    _a("5.2", "Wet FGD Absorber Vessels & Accessories", "Wet FGD exit gas flow", "acfm", 0.73, 1_459_000, 1_962_000),
    _a("5.3", "Other FGD", "Wet FGD exit gas flow", "acfm", 0.73, 1_459_000, 1_962_000),
    _a("5.4", "CO2 Compression & Drying", "CO2 compressor load", "kW", 0.61, 17_000, 46_700,
       "Valid only at the modelled suction (28.9 psia) and discharge (2,214.7 psia) pressures."),
    _a("5.5", "CO2 Compressor Aftercooler", "CO2 aftercooler duty", "MMBtu/h", 0.83, 32, 88),
    _a("5.6", "Mercury Removal (DSI/ACI)", "Brominated activated carbon injection rate", "tpd", {1: 0.78, 2: 0.80}, 1.2, 1.7),
    _a("5.9", "Particulate Removal (baghouse & accessories)", "Gas flow to baghouse", "acfm", 0.79, 1_691_000, 2_274_000),
    _a("5.12", "Gas Cleanup Foundations", "Coal feed rate", "lb/h", 0.79, 472_000, 635_000),
    _a("5.13", "Gypsum Dewatering System", "Gypsum production rate", "tpd", {1: 0.58, 2: 0.60}, 830, 1_120),
    # --- 7 DUCTWORK & STACK (Exhibit 3-7) ----------------------------------
    _a("7.3", "Ductwork", "Total fuel feed", "lb/h", 0.29, 472_000, 635_000),
    _a("7.4", "Stack", "Gas flow to stack", "acfm", 0.06, 1_314_000, 1_522_000),
    _a("7.5", "Duct & Stack Foundations", "Total fuel feed", "lb/h", 0.06, 472_000, 635_000),
    # --- 8 STEAM TURBINE & ACCESSORIES (Exhibit 3-8) -----------------------
    _a("8.1", "Steam Turbine Generator & Accessories", "Steam turbine gross power", "kW", 0.70, 685_000, 776_000),
    _a("8.2", "Steam Turbine Plant Auxiliaries", "Steam turbine gross power", "kW", {1: 0.70, 2: 0.71}, 685_000, 776_000),
    _a("8.3a", "Condenser & Auxiliaries", "Condenser duty", "MMBtu/h", {1: 1.04, 2: 0.86}, 2_010, 2_650),
    _a("8.3b", "Air Cooled Condenser", "Condenser duty", "MMBtu/h", None, 0, 0,
       "Revision 4 cases use wet cooling exclusively; no scaling guidance developed."),
    _a("8.4", "Steam Piping", "Feedwater flow (HP only)", "lb/h", 0.70, 4_120_000, 5_317_000),
    _a("8.5", "Turbine Generator Foundations", "Steam turbine gross power", "kW", 0.71, 685_000, 776_000),
    # --- 9 COOLING WATER SYSTEM (Exhibit 3-9) ------------------------------
    _a("9.1", "Cooling Towers", "Cooling tower duty", "MMBtu/h", {1: 0.77, 2: 0.76}, 2_550, 4_880),
    _a("9.2", "Circulating Water Pumps", "Circulating water flow rate", "gpm", 0.86, 255_000, 498_000),
    _a("9.3", "Circ. Water System Auxiliaries", "Circulating water flow rate", "gpm", 0.63, 255_000, 498_000),
    _a("9.4", "Circ. Water Piping", "Circulating water flow rate", "gpm", 0.63, 255_000, 498_000),
    _a("9.5", "Make-up Water System", "Raw water withdrawal", "gpm", 0.49, 6_000, 10_700),
    _a("9.6", "Component Cooling Water System", "Circulating water flow rate", "gpm", 0.63, 255_000, 498_000),
    _a("9.7", "Circ. Water System Foundations", "Circulating water flow rate", "gpm", 0.58, 255_000, 498_000),
    # --- 10 ASH & SPENT SORBENT HANDLING (Exhibit 3-10) --------------------
    _a("10.6", "Ash Storage Silos", "Total ash flow rate", "lb/h", 0.56, 52_000, 70_400),
    _a("10.7", "Ash Transport & Feed Equipment", "Total ash flow rate", "lb/h", 0.56, 52_000, 70_400),
    _a("10.9", "Ash / Spent Sorbent Foundation", "Total ash flow rate", "lb/h", 0.56, 52_000, 70_400),
    # --- 11 ACCESSORY ELECTRIC PLANT (Exhibit 3-11) ------------------------
    _a("11.1", "Generator Equipment", "Steam turbine gross power", "kW", 0.57, 685_000, 776_000),
    _a("11.2", "Station Service Equipment", "Auxiliary load", "kW", 0.43, 35_000, 125_800),
    _a("11.3", "Switchgear & Motor Control", "Auxiliary load", "kW", 0.43, 35_000, 125_800),
    _a("11.4", "Conduit & Cable Tray", "Auxiliary load", "kW", 0.43, 35_000, 125_800),
    _a("11.5", "Wire & Cable", "Auxiliary load", "kW", 0.43, 35_000, 125_800),
    _a("11.6", "Protective Equipment", "Auxiliary load", "kW", 0.00, 35_000, 125_800, "Fixed cost."),
    _a("11.7", "Standby Equipment", "Steam turbine gross power", "kW", 0.46, 685_000, 776_000),
    _a("11.8", "Main Power Transformers", "STG rating", "MVA", 0.70, 760, 860),
    _a("11.9", "Electrical Foundations", "Steam turbine gross power", "kW", 0.69, 685_000, 776_000),
    # --- 12 INSTRUMENTATION & CONTROL (Exhibit 3-12) -----------------------
    *[_a(n, d, "Auxiliary load", "kW", 0.13, 35_000, 125_800,
         "I&C is largely a fixed cost; exponent 0.13 barely responds to plant size.")
      for n, d in [("12.1", "PC Boiler Control Equipment"),
                   ("12.3", "Steam Turbine Control Equipment"),
                   ("12.5", "Signal Processing Equipment"),
                   ("12.6", "Control Boards, Panels & Racks"),
                   ("12.7", "Distributed Control System Equipment"),
                   ("12.8", "Instrument Wiring & Tubing"),
                   ("12.9", "Other I&C Equipment")]],
    # --- 13 IMPROVEMENTS TO SITE (Exhibit 3-13) ----------------------------
    *[_a(n, d, "BEC (minus accounts 13 and 14)", "$1000", 0.20, 883_600, 1_622_000)
      for n, d in [("13.1", "Site Preparation"), ("13.2", "Site Improvements"),
                   ("13.3", "Site Facilities")]],
    # --- 14 BUILDINGS & STRUCTURES (Exhibit 3-14) --------------------------
    _a("14.2", "Boiler Building", "BEC (minus accounts 13 and 14)", "$1000", 0.00, 883_600, 1_622_000),
    _a("14.3", "Steam Turbine Building", "BEC (minus accounts 13 and 14)", "$1000", 0.00, 883_600, 1_622_000),
    _a("14.4", "Administration Building", "Steam turbine gross power", "kW", 0.00, 685_000, 776_000),
    _a("14.5", "Circulation Water Pumphouse", "Circulating water flow rate", "gpm", {1: 0.60, 2: 0.59}, 255_000, 498_000),
    _a("14.6", "Water Treatment Buildings", "Raw water withdrawal", "gpm", 0.50, 6_000, 10_700),
    _a("14.7", "Machine Shop", "Steam turbine gross power", "kW", 0.00, 685_000, 776_000),
    _a("14.8", "Warehouse", "Steam turbine gross power", "kW", 0.00, 685_000, 776_000),
    _a("14.9", "Other Buildings & Structures", "Steam turbine gross power", "kW", 0.00, 685_000, 776_000),
    _a("14.10", "Waste Treating Building & Structures", "Raw water withdrawal", "gpm", 0.05, 6_000, 10_700),
]

_IGCC = [
    # --- 1 COAL HANDLING (Exhibit 3-16) ------------------------------------
    *[_a(n, d, "Coal feed rate", "lb/h", 0.62, 435_000, 483_000)
      for n, d in [("1.1", "Coal Receive & Unload"), ("1.2", "Coal Stackout & Reclaim"),
                   ("1.3", "Coal Conveyors & Yard Crush"), ("1.4", "Other Coal Handling"),
                   ("1.9", "Coal & Sorbent Handling Foundations")]],
    # --- 2 COAL PREPARATION & FEED (Exhibit 3-17) --------------------------
    *[_a(n, d, "Coal feed rate", "lb/h", 0.66, 435_000, 483_000)
      for n, d in [("2.1", "Coal Crushing & Drying"), ("2.2", "Prepared Coal Storage & Feed"),
                   ("2.3", "Dry / Slurry Coal Injection System"),
                   ("2.4", "Miscellaneous Coal Prep & Feed"),
                   ("2.9", "Coal & Sorbent Feed Foundation")]],
    # --- 3 FEEDWATER & MISC BOP (Exhibit 3-18) -----------------------------
    _a("3.1", "Feedwater System", "Feedwater flow (HP only)", "lb/h", 0.71, 839_700, 1_597_000),
    _a("3.2", "Water Makeup & Pretreating", "Raw water withdrawal", "gpm", 0.71, 4_100, 6_300),
    _a("3.3", "Other Feedwater Subsystems", "Feedwater flow (HP only)", "lb/h", 0.71, 839_700, 1_597_000),
    _a("3.4", "Service Water Systems", "Raw water withdrawal", "gpm", 0.71, 4_100, 6_300),
    _a("3.5", "Other Boiler Plant Systems", "Feedwater flow (HP only)", "lb/h", 0.73, 839_700, 1_597_000),
    _a("3.6", "Natural Gas Pipeline and Start-Up System", "Coal feed rate", "lb/h", 0.24, 435_000, 483_000),
    _a("3.7", "Waste Water Treatment Equipment", "Process water discharge", "gpm", 0.71, 900, 1_220),
    _a("3.8", "Vacuum Flash, Brine Concentrator & Crystallizer", "Syngas scrubber blowdown flow rate", "gpm", 0.76, 275, 635),
    _a("3.9", "Miscellaneous Plant Equipment", "Coal feed rate", "lb/h", 0.24, 435_000, 483_000),
    # --- 4 GASIFIER, ASU & ACCESSORIES (Exhibit 3-19) ----------------------
    _a("4.1", "Gasifier & Auxiliaries", "Coal feed rate", "lb/h", {3: 0.19, 4: 0.70, 5: 1.42}, 435_000, 483_000,
       "Category 4 is nuanced: use 0.70 for general changes; use 0.00 for small changes "
       "within a set gasifier feed rate (<=18,200 lb/h / 220 tpd), since gasifiers are "
       "marketed at fixed inlet rates; and for changes large enough to add or remove a "
       "full train (e.g. +/-50%), multiply the reference cost by the train-count ratio "
       "(x1.5 to add one of two trains, x0.5 to remove one)."),
    _a("4.2", "Syngas Cooler", "Syngas cooler duty", "MMBtu/h", {3: 0.33, 5: 0.33}, 110, 200,
       "Not applicable to category 4."),
    _a("4.3", "Air Separation Unit / Oxidant Compression", "O2 production / main air compressor load", "TPD, kW", 0.60, 4_000, 4_800,
       "BLENDED (Equation 6): 50% on O2 production (TPD, 4,000-4,800) at exponent 0.60, "
       "50% on main air compressor load (kW, 61,000-71,400) at exponent 0.60."),
    _a("4.5", "Miscellaneous Gasification Equipment", "Coal feed rate", "lb/h", 0.50, 435_000, 483_000),
    _a("4.6", "LT Heat Recovery & Flue Gas Saturation", "Coal feed rate", "lb/h", None, 435_000, 483_000,
       "Maintain the reference case ratio of Account 4.6 to Account 4.1 rather than scaling directly."),
    _a("4.7", "Flare Stack System", "Coal feed rate", "lb/h", 0.50, 435_000, 483_000),
    _a("4.8", "Black Water & Sour Gas Section", "Coal feed rate", "lb/h", None, 435_000, 483_000,
       "Costs are included in Account 4.1; no separate scaling guidance."),
    _a("4.15", "Major Component Rigging", "Coal feed rate", "lb/h", 0.50, 435_000, 483_000),
    _a("4.16", "Gasification Foundations", "Coal feed rate", "lb/h", 0.50, 435_000, 483_000),
    # --- 5 SYNGAS CLEANUP (Exhibit 3-20) -----------------------------------
    _a("5.1", "Double Stage Selexol", "Gas flow to CO2 absorber", "acfm", 0.79, 6_500, 14_000),
    _a("5.2", "Sulfur Removal (Sulfinol, MDEA, single-stage Selexol)", "Gas flow to CO2 absorber", "acfm", 0.70, 6_500, 14_000,
       "Only one data point per system exists, so no exponent was derived; NETL "
       "recommends 0.70 on gas flow to the CO2 absorber."),
    _a("5.3", "Elemental Sulfur Plant", "Sulfur production", "lb/h", 0.67, 10_800, 12_100),
    _a("5.4", "Carbon Dioxide Compression & Drying", "CO2 compressor load", "kW", 0.88, 17_000, 46_700,
       "Valid only at the modelled suction/discharge pressures and the compressor "
       "configuration compatible with a double-stage Selexol system."),
    _a("5.5", "Carbon Dioxide Aftercooler", "CO2 aftercooler duty", "MMBtu/h", 0.83, 32, 88),
    _a("5.6", "Mercury Removal (carbon bed)", "Sulfur-impregnated activated carbon initial fill", "ft3", 1.64, 3_400, 7_600,
       "Exponent > 1: this account is diseconomic in scale."),
    _a("5.7", "Shift Reactors", "WGS catalyst initial fill", "ft3", 0.80, 9_800, 25_800),
    _a("5.8", "COS Hydrolysis", "COS hydrolysis catalyst volume", "ft3", 0.80, 1_300, 2_200),
    _a("5.9", "Particulate Removal", "Candle filter flow rate", "acfm", {3: 0.79, 5: 0.79}, 19_200, 29_300,
       "Not applicable to category 4."),
    _a("5.10", "Blowback Gas Systems", "Candle filter flow rate", "acfm", 0.30, 13_700, 29_300),
    _a("5.11", "Fuel Gas Piping", "Syngas flow rate", "lb/h", 0.72, 182_300, 870_300),
    _a("5.12", "Gas Cleanup Foundations", "Sulfur production", "lb/h", 0.79, 10_800, 12_100),
    # --- 6 COMBUSTION TURBINE & ACCESSORIES (Exhibit 3-21) -----------------
    _a("6.1", "Combustion Turbine Generator", "Syngas flow rate", "lb/h", 0.00, 182_300, 870_300,
       "Fixed cost. Scale capture-to-capture or non-capture-to-non-capture only; "
       "CTG costs differ slightly between the two and must not be crossed."),
    _a("6.2", "Syngas Expander", "Syngas flow rate", "lb/h", {4: 0.88}, 182_300, 870_300,
       "Category 4 only."),
    _a("6.3", "Combustion Turbine Accessories", "Syngas flow rate", "lb/h", 0.00, 182_300, 870_300),
    _a("6.4", "Compressed Air Piping", "Syngas flow rate", "lb/h", 0.00, 182_300, 870_300),
    _a("6.5", "Combustion Turbine Foundations", "Syngas flow rate", "lb/h", 0.00, 182_300, 870_300),
    # --- 7 HRSG, DUCTWORK & STACK (Exhibit 3-22) ---------------------------
    _a("7.1", "Heat Recovery Steam Generator", "HRSG duty", "MMBtu/h", 0.70, 1_770, 1_930),
    _a("7.2", "HRSG Accessories", "HRSG duty", "MMBtu/h", 0.70, 1_770, 1_930),
    _a("7.3", "Ductwork", "Gas flow to stack", "acfm", {3: 0.64, 4: 0.70, 5: 0.70}, 2_611_000, 2_705_000),
    _a("7.4", "Stack", "Gas flow to stack", "acfm", 0.70, 2_611_000, 2_705_000),
    _a("7.5", "HRSG, Ductwork & Stack Foundations", "Gas flow to stack", "acfm", {3: 0.70, 4: 0.70, 5: 0.73}, 2_611_000, 2_705_000),
    # --- 8 STEAM TURBINE & ACCESSORIES (Exhibit 3-23) ----------------------
    _a("8.1", "Steam Turbine Generator & Accessories", "Steam turbine gross power", "kW", 0.70, 217_400, 301_200),
    _a("8.2", "Steam Turbine Plant Auxiliaries", "Steam turbine gross power", "kW", 0.71, 217_400, 301_200),
    _a("8.3a", "Condenser & Auxiliaries", "Condenser duty", "MMBtu/h", 0.71, 1_275, 1_570),
    _a("8.4", "Steam Piping", "Feedwater flow (HP only)", "lb/h", 0.72, 839_700, 1_597_000),
    _a("8.5", "Turbine Generator Foundations", "Steam turbine gross power", "kW", 0.72, 217_400, 301_200),
    # --- 9 COOLING WATER SYSTEM (Exhibit 3-24) -----------------------------
    _a("9.1", "Cooling Towers", "Cooling tower duty", "MMBtu/h", 0.72, 1_920, 2_540),
    _a("9.2", "Circulating Water Pumps", "Circulating water flow rate", "gpm", 0.72, 192_000, 253_700),
    _a("9.3", "Circulating Water System Auxiliaries", "Circulating water flow rate", "gpm", {3: 0.64, 4: 0.67, 5: 0.67}, 192_000, 253_700),
    _a("9.4", "Circulating Water Piping", "Circulating water flow rate", "gpm", 0.61, 192_000, 253_700),
    _a("9.5", "Make-up Water System", "Raw water withdrawal", "gpm", 0.63, 4_100, 6_300),
    _a("9.6", "Component Cooling Water System", "Circulating water flow rate", "gpm", 0.64, 192_000, 253_700),
    _a("9.7", "Circulating Water System Foundations", "Circulating water flow rate", "gpm", 0.59, 192_000, 253_700),
    # --- 10 SLAG RECOVERY & HANDLING (Exhibit 3-25) ------------------------
    *[_a(n, d, "Slag production", "lb/h", 0.64, 43_600, 53_000)
      for n, d in [("10.1", "Slag Dewatering & Cooling"),
                   ("10.2", "Gasifier Ash Depressurization"),
                   ("10.3", "Cleanup Ash Depressurization")]],
    *[_a(n, d, "Slag production", "lb/h", 0.55, 43_600, 53_000)
      for n, d in [("10.6", "Ash Storage Silos"), ("10.7", "Ash Transport & Feed Equipment"),
                   ("10.8", "Miscellaneous Ash Handling Equipment"),
                   ("10.9", "Ash / Spent Sorbent Foundation")]],
    # --- 11 ACCESSORY ELECTRIC PLANT (Exhibit 3-26) ------------------------
    _a("11.1", "Generator Equipment", "Steam turbine gross power", "kW", 0.54, 217_400, 301_200),
    *[_a(n, d, "Auxiliary load", "kW", 0.45, 122_400, 185_600)
      for n, d in [("11.2", "Station Service Equipment"), ("11.3", "Switchgear & Motor Control"),
                   ("11.4", "Conduit & Cable Tray"), ("11.5", "Wire & Cable")]],
    _a("11.6", "Protective Equipment", "Auxiliary load", "kW", 0.00, 122_400, 185_600, "Fixed cost."),
    _a("11.7", "Standby Equipment", "Total plant gross power", "kW", 0.48, 684_700, 765_200),
    _a("11.8", "Main Power Transformers", "Total plant gross power", "kW", 0.71, 684_700, 765_200),
    _a("11.9", "Electrical Foundations", "Total plant gross power", "kW", 0.70, 684_700, 765_200),
    # --- 12 INSTRUMENTATION & CONTROL (Exhibit 3-27) -----------------------
    *[_a(n, d, "Auxiliary load", "kW", 0.13, 122_400, 185_600,
         "I&C is largely a fixed cost.")
      for n, d in [("12.1", "IGCC Control Equipment"),
                   ("12.2", "Combustion Turbine Control Equipment"),
                   ("12.3", "Steam Turbine Control Equipment"),
                   ("12.4", "Other Major Component Control Equipment"),
                   ("12.5", "Signal Processing Equipment"),
                   ("12.6", "Control Boards, Panels & Racks"),
                   ("12.7", "Distributed Control System Equipment"),
                   ("12.8", "Instrument Wiring & Tubing"),
                   ("12.9", "Other I&C Equipment")]],
    # --- 13 IMPROVEMENTS TO SITE (Exhibit 3-28) ----------------------------
    _a("13.1", "Site Preparation", "BEC (minus accounts 13 and 14)", "$1000", 0.09, 1_494_000, 2_188_000),
    _a("13.2", "Site Improvements", "BEC (minus accounts 13 and 14)", "$1000", 0.09, 1_494_000, 2_188_000),
    _a("13.3", "Site Facilities", "BEC (minus accounts 13 and 14)", "$1000", 0.08, 1_494_000, 2_188_000),
    # --- 14 BUILDINGS & STRUCTURES (Exhibit 3-29) --------------------------
    _a("14.1", "Combustion Turbine Area", "Combustion turbine gross power", "kW", 0.00, 348_000, 580_000),
    _a("14.3", "Steam Turbine Building", "Steam turbine gross power", "kW", 0.06, 217_400, 301_200),
    _a("14.4", "Administration Building", "Steam turbine gross power", "kW", 0.04, 217_400, 301_200),
    _a("14.5", "Circulation Water Pumphouse", "Circulating water flow rate", "gpm", 0.46, 192_000, 253_700),
    _a("14.6", "Water Treatment Buildings", "Raw water withdrawal", "gpm", 0.71, 4_100, 6_300),
    _a("14.7", "Machine Shop", "Steam turbine gross power", "kW", 0.02, 217_400, 301_200),
    _a("14.8", "Warehouse", "Steam turbine gross power", "kW", 0.02, 217_400, 301_200),
    _a("14.9", "Other Buildings & Structures", "Steam turbine gross power", "kW", 0.02, 217_400, 301_200),
    _a("14.10", "Waste Treating Building & Structures", "Raw water withdrawal", "gpm", 0.09, 4_100, 6_300),
]

_NGCC = [
    # --- 3 FEEDWATER & MISC BOP (Exhibit 3-31) -----------------------------
    _a("3.1", "Feedwater System", "Feedwater flow (HP only)", "lb/h", 0.72, 803_200, 1_339_000),
    _a("3.2", "Water Makeup & Pretreating", "Raw water withdrawal", "gpm", 0.73, 2_900, 4_700),
    _a("3.3", "Other Feedwater Subsystems", "Feedwater flow (HP only)", "lb/h", 0.72, 803_200, 1_339_000),
    _a("3.4", "Service Water Systems", "Raw water withdrawal", "gpm", 0.73, 2_900, 4_700),
    _a("3.5", "Other Boiler Plant Systems", "Raw water withdrawal", "gpm", 0.00, 0, 0, "Fixed cost; no range given."),
    _a("3.6", "Natural Gas Pipeline and Start-Up System", "Natural gas feed rate", "lb/h", 0.00, 0, 0,
       "The natural gas pipeline is an ADDITIVE cost and must not be scaled -- scaling "
       "it effectively lengthens or shortens the pipe. Build the pipeline cost up "
       "separately for your site."),
    _a("3.7", "Waste Water Treatment Equipment", "Process water discharge", "gpm", 0.71, 650, 1_670),
    _a("3.9", "Miscellaneous Plant Equipment", "Natural gas feed rate", "lb/h", 0.00, 0, 0),
    # --- 5B FLUE GAS CLEANUP (Exhibit 3-32) --------------------------------
    _a("5.1", "Cansolv CO2 Removal System", "CO2 product flow rate / gas flow to CO2 absorber", "lb/h, acfm", 0.60, 370_000, 617_000,
       "BLENDED: 60% of cost scales on CO2 product flow (lb/h, 370,000-617,000); 40% on "
       "gas flow to CO2 absorber (acfm, 1,915,000-3,192,000). Use blend=True."),
    _a("5.4", "CO2 Compression & Drying", "CO2 compressor load", "kW", 0.41, 17_000, 46_700,
       "Valid only at the modelled suction (28.9 psia) and discharge (2,214.7 psia) pressures."),
    _a("5.5", "CO2 Compressor Aftercooler", "CO2 aftercooler duty", "MMBtu/h", 0.83, 32, 88),
    _a("5.12", "Gas Cleanup Foundations", "CO2 flow rate", "lb/h", 0.79, 370_000, 617_000),
    # --- 6 COMBUSTION TURBINE & ACCESSORIES (Exhibit 3-33) -----------------
    *[_a(n, d, p, "lb/h" if "gas" in p.lower() else "kW", 0.00, 0, 0,
         "Combustion turbines are manufactured in discrete sizes, so this is a fixed "
         "cost for a given frame. Do not scale -- change the machine or the count.")
      for n, d, p in [("6.1", "Combustion Turbine Generator", "Natural gas feed rate"),
                      ("6.3", "Combustion Turbine Accessories", "Natural gas feed rate"),
                      ("6.4", "Compressed Air Piping", "Natural gas feed rate"),
                      ("6.5", "Combustion Turbine Foundations", "Combustion turbine gross power")]],
    # --- 7 HRSG, DUCTWORK & STACK (Exhibit 3-34) ---------------------------
    _a("7.1", "Heat Recovery Steam Generator", "HRSG duty", "MMBtu/h", 0.70, 1_950, 2_300),
    _a("7.2", "HRSG Accessories", "HRSG duty", "MMBtu/h", 1.40, 1_950, 2_300,
       "Exponent > 1: diseconomic in scale."),
    _a("7.3", "Ductwork", "Gas flow to stack", "acfm", 0.70, 1_833_000, 2_365_000),
    _a("7.4", "Stack", "Gas flow to stack", "acfm", 0.70, 1_833_000, 2_365_000),
    _a("7.5", "HRSG, Ductwork & Stack Foundations", "Gas flow to stack", "acfm", 0.70, 1_833_000, 2_365_000),
    _a("7.6", "Selective Catalytic Reduction System", "Flue gas flow to HRSG", "acfm", 0.00, 0, 0, "Fixed cost."),
    # --- 8 STEAM TURBINE & ACCESSORIES (Exhibit 3-35) ----------------------
    _a("8.1", "Steam Turbine Generator & Accessories", "Steam turbine gross power", "kW", 0.80, 212_500, 263_000),
    _a("8.2", "Steam Turbine Plant Auxiliaries", "Steam turbine gross power", "kW", 0.73, 212_500, 263_000),
    _a("8.3", "Condenser & Auxiliaries", "Condenser duty", "MMBtu/h", 0.80, 788, 1_340),
    _a("8.4", "Steam Piping", "Feedwater flow (HP only)", "lb/h", 0.00, 803_200, 1_339_000,
       "HP steam flow is identical between the NGCC capture and non-capture cases; fixed."),
    _a("8.5", "Turbine Generator Foundations", "Steam turbine gross power", "kW", 0.73, 212_500, 263_000),
    # --- 9 COOLING WATER SYSTEM (Exhibit 3-36) -----------------------------
    _a("9.1", "Cooling Towers", "Cooling tower duty", "MMBtu/h", 0.73, 1_300, 2_200),
    _a("9.2", "Circulating Water Pumps", "Circulating water flow rate", "gpm", 0.72, 135_700, 220_800),
    _a("9.3", "Circ. Water System Auxiliaries", "Circulating water flow rate", "gpm", 0.49, 135_700, 220_800),
    _a("9.4", "Circ. Water Piping", "Circulating water flow rate", "gpm", 0.60, 135_700, 220_800),
    _a("9.5", "Make-up Water System", "Raw water withdrawal", "gpm", 0.40, 2_900, 4_700),
    _a("9.6", "Component Cooling Water System", "Circulating water flow rate", "gpm", 0.60, 135_700, 220_800),
    _a("9.7", "Circ. Water System Foundations", "Circulating water flow rate", "gpm", 0.60, 135_700, 220_800),
    # --- 11 ACCESSORY ELECTRIC PLANT (Exhibit 3-37) ------------------------
    _a("11.1", "Generator Equipment", "Total plant gross power", "kW", 0.59, 689_800, 740_100),
    *[_a(n, d, "Auxiliary load", "kW", 0.64, 13_500, 44_000)
      for n, d in [("11.2", "Station Service Equipment"), ("11.3", "Switchgear & Motor Control"),
                   ("11.4", "Conduit & Cable Tray"), ("11.5", "Wire & Cable")]],
    _a("11.6", "Protective Equipment", "Auxiliary load", "kW", 1.10, 13_500, 44_000,
       "Exponent > 1: diseconomic in scale."),
    _a("11.7", "Standby Equipment", "Total plant gross power", "kW", 0.48, 689_800, 740_100),
    _a("11.8", "Main Power Transformers", "STG output + CTG output", "MVA", 1.36, 520, 580,
       "Exponent > 1: diseconomic in scale."),
    _a("11.9", "Electrical Foundations", "Total plant gross power", "kW", 0.70, 689_800, 740_100),
    # --- 12 INSTRUMENTATION & CONTROL (Exhibit 3-38) -----------------------
    _a("12.1", "NGCC Control Equipment", "Auxiliary load", "kW", 0.13, 13_500, 44_000),
    _a("12.2", "Combustion Turbine Control Equipment", "Auxiliary load", "kW", 0.00, 13_500, 44_000),
    _a("12.3", "Steam Turbine Control Equipment", "Auxiliary load", "kW", 0.13, 13_500, 44_000),
    _a("12.4", "Other Major Component Control Equipment", "Auxiliary load", "kW", 0.16, 13_500, 44_000),
    _a("12.5", "Signal Processing Equipment", "Auxiliary load", "kW", 0.13, 13_500, 44_000),
    _a("12.6", "Control Boards, Panels & Racks", "Auxiliary load", "kW", 0.16, 13_500, 44_000),
    _a("12.7", "Distributed Control System Equipment", "Auxiliary load", "kW", 0.16, 13_500, 44_000),
    _a("12.8", "Instrument Wiring & Tubing", "Auxiliary load", "kW", 0.16, 13_500, 44_000),
    _a("12.9", "Other I&C Equipment", "Auxiliary load", "kW", 0.16, 13_500, 44_000),
    # --- 13 IMPROVEMENTS TO SITE (Exhibit 3-39) ----------------------------
    *[_a(n, d, "Total plant gross power", "kW", 0.46, 689_800, 740_100)
      for n, d in [("13.1", "Site Preparation"), ("13.2", "Site Improvements"),
                   ("13.3", "Site Facilities")]],
    # --- 14 BUILDINGS & STRUCTURES (Exhibit 3-40) --------------------------
    _a("14.1", "Combustion Turbine Area", "Gas turbine power", "kW", 0.00, 0, 0, "Fixed cost."),
    _a("14.3", "Steam Turbine Building", "Steam turbine gross power", "kW", 0.60, 212_500, 263_000),
    _a("14.4", "Administration Building", "Total plant gross power", "kW", 0.35, 689_800, 740_100),
    _a("14.5", "Circulation Water Pumphouse", "Circulating water flow rate", "gpm", 0.82, 135_700, 220_800),
    _a("14.6", "Water Treatment Buildings", "Raw water withdrawal", "gpm", 0.66, 2_900, 4_700),
    _a("14.7", "Machine Shop", "Total plant gross power", "kW", 0.36, 689_800, 740_100),
    _a("14.8", "Warehouse", "Total plant gross power", "kW", 0.34, 689_800, 740_100),
    _a("14.9", "Other Buildings & Structures", "Total plant gross power", "kW", 0.25, 689_800, 740_100),
    _a("14.10", "Waste Treating Building & Structures", "Total plant gross power", "kW", 0.34, 689_800, 740_100),
]

ACCOUNTS: dict[str, list[dict]] = {"PC": _PC, "IGCC": _IGCC, "NGCC": _NGCC}


# ============================================================================
# Look-up and scaling
# ============================================================================
def accounts_for(technology: str) -> list[dict]:
    """All account records for 'PC', 'IGCC' or 'NGCC'."""
    t = technology.strip().upper()
    if t not in ACCOUNTS:
        raise KeyError(f"technology must be one of {list(ACCOUNTS)}")
    return ACCOUNTS[t]


def _find(technology: str, account: str) -> dict:
    for rec in accounts_for(technology):
        if rec["account"] == account:
            return rec
    raise KeyError(f"Account {account!r} not found for {technology}. "
                   f"Available: {', '.join(r['account'] for r in accounts_for(technology))}")


def _exponent(rec: dict, category: int | None) -> float:
    exp = rec["exponent"]
    if exp is None:
        raise ValueError(
            f"Account {rec['account']} ({rec['name']}) has no scaling exponent. "
            f"{rec['note']}")
    if isinstance(exp, dict):
        if category is None:
            raise ValueError(
                f"Account {rec['account']} has category-specific exponents "
                f"{exp}; pass category=")
        if category not in exp:
            raise ValueError(
                f"Account {rec['account']} has no exponent for category {category} "
                f"(available: {sorted(exp)}). {rec['note']}")
        return exp[category]
    return float(exp)


@dataclass
class AccountResult:
    """Result of scaling one account."""
    account: str
    name: str
    parameter: str
    unit: str
    exponent: float
    reference_cost: float
    reference_parameter: float
    scaled_parameter: float
    scaled_cost: float
    in_range: bool
    note: str = ""

    def __float__(self) -> float:
        return self.scaled_cost


def scale_account(technology: str,
                  account: str,
                  reference_cost: float,
                  reference_parameter: float,
                  scaled_parameter: float,
                  category: int | None = None,
                  coefficient: float | None = None,
                  reference_tpc: float | None = None,
                  strict_range: bool = False) -> AccountResult:
    """
    Scale one plant account (QGESS Equation 3/5, or Equation 4 with a coefficient).

        SC = RC * (SP / RP) ** Exp                    [Equation 3 / 5]
        SC = (RC / RTPC) * C * SP ** Exp              [Equation 4, with coefficient]

    Parameters
    ----------
    technology : {'PC', 'IGCC', 'NGCC'}
    account : str
        Account number, e.g. "5A.1", "9.1", "12.7".
    reference_cost : float
        The reference plant's cost for this account, at ONE cost level. Run
        this once for equipment, once for material, once for labour; the sum
        is the scaled BEC.
    reference_parameter : float
        The reference plant's value of the scaling parameter.
    scaled_parameter : float
        Your plant's value of the same parameter.
    category : int, optional
        Required where NETL gives category-specific exponents (e.g. PC
        supercritical = 1 vs subcritical = 2).
    coefficient, reference_tpc : float, optional
        For the handful of IGCC accounts that use Equation 4.
    strict_range : bool
        Raise instead of warn when the scaled parameter falls outside NETL's
        stated range.

    Examples
    --------
    Reproduces the QGESS worked example, Account 5A.1 Selexol: reference cost
    $73,047k at 11,389 acfm, scaled to 12,068 acfm at exponent 0.79 gives
    $76,466k. (That account lives in the legacy category-7 tables; the same
    exponent appears here as IGCC 5.1.)

    >>> r = scale_account("IGCC", "5.1", 73_047, 11_389, 12_068)
    >>> round(r.scaled_cost)
    76466

    Cooling towers on an NGCC, duty rising from 1,500 to 2,000 MMBtu/h:

    >>> round(scale_account("NGCC", "9.1", 12_000_000, 1500, 2000).scaled_cost)
    14804254

    Combustion turbines do not scale at all:

    >>> round(scale_account("NGCC", "6.1", 100e6, 1, 2).scaled_cost)
    100000000
    """
    rec = _find(technology, account)
    exp = _exponent(rec, category)
    lo, hi = rec["valid"]
    in_range = (lo <= scaled_parameter <= hi) if (lo or hi) else True

    if not in_range:
        msg = (f"{technology} account {account}: scaled parameter "
               f"{scaled_parameter:g} {rec['unit']} is outside NETL's stated "
               f"range {lo:g}-{hi:g}. NETL expects validity over roughly the "
               f"median +/- 25%.")
        if strict_range:
            raise ValueError(msg)

    if coefficient is not None:
        if reference_tpc in (None, 0):
            raise ValueError("Equation 4 needs reference_tpc alongside coefficient")
        scaled = (reference_cost / reference_tpc) * coefficient * scaled_parameter ** exp
    else:
        if reference_parameter <= 0:
            raise ValueError("reference_parameter must be positive")
        scaled = reference_cost * (scaled_parameter / reference_parameter) ** exp

    return AccountResult(
        account=account, name=rec["name"], parameter=rec["parameter"],
        unit=rec["unit"], exponent=exp, reference_cost=reference_cost,
        reference_parameter=reference_parameter, scaled_parameter=scaled_parameter,
        scaled_cost=scaled, in_range=in_range, note=rec["note"],
    )


def scale_case(technology: str,
               reference: dict[str, tuple[float, float]],
               scaled_parameters: dict[str, float],
               category: int | None = None,
               strict_range: bool = False) -> tuple[float, list[AccountResult]]:
    """
    Scale a whole case, account by account.

    Parameters
    ----------
    reference : dict
        {account: (reference_cost, reference_parameter)}
    scaled_parameters : dict
        {account: scaled_parameter}

    Returns
    -------
    (total_scaled_cost, [AccountResult, ...])

    Examples
    --------
    >>> ref = {"9.1": (12e6, 1500), "9.2": (4e6, 150_000), "12.1": (3e6, 20_000)}
    >>> sp  = {"9.1": 2000,         "9.2": 200_000,        "12.1": 30_000}
    >>> total, rows = scale_case("NGCC", ref, sp)
    >>> len(rows)
    3
    """
    rows = []
    for acct, (rc, rp) in reference.items():
        sp = scaled_parameters.get(acct)
        if sp is None:
            raise KeyError(f"No scaled parameter supplied for account {acct}")
        rows.append(scale_account(technology, acct, rc, rp, sp,
                                  category=category, strict_range=strict_range))
    return sum(r.scaled_cost for r in rows), rows


def contingency_percent(reference_contingency: float, reference_bec: float) -> float:
    """
    QGESS Equation 2: carry the reference plant's contingency across as a
    percentage of BEC, then apply it to the scaled BEC.

        SCon = RCon / RBEC

    >>> round(contingency_percent(150e6, 1000e6), 3)
    0.15
    """
    if reference_bec <= 0:
        raise ValueError("reference_bec must be positive")
    return reference_contingency / reference_bec


def derive_exponent(cost_1: float, cost_2: float,
                    param_1: float, param_2: float) -> float:
    """
    Back out a scaling exponent from two vendor quotes (QGESS Equation 1).

        Exp = ln(RC1 / RC2) / ln(RP1 / RP2)

    This is how NETL built the tables in this module, and it is what you should
    do whenever you have two real quotes for the same item at different sizes —
    a derived exponent beats any published default.

    >>> round(derive_exponent(100_000, 60_000, 1000, 400), 3)
    0.557
    """
    if param_1 <= 0 or param_2 <= 0 or param_1 == param_2:
        raise ValueError("parameters must be positive and different")
    import math
    return math.log(cost_1 / cost_2) / math.log(param_1 / param_2)


def account_table(technology: str, category: int | None = None) -> str:
    """Printable table of all accounts and exponents for a technology."""
    rows = [f"NETL capital cost scaling exponents — {technology.upper()}"
            f"{f' (category {category})' if category else ''}",
            f"Source: DOE/NETL-2022/3340 Rev. 4a. Basis: {BASIS_YEAR} dollars.",
            ""]
    hdr = f"{'acct':<7}{'item':<48}{'scaling parameter':<38}{'unit':<10}{'n':>7}"
    rows += [hdr, "-" * len(hdr)]
    for rec in accounts_for(technology):
        exp = rec["exponent"]
        if exp is None:
            e = "  n/a"
        elif isinstance(exp, dict):
            e = f"{exp[category]:.2f}" if category in exp else "/".join(
                f"{v:.2f}" for v in exp.values())
        else:
            e = f"{exp:.2f}"
        flag = " *" if rec["note"] else ""
        rows.append(f"{rec['account']:<7}{rec['name'][:47]:<48}"
                    f"{rec['parameter'][:37]:<38}{rec['unit']:<10}{e:>7}{flag}")
    rows += ["", "* = carries a note; see ACCOUNTS[...]['note']"]
    return "\n".join(rows)
