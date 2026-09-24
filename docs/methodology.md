# Methodology

What teakit computes, in the order it computes it, and where each step comes
from. This is the document to read before you defend a number to a reviewer.

---

## 1. Purchased equipment cost

```
C = C_base × (S / S_base)^n × (I_target / I_1998) × F_M × F_L
```

| term | meaning | source |
|---|---|---|
| `C_base`, `S_base`, `n` | reference cost, reference size, scale factor | regressed from DOE/NETL-2002/1169 Appendix B |
| `I` | Chemical Engineering Plant Cost Index | *Chemical Engineering* |
| `F_M` | material factor | DOE/NETL-2002/1169 Table 7 |
| `F_L` | location factor | user; USGC = 1.00 |

The six-tenths rule (`n = 0.6`) is a fallback, not a default. Fitted exponents
across the catalogue run from about 0.17 to 1.39, and using 0.6 where a fitted
value exists throws away the data.

**Past `valid_max`, economy of scale stops.** Beyond the largest unit a shop can
fabricate, capacity comes from parallel trains at roughly constant unit cost.
teakit splits the duty rather than extrapolating the power law, because
extrapolating it is one of the commonest ways to under-estimate a large plant.

**Extrapolation below `valid_min` raises** unless you pass
`allow_extrapolation=True`, and is recorded in the result's notes when you do.

## 2. Purchased → installed

Three routes, in increasing rigour:

| method | what it is | when |
|---|---|---|
| user factor | one multiplier you supply | you have a house factor |
| Lang factor | 4.74 fluid / 3.63 mixed / 3.10 solid, on total purchased cost | order-of-magnitude |
| distributive factors | per-item bulk material and labour by service and equipment type, DOE/NETL-2002/1169 Tables 2–6 | the default |

The distributive method builds foundations, structural steel, piping, electrical,
instrumentation, insulation and paint separately, each with its own material and
labour factor, plus setting labour by equipment type. It reproduces the Appendix A
worked example exactly: $62,000 bare becomes $150,245 installed.

**An already-installed cost must not go through this step.** Vendor and
programme-record prices are frequently installed costs; put them in with
`cost_is_installed=True` and they enter the cascade at BEC. Mixing a purchased
cost and an installed cost in one subtotal is a classic and expensive error.

## 3. The capital ladder

Verbatim from NETL-PUB-22580 §2.1:

```
BEC    Bare Erected Cost — process equipment, on-site support facilities,
       and the direct and indirect labour to install them.
EPCC   = BEC + EPC contractor services (detailed design, permitting,
       project and construction management). NETL: 15–20% of BEC.
TPC    = EPCC + process contingency + project contingency.
TOC    = TPC + owner's costs. An overnight cost: no escalation, no
       construction financing.
TASC   = all capital expenditure as incurred across the build, including
       escalation and interest during construction. Mixed current-year
       dollars.
```

**BEC, EPCC, TPC and TOC are overnight costs in base-year dollars. TASC is not.**
Always ask which one a published number is.

### Contingency

Two contingencies, covering different ignorance, and they are not interchangeable.

*Process contingency* covers technology immaturity, as a fraction of the
associated process capital. AACE 16R-90 bands:

| technology status | process contingency |
|---|---|
| new concept, limited data | 40%+ |
| concept with bench-scale data | 30–70% |
| small pilot plant data | 20–35% |
| full-sized modules operated | 5–20% |
| commercial | 0–10% |

*Project contingency* covers estimate immaturity: 15–30% of BEC + EPC fee +
process contingency for a budget-type (Class 4/5) estimate.

### TASC/TOC

```
TASC/TOC = Escalation + Cost of Funding
Escalation      = Σ (1+i)^(n-1+offset) · %Capital_n
Cost of Funding = Σ WACC · (y-n+1) · (1+i)^(n-1+offset) · %Capital_n
```

The cost-of-funding term is simple interest on the running balance: money
committed in year *n* sits in the project for *(y−n+1)* years before the plant
runs. NETL uses the **pre-tax WACC** here, not the ATWACC, because nothing is
earning revenue during construction.

| build | real | nominal |
|---|---|---|
| 3 years | 1.093 | 1.171 (1.242 at NETL's offset of 2) |
| 5 years | 1.154 | 1.297 |

## 4. Operating cost

**Variable** — feedstock, catalysts and chemicals, utilities, waste disposal,
royalties. Quoted at full rate and scaled by the capacity factor, except lines
pinned with `scales_with_rate=False` (a take-or-pay contract, a calendar-based
catalyst change).

**Fixed** — labour and supervision, maintenance, operating supplies, laboratory,
property tax and insurance, plant overhead, general and administrative.

**Neither** — depreciation, interest, return on capital, working capital. There
is no field for them in the operating cost model. They belong to the costing
method, and putting them in both places is the commonest error in a first TEA.

Three conventions, each internally coherent. Pick one and name it:

| | maintenance | tax + insurance | overhead |
|---|---|---|---|
| NREL | 3% of installed equipment | 0.7% of FCI | 90% of labour |
| Peters & Timmerhaus | 5% of FCI | 2% of FCI | 60% of labour, + lab 15%, + G&A 20% |
| NETL | 2% of TPC | 2% of TPC | 30% of labour, + admin 25% |

`turton_com()` gives an independent one-line check:

```
COM_d = 0.180·FCI + 2.73·C_OL + 1.23·(C_UT + C_WT + C_RM)
```

Note `COM_d` — *without* depreciation. Use it against a DCF; the `COM` variant
adds 0.10·FCI and would charge for capital twice.

## 5. Products and allocation

| method | rule | fails when |
|---|---|---|
| byproduct credit | subtract secondary revenue from total cost | credits approach total cost — the primary becomes a small difference of large numbers |
| market value | split cost in proportion to revenue | the primary price is what you are solving for (teakit uses a stated reference price) |
| mass | split by tonnes | products differ greatly in value per tonne |
| energy | split by heating value | non-fuel products |

A levelised cost reported without naming the allocation method is not
reproducible.

## 6. Levelised cost — three methods

### `simple`

```
LC = (TOC / life + annual O&M − byproduct revenue) / annual production
```

No cost of capital at all. Understates by 30–50% at typical discount rates.
Screening only.

### `fcr` — NETL

```
CRF = i(1+i)^n / ((1+i)^n − 1)
FCR = CRF · (1 − t·PV_depreciation) / (1 − t)
COE = (FCR·TASC + OC_fix + CF·OC_var) / (CF · annual production)
```

The FCR converts a capital sum into the annual revenue needed to service it
after tax. **The interest rate inside the FCR must be the ATWACC**, and the
capital basis must be **TASC, not TOC** — applying an FCR to a TOC understates
the capital charge by the TASC/TOC factor.

### `dcf` — NREL / H2A

Build the full after-tax cash flow year by year and solve for the product price
that puts NPV at zero. That price is the minimum selling price.

```
construction years        capital spent per the spend profile
start-up year             reduced revenue, elevated unit cost
operating years           revenue − opex − depreciation → taxable income
                          net cash flow = revenue − opex − tax − principal
final year                working capital, land and salvage recovered
```

MACRS depreciation from IRS Pub. 946. Tax losses carried forward by default
rather than booked as a credit. By construction, IRR at the MSP equals the
discount rate — teakit tests that.

### Why they disagree, and what to do about it

`method_comparison()` runs all three. The spread is the cost of capital and how
each method charges for it. Picking one is fine; **mixing them is not** — an FCR
applied to a TOC, or depreciation inside OPEX *and* a discount rate on top.

## 7. Real versus nominal

Keep one basis throughout.

| | discount rate | escalation | O&M growth |
|---|---|---|---|
| real | real ATWACC (NETL 4.73%) | 0% | 0% |
| nominal | nominal ATWACC (NETL 6.54%) | 3% | 3% |

```
(1 + nominal) = (1 + real)(1 + inflation)
```

Under 0% real escalation the real LCOE equals the base-year COE, which is why
NETL's baselines report them interchangeably.

## 8. Estimate class

| class | definition | accuracy |
|---|---|---|
| 5 | 0–2% | −25% / +50% |
| 4 | 1–15% | −15% / +30% |
| 3 | 10–40% | −10% / +20% |
| 2 | 30–70% | −5% / +15% |
| 1 | 50–100% | −3% / +10% |

Correlation-based capital escalated from a 1998 data set is **Class 5–4**, and
that band is before the escalation error. Report the range, not the point.
