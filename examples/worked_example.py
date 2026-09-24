#!/usr/bin/env python3
"""
Worked example: a green-hydrogen plant, costed three ways.
==========================================================

Runs the whole chain and — importantly — cross-validates the three levelised
cost methods against each other on the same plant, so you can see how much the
answer depends on the method rather than on the engineering.

    python examples/worked_example.py

Case: 100 t/day H2 electrolysis plant, US Gulf Coast, 2025 dollars.
The equipment list is illustrative — the point is the method, not the plant.
"""

import sys
import pathlib
import warnings

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")

import tea


def rule(title=""):
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


# =============================================================================
rule("STEP 0 — COST INDICES")
# =============================================================================
print(f"CEPCI 1998 (correlation basis) : {tea.cepci(1998):7.1f}")
print(f"CEPCI 2022                     : {tea.cepci(2022):7.1f}")
print(f"CEPCI 2024 Q1 (from monthlies) : {tea.cepci(2024, quarter=1):7.1f}")
print(f"CEPCI 2025 (provisional)       : {tea.cepci(2025):7.1f}")
print(f"escalation factor 1998 -> 2025 : {tea.index_ratio(1998, 2025):7.3f}")
print()
prov = tea.is_provisional(2025)
print("!! " + prov.split(".")[0] + ".")
print("   A ~27-year escalation is well outside the 5-year window cost")
print("   engineers recommend. Treat the capital numbers below as AACE Class 5.")


# =============================================================================
rule("STEP 1 — EQUIPMENT SCALING  (base cost, base size, scale factor)")
# =============================================================================
items = [
    tea.Equipment("K-101", "compressor_centrifugal_150psia", 12_000, material="ss304"),
    tea.Equipment("K-102", "blower_rotary", 3_000),
    tea.Equipment("E-101", "hx_shell_tube", 8_000, material="ss316"),
    tea.Equipment("E-102", "hx_air_cooler", 6_000),
    tea.Equipment("V-101", "separator", 8_000, quantity=2),        # KO drums
    tea.Equipment("P-101", "pump", 900, quantity=2, spare=1),
    tea.Equipment("TK-101", "tank_storage_cone_roof", 400_000),
    tea.Equipment("CT-101", "cooling_tower", 5_000),
]

print(f"{'tag':<8}{'equipment':<32}{'size':>12} {'unit':<18}{'n':>6}{'2025 US$':>14}")
print("-" * 92)
total_pec = 0.0
for it in items:
    rec = tea.EQUIPMENT[tea.resolve(it.kind)]
    c = it.cost(year=2025)
    total_pec += c
    print(f"{it.tag:<8}{tea.resolve(it.kind):<32}{it.size:>12,.0f} "
          f"{rec['size_unit']:<18}{rec['exponent']:>6.3f}{c:>14,.0f}")
print("-" * 92)
print(f"{'catalogue subtotal':<78}{total_pec:>14,.0f}")

# ---------------------------------------------------------------------------
# The electrolyser stacks are the heart of this plant and are NOT in the
# DOE/NETL 2002 catalogue -- no generic correlation covers them. This is the
# normal situation: a catalogue gets you the balance of plant, and the
# technology-defining equipment comes from a vendor quote or a published
# reference cost. Here we use DOE's own figure.
#
# Source: DOE Hydrogen Program Record 24005 (20 May 2024), "Clean Hydrogen
# Production Cost -- PEM Electrolyzer": baseline INSTALLED PEM electrolyser
# capital cost of ~$2,000/kW in 2022 dollars, from H2NEW Consortium modelling
# and vetted by domestic electrolyser manufacturers.
# https://www.hydrogen.energy.gov/docs/hydrogenprogramlibraries/pdfs/24005-clean-hydrogen-production-cost-pem-electrolyzer.pdf
# ---------------------------------------------------------------------------
STACK_INSTALLED_PER_KW_2022 = 2000.0
stack_installed = tea.escalate(STACK_INSTALLED_PER_KW_2022 * 210_000, 2022, 2025)
print(f"{'electrolyser stacks (DOE Record 24005, INSTALLED)':<78}"
      f"{stack_installed:>14,.0f}")
print(f"\n  ! That figure is already an INSTALLED cost, so it bypasses Step 2 and")
print( "    enters the cascade directly at BEC. Mixing a purchased cost and an")
print( "    installed cost in the same subtotal is a classic and expensive error.")

print("\nAudit trail for one item:")
print(tea.purchased_cost("hx_shell_tube", 8000, year=2025,
                         material="ss316", quiet=True).report())


# =============================================================================
rule("STEP 2 — INSTALLED COST  (DOE/NETL distributive factors, Loh App. A)")
# =============================================================================
inst = tea.installed_cost_loh(total_pec, "gas_lt400F_gt150psig", "heat exchanger")
print(f"{'bare equipment':<32}{inst['bare_equipment']:>16,.0f}")
print(f"{'setting labour':<32}{inst['setting_labor']:>16,.0f}")
print(f"{'bulk materials':<32}{inst['total_material']:>16,.0f}")
print(f"{'bulk + setting labour':<32}{inst['total_labor']:>16,.0f}")
print(f"{'INSTALLED (= BEC)':<32}{inst['installed_cost']:>16,.0f}")
print(f"{'installation factor':<32}{inst['installation_factor']:>16.2f}")

lang = tea.lang_factor_capital(total_pec, "fluid processing")
print(f"\nLang-factor cross-check (fluid processing, f = {lang['lang_factor']}):")
print(f"  fixed capital {lang['fixed_capital']:,.0f}  "
      f"vs NETL cascade TPC below — expect the same order, not the same number.")

bec = inst["installed_cost"] + stack_installed
print(f"\n{'BEC = installed BOP + installed stacks':<32}{bec:>16,.0f}")


# =============================================================================
rule("STEP 3 — CAPITAL CASCADE  (BEC -> EPCC -> TPC -> TOC -> TASC)")
# =============================================================================
model = tea.NETLCapitalCost(
    bec=bec,
    epc_fee_frac=0.175,
    process_contingency_frac=0.15,     # pilot-scale electrolysis data (AACE 16R-90)
    project_contingency_frac=0.20,     # budget-type estimate
    land_cost=100 * 3_000,             # 100 acres at NETL's $3,000/acre
    construction_years=3,
    basis="real",
)
cap = model.evaluate()
print(cap.report())
print(f"\nProcess contingency of {model.process_contingency_frac:.0%} chosen from "
      f"AACE 16R-90 'small pilot plant data' band "
      f"{tea.PROCESS_CONTINGENCY_AACE['small pilot plant data']}.")


# =============================================================================
rule("STEP 4 — OPERATING COSTS")
# =============================================================================
H2_TPD = 100.0
ONSTREAM = 0.90
h2_kg_yr = H2_TPD * 1000 * 365 * ONSTREAM

power_mw = 210.0   # ~52.5 kWh/kg H2 at 100 t/d
power_price = 45.0                                    # $/MWh
elec_cost = power_mw * 8760 * ONSTREAM * power_price
fixed_om = 0.04 * cap.toc                             # 4% of TOC/yr
stack_replacement = 0.02 * cap.toc
o2_credit = h2_kg_yr * 8 / 1000 * 15.0                # 8 kg O2/kg H2 at $15/t

var_om = elec_cost + stack_replacement
print(f"{'H2 production':<34}{h2_kg_yr:>16,.0f} kg/yr  ({ONSTREAM:.0%} on-stream)")
print(f"{'electricity':<34}{elec_cost:>16,.0f} $/yr")
print(f"{'stack replacement reserve':<34}{stack_replacement:>16,.0f} $/yr")
print(f"{'fixed O&M':<34}{fixed_om:>16,.0f} $/yr")
print(f"{'oxygen byproduct credit':<34}{o2_credit:>16,.0f} $/yr")


# =============================================================================
rule("STEP 5 — LEVELISED COST, THREE WAYS")
# =============================================================================

# --- 5a. SIMPLE: no interest rate at all -------------------------------------
print("\n(a) SIMPLE — capital straight-lined, NO interest rate\n")
simple = tea.simple_levelized_cost(
    total_capital=cap.toc,
    annual_fixed_opex=fixed_om,
    annual_variable_opex=var_om,
    annual_production=h2_kg_yr,
    plant_life_years=30,
    byproduct_revenue=o2_credit,
)
for k in ("capital_component", "fixed_component", "variable_component",
          "byproduct_component", "levelized_cost"):
    print(f"    {k:<26}{simple[k]:>10.3f}  $/kg H2")

# --- 5b. ANNUITY: interest rate over the plant years -------------------------
print("\n(b) ANNUITY — FCR embeds cost of capital + depreciation tax shield\n")
fin = tea.NETL_FINANCE_IOU["real"]
aw = tea.atwacc(fin["debt_frac"], fin["cost_of_debt"],
                fin["return_on_equity"], tea.NETL_GLOBAL_ASSUMPTIONS["effective_tax_rate"])
f = tea.fcr(aw, 30, tea.NETL_GLOBAL_ASSUMPTIONS["effective_tax_rate"], 20)
print(f"    ATWACC (real)             {aw:>10.4f}")
print(f"    CRF  (30 yr)              {tea.crf(aw, 30):>10.4f}")
print(f"    FCR  (MACRS 20-yr)        {f:>10.4f}")
print()
lc = tea.lcox(cap.tasc, fixed_om, var_om, h2_kg_yr, f,
              annual_byproduct_revenue=o2_credit, unit="$/kg H2")
print("    " + lc.report().replace("\n", "\n    "))

# --- 5c. DCF: NPV = 0 --------------------------------------------------------
print("\n(c) DCF — full after-tax cash flow solved for NPV = 0\n")
dcf = tea.CashFlowModel(
    total_capital=cap.toc,
    annual_production=h2_kg_yr,
    annual_fixed_opex=fixed_om,
    annual_variable_opex=var_om,
    annual_byproduct_revenue=o2_credit,
    plant_life_years=30,
    construction_years=3,
    discount_rate=aw,                  # same ATWACC as the FCR above
    tax_rate=tea.NETL_GLOBAL_ASSUMPTIONS["effective_tax_rate"],
    depreciation_years=20,
    working_capital=0.05 * cap.toc,
)
msp = dcf.minimum_selling_price()
res = dcf.run(msp)
print(f"    MSP (NPV = 0)             {msp:>10.3f}  $/kg H2")
print(f"    check: NPV at MSP         {res.npv:>10.2f}  $")
print(f"    check: IRR at MSP         {res.irr:>10.4%}  (= discount rate)")
if res.payback_year is not None:
    print(f"    discounted payback        year {res.payback_year:.1f}")
else:
    print("    discounted payback        n/a — priced exactly at break-even, so")
    print("                              the cumulative DCF only reaches zero at")
    print("                              end of life. Re-run at a market price")
    print("                              above the MSP to get a payback year.")

print("\n" + res.table(max_rows=14))


# =============================================================================
rule("CROSS-VALIDATION — how much does the METHOD change the answer?")
# =============================================================================
print(f"{'(a) simple, no interest':<44}{simple['levelized_cost']:>9.3f}  $/kg")
print(f"{'(b) annuity, FCR x TASC':<44}{lc.levelized_cost:>9.3f}  $/kg")
print(f"{'(c) DCF, NPV = 0 on TOC':<44}{msp:>9.3f}  $/kg")
print()
print(f"(a) is {(1 - simple['levelized_cost'] / msp) * 100:.0f}% below (c): that gap is "
      f"the entire cost of capital.")
print(f"(b) sits above (c) mainly because it charges FCR against TASC "
      f"(x{cap.tasc_toc_factor:.3f} on TOC)")
print("    while (c) charges the ATWACC against TOC and models construction")
print("    financing through the discounting itself. Both are defensible; the")
print("    error is mixing them — e.g. applying an FCR to a TOC, which would")
print(f"    understate the capital charge by {(cap.tasc_toc_factor - 1) * 100:.0f}%.")


# =============================================================================
rule("SENSITIVITY — which assumptions actually drive the answer?")
# =============================================================================
print(f"{'parameter':<28}{'-30%':>11}{'-15%':>11}{'base':>11}{'+15%':>11}{'+30%':>11}")
print("-" * 84)
for param, label in [("total_capital", "capital"),
                     ("annual_variable_opex", "electricity + variable"),
                     ("annual_fixed_opex", "fixed O&M"),
                     ("annual_production", "output / on-stream"),
                     ("discount_rate", "discount rate")]:
    row = dcf.sensitivity(param, [0.7, 0.85, 1.0, 1.15, 1.3])
    print(f"{label:<28}" + "".join(f"{v:>11.3f}" for _, v in row))
print("\nRead the spread, not the level: the widest row is what your next hour")
print("of engineering effort should be spent on.")

rule()
print("Every number above traces to a public source. See README.md for the")
print("bibliography and for the limitations to state in any report.")
