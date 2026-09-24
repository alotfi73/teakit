#!/usr/bin/env python3
"""
Example 2: scaling a whole plant, account by account.
=====================================================

    python examples/plant_scaling_example.py

Two things this shows that the equipment-list route cannot:

1. **How a real published case gets rescaled.** You have a NETL baseline at one
   capacity and need it at another. Scaling 60-odd accounts against their own
   process parameters, using exponents NETL regressed from vendor quotes, is far
   more defensible than re-costing a bottom-up equipment list.

2. **Why a single plant-wide six-tenths factor is wrong even when the total
   looks right.** The exponents span 0.00 to 1.40. A blanket 0.6 moves fixed
   costs that shouldn't move and holds back diseconomic ones that should.

Case: an NGCC with post-combustion capture, scaled from a 650 MW reference to
a 900 MW plant of the same design. Reference costs below are illustrative
placeholders — replace them with the account-level costs from the actual
Fossil Energy Baseline Revision 4a tables.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tea


def rule(t=""):
    print("\n" + "=" * 96)
    if t:
        print(t)
        print("=" * 96)


SCALE = 900.0 / 650.0        # capacity ratio

# ---------------------------------------------------------------------------
# Reference case: {account: (reference cost $, reference parameter value)}
# and the corresponding parameter values for the plant of interest.
#
# Note that each account has its OWN parameter. That is the whole point: the
# stack scales on gas flow, the pumps on circulating water flow, the controls
# on auxiliary load. Ratios differ between them, so a single capacity ratio
# would be wrong even before the exponents are applied.
# ---------------------------------------------------------------------------
REFERENCE = {
    # acct    (ref cost $,   ref parameter)
    "3.1":   (18_500_000,      1_339_000),    # feedwater flow, lb/h
    "3.2":   ( 9_200_000,          4_700),    # raw water withdrawal, gpm
    "3.4":   ( 6_100_000,          4_700),
    "3.6":   (32_000_000,        180_000),    # natural gas feed rate, lb/h
    "3.7":   ( 7_400_000,          1_670),    # process water discharge, gpm
    "5.1":   (185_000_000,       617_000),    # CO2 product flow, lb/h
    "5.4":   (48_000_000,         46_700),    # CO2 compressor load, kW
    "5.5":   ( 6_800_000,             88),    # CO2 aftercooler duty, MMBtu/h
    "6.1":   (162_000_000,       180_000),    # natural gas feed rate, lb/h
    "6.3":   (24_000_000,        180_000),
    "7.1":   (58_000_000,          2_300),    # HRSG duty, MMBtu/h
    "7.2":   (11_000_000,          2_300),
    "7.4":   ( 5_600_000,      2_365_000),    # gas flow to stack, acfm
    "8.1":   (74_000_000,        263_000),    # steam turbine gross power, kW
    "8.3":   (21_000_000,          1_340),    # condenser duty, MMBtu/h
    "9.1":   (13_500_000,          2_200),    # cooling tower duty, MMBtu/h
    "9.2":   ( 8_900_000,        220_800),    # circulating water flow, gpm
    "9.4":   (12_300_000,        220_800),
    "11.1":  (14_000_000,        740_100),    # total plant gross power, kW
    "11.3":  ( 9_600_000,         44_000),    # auxiliary load, kW
    "11.8":  (17_500_000,            580),    # STG + CTG output, MVA
    "12.1":  ( 8_200_000,         44_000),    # auxiliary load, kW
    "12.7":  ( 6_400_000,         44_000),
    "13.1":  ( 9_100_000,        740_100),    # total plant gross power, kW
    "14.3":  (11_800_000,        263_000),    # steam turbine gross power, kW
    "14.8":  ( 3_200_000,        740_100),
}

# Parameter values for the plant of interest. Most rise with capacity; the
# combustion turbine accounts are pinned because you would buy a second frame,
# not a bigger one, and the gas pipeline is site-specific and additive.
SCALED = {
    "3.1": 1_339_000 * SCALE, "3.2": 4_700 * SCALE, "3.4": 4_700 * SCALE,
    "3.6": 180_000 * SCALE,   "3.7": 1_670 * SCALE,
    "5.1": 617_000 * SCALE,   "5.4": 46_700 * SCALE, "5.5": 88 * SCALE,
    "6.1": 180_000 * SCALE,   "6.3": 180_000 * SCALE,
    "7.1": 2_300 * SCALE,     "7.2": 2_300 * SCALE,  "7.4": 2_365_000 * SCALE,
    "8.1": 263_000 * SCALE,   "8.3": 1_340 * SCALE,
    "9.1": 2_200 * SCALE,     "9.2": 220_800 * SCALE, "9.4": 220_800 * SCALE,
    "11.1": 740_100 * SCALE,  "11.3": 44_000 * SCALE, "11.8": 580 * SCALE,
    "12.1": 44_000 * SCALE,   "12.7": 44_000 * SCALE,
    "13.1": 740_100 * SCALE,  "14.3": 263_000 * SCALE, "14.8": 740_100 * SCALE,
}


rule(f"NGCC WITH CAPTURE — SCALING 650 MW REFERENCE TO 900 MW  (x{SCALE:.3f})")
print(f"Exponents: {tea.plant_sections.BASIS_NOTE}")

total, rows = tea.scale_case("NGCC", REFERENCE, SCALED)
ref_total = sum(c for c, _ in REFERENCE.values())

hdr = (f"{'acct':<7}{'item':<40}{'n':>6}{'ref cost $':>15}"
       f"{'scaled $':>15}{'ratio':>8}  range")
print("\n" + hdr)
print("-" * len(hdr))
for r in sorted(rows, key=lambda x: [int(p) for p in x.account.split(".")]):
    ratio = r.scaled_cost / r.reference_cost
    flag = "" if r.in_range else "  OUT OF RANGE"
    print(f"{r.account:<7}{r.name[:39]:<40}{r.exponent:>6.2f}"
          f"{r.reference_cost:>15,.0f}{r.scaled_cost:>15,.0f}{ratio:>8.3f}{flag}")
print("-" * len(hdr))
print(f"{'TOTAL':<53}{ref_total:>15,.0f}{total:>15,.0f}"
      f"{total / ref_total:>8.3f}")

# ---------------------------------------------------------------------------
rule("WHAT A BLANKET SIX-TENTHS FACTOR WOULD HAVE DONE")
# ---------------------------------------------------------------------------
naive = ref_total * SCALE ** 0.6
print(f"{'account-by-account (NETL exponents)':<52}{total:>18,.0f}")
print(f"{'single plant-wide n = 0.6':<52}{naive:>18,.0f}")
print(f"{'difference':<52}{naive - total:>18,.0f}"
      f"   ({(naive / total - 1) * 100:+.1f}%)")
print(f"""
The totals are within a few percent — which is exactly the trap. Look at where
the money moved instead:""")

worst = sorted(rows, key=lambda r: abs(r.exponent - 0.6), reverse=True)[:6]
print(f"\n{'acct':<7}{'item':<40}{'n':>6}{'NETL scaled $':>16}{'at n=0.6 $':>16}{'error':>12}")
print("-" * 97)
for r in worst:
    n06 = r.reference_cost * SCALE ** 0.6
    print(f"{r.account:<7}{r.name[:39]:<40}{r.exponent:>6.2f}"
          f"{r.scaled_cost:>16,.0f}{n06:>16,.0f}"
          f"{(n06 / r.scaled_cost - 1) * 100:>11.1f}%")
print("""
The combustion turbine (n = 0.00) is a fixed cost for a given frame — a blanket
0.6 inflates it by 20%, which on a $162M account is $26M of money that does not
exist. Meanwhile the main power transformers (n = 1.36) and HRSG accessories
(n = 1.40) are genuinely diseconomic and get under-costed. The errors happen to
partly cancel in the total; they do not cancel in the cost breakdown, and the
cost breakdown is what your sensitivity analysis and your R&D targeting run on.""")

# ---------------------------------------------------------------------------
rule("DERIVING YOUR OWN EXPONENT FROM TWO QUOTES (QGESS Equation 1)")
# ---------------------------------------------------------------------------
print("""A published exponent is a fallback. If you have two real vendor quotes
for the same item at different sizes, derive the exponent from them — that is
exactly how NETL built the tables above.

    Exp = ln(RC1 / RC2) / ln(RP1 / RP2)
""")
for c1, c2, p1, p2, what in [
    (2_400_000, 1_500_000, 5_000, 2_500, "compressor, 5,000 vs 2,500 acfm"),
    (860_000, 610_000, 12_000, 7_000, "exchanger, 12,000 vs 7,000 ft2"),
    (18_500_000, 17_900_000, 900_000, 650_000, "turbine, 900 vs 650 MW"),
]:
    n = tea.derive_exponent(c1, c2, p1, p2)
    verdict = ("fixed cost — do not scale" if n < 0.15 else
               "diseconomic — check it" if n > 1.0 else "normal economy of scale")
    print(f"  {what:<38} n = {n:5.3f}   {verdict}")

# ---------------------------------------------------------------------------
rule("EXPONENT DISTRIBUTION ACROSS ALL THREE TECHNOLOGIES")
# ---------------------------------------------------------------------------
bands = {"0.00 (fixed)": 0, "0.01-0.30": 0, "0.31-0.50": 0,
         "0.51-0.70": 0, "0.71-0.90": 0, "0.91-1.00": 0, ">1.00": 0}
for tech in ("PC", "IGCC", "NGCC"):
    for rec in tea.accounts_for(tech):
        e = rec["exponent"]
        vals = list(e.values()) if isinstance(e, dict) else ([] if e is None else [e])
        for v in vals:
            if v == 0:              bands["0.00 (fixed)"] += 1
            elif v <= 0.30:         bands["0.01-0.30"] += 1
            elif v <= 0.50:         bands["0.31-0.50"] += 1
            elif v <= 0.70:         bands["0.51-0.70"] += 1
            elif v <= 0.90:         bands["0.71-0.90"] += 1
            elif v <= 1.00:         bands["0.91-1.00"] += 1
            else:                   bands[">1.00"] += 1
total_n = sum(bands.values())
for band, n in bands.items():
    bar = "#" * round(48 * n / total_n)
    print(f"  {band:<14}{n:>4}  {bar}")
print(f"\n  {total_n} exponents across {len(tea.accounts_for('PC'))} PC, "
      f"{len(tea.accounts_for('IGCC'))} IGCC and {len(tea.accounts_for('NGCC'))} "
      f"NGCC accounts.")
print("""
Only about a third sit in the 0.51-0.70 band that the six-tenths rule assumes.
A fifth are fixed costs. That distribution is the argument for account-level
scaling in one picture.""")

rule()
print("Reference costs above are placeholders. Replace them with the actual")
print("account tables from Fossil Energy Baseline Revision 4a before quoting")
print("any number from this. See README.md §1.1.")
