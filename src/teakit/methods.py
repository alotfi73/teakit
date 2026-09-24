"""
teakit.methods — What every option means, and how the selected one calculates.
==============================================================================

Three things live here, and they live *here* rather than in the JavaScript so
that the interface, the HTML report, the Markdown report and the Excel workbook
all say the same thing:

:data:`OPTION_HELP`
    One short sentence per dropdown option, keyed by field. The interface hangs
    these on the ``<option>`` elements as tooltips and prints the selected one
    underneath the control, so a user meets an explanation *before* choosing
    rather than after being surprised by the answer.

:data:`GUIDE`
    The long-form manual behind the application's Info section: what each step
    is for, what the numbers mean, where they come from, and the mistakes this
    kind of estimate invites.

:func:`explain`
    The method appendix. Given a project and its result it returns the
    equations actually used, the symbols with the run's own values substituted,
    and the arithmetic step by step — so a reviewer can reproduce the number
    with a calculator. This is what goes at the end of the report and onto the
    workbook's method sheet.

    >>> import teakit
    >>> p = teakit.demo()
    >>> secs = explain(p, p.run())
    >>> secs[0]["title"]
    'Purchased equipment cost'
    >>> any(s["id"] == "costing" for s in secs)
    True
"""

from __future__ import annotations

from . import equipment_data as _eqdata

__all__ = ["OPTION_HELP", "GUIDE", "explain", "help_for", "option_help_flat"]


# ===========================================================================
# 1. Per-option help — the dropdown tooltips
# ===========================================================================
#: ``field -> option value -> one-sentence explanation``.
#:
#: Keys match the ``data-help`` attribute on the corresponding control in
#: ``static/index.html``. Anything absent simply gets no tooltip, so adding an
#: option never breaks the interface — it only leaves it unexplained.
OPTION_HELP: dict[str, dict[str, str]] = {

    # -- project ---------------------------------------------------------
    "method": {
        "dcf": "builds a full after-tax cash flow and solves for the price at "
               "which the project's NPV is exactly zero. The most rigorous of "
               "the three, and the one to quote in a report.",
        "fcr": "multiplies a fixed charge rate by the as-spent capital, the "
               "NETL convention for power and fuels studies. Fast, "
               "reproducible, and comparable with published NETL numbers.",
        "crf": "annualises the capital with the capital recovery factor and "
               "divides (annualised capital + operating cost - byproduct "
               "revenue) by production. The textbook annuity form, and the "
               "NREL ATB convention. It charges the cost of capital but no "
               "tax, so it sits between 'simple' and the cash flow; quote it "
               "as a pre-tax, constant-dollar levelised cost.",
        "simple": "recovers capital in equal straight-line slices and charges "
                  "nothing for the cost of capital. Screening only — it "
                  "understates a real project by roughly 30-50%.",
    },
    "basis": {
        "real": "everything in constant dollars of the dollar-year, with a "
                "real discount rate and no escalation. The usual choice for a "
                "study that will be compared with other studies.",
        "nominal": "everything in the dollars of the year it is spent, with "
                   "escalation and a nominal discount rate. Use it when the "
                   "audience is a financier rather than an engineer.",
    },
    "capital_basis": {
        "real": "no escalation during construction, so TASC exceeds TOC only "
                "by the cost of carrying the spend.",
        "nominal": "adds 3%/yr escalation over the build, which raises the "
                   "TASC/TOC factor and therefore the FCR-method answer.",
    },

    # -- capital ---------------------------------------------------------
    "installation_method": {
        "loh": "builds foundations, steel, piping, electrical, instruments, "
               "insulation and paint from the DOE/NETL factors, with one "
               "service and one setting-labour class standing for the whole "
               "equipment list. The default, and what teakit has always done.",
        "type": "the same DOE/NETL factors, but resolved for each item from "
                "its equipment type, so a conveyor is not installed at a "
                "fired heater's factor. Bulk material and setting labour are "
                "not the same fraction of a pump's cost as of a crusher's, "
                "and this is the only method that says so. Every type's "
                "factor is listed and can be overridden, and so can any "
                "single item's.",
        "lang": "one whole-plant multiplier on total purchased cost, by plant "
                "type. An order-of-magnitude device; it cannot distinguish a "
                "pump from a tower.",
        "factor": "a single multiplier you supply. Use it when your company "
                  "has a house factor it wants applied — and say so in the "
                  "report, because nobody else can reproduce it.",
    },
    "loh_service": {
        "liquid_slurry_lt150psig":
            "liquids and slurries below 150 psig. Piping-heavy but low "
            "pressure — the lightest of the liquid bulk-material sets.",
        "liquid_slurry_gt150psig":
            "liquids and slurries above 150 psig. Heavier pipe schedules and "
            "more insulation than the low-pressure case.",
        "gas_lt400F_lt150psig":
            "gas service, cool and low pressure. The lightest gas case.",
        "gas_lt400F_gt150psig":
            "gas service, cool but above 150 psig — more piping and steel.",
        "gas_gt400F_lt150psig":
            "hot gas below 150 psig. Insulation dominates the increase.",
        "gas_gt400F_gt150psig":
            "hot gas above 150 psig — the heaviest gas case, and the usual "
            "choice for a reforming or synthesis section.",
        "solids_lt400F":
            "solids handling below 400 degF. Less piping, more structure and "
            "buildings than a fluid service.",
        "solids_gt400F":
            "hot solids handling — as above, with insulation.",
        "solids_gas_lt400F_lt150psig":
            "mixed solids and gas, cool and low pressure. Use it when the "
            "section genuinely handles both.",
        "solids_gas_gt400F_gt150psig":
            "mixed solids and gas, hot and above 150 psig — gasification and "
            "combustion sections.",
    },

    # "loh_setting" is generated from the factor table by _fill_setting_help().

    "lang_type": {
        "fluid processing": "4.74 x total purchased cost. Fluid-processing "
                            "plant — the most piping-intensive, so the "
                            "largest multiplier.",
        "solid-fluid processing": "3.63 x total purchased cost. A mixed "
                                  "solid/fluid plant.",
        "solid processing": "3.10 x total purchased cost. Solids-processing "
                            "plant — the least piping.",
    },

    # -- operating -------------------------------------------------------
    "convention": {
        "NREL": "maintenance 3% of installed cost, insurance and tax 0.7% of "
                "FCI, overhead 90% of labour. The biofuels-study convention "
                "(NREL/TP-5100-47764).",
        "Peters & Timmerhaus": "the textbook factored set — more lines and a "
                               "higher total. Watch the overlap between plant "
                               "overhead and the payroll burden you set on the "
                               "labour model.",
        "NETL": "maintenance and insurance/tax each 2% of TPC, overhead 30% of "
                "labour, plus 25% administrative labour. The power-plant "
                "convention (NETL-PUB-22580).",
    },
    "labor_mode": {
        "rule": "size the payroll from operators per shift and a coverage "
                "factor. Right for a screening estimate.",
        "plan": "name every role and its headcount. Right once you have an "
                "organisation chart, and the only way to show shift and "
                "day-staff separately.",
    },

    # -- products --------------------------------------------------------
    "allocation": {
        "byproduct credit": "secondary revenue is subtracted from total cost "
                            "before dividing by primary production. Standard "
                            "for an incidental output — but when credits "
                            "approach total cost, your answer has quietly "
                            "become a byproduct price forecast.",
        "market value": "cost is split between products in proportion to "
                        "revenue. Needs a reference price for the primary "
                        "product, which makes the result mildly circular; "
                        "teakit reports the price it used.",
        "mass": "cost is split by tonnes out. Defensible only when a tonne of "
                "each product is worth roughly the same.",
        "energy": "cost is split by heating value. The convention in fuels "
                  "work and required by several fuel regulations; set the "
                  "energy content on every product.",
    },

    # -- finance ---------------------------------------------------------
    "depreciation_years": {
        "3": "MACRS 3-year — short-lived assets, rarely a whole plant.",
        "5": "MACRS 5-year — the usual class for renewable-energy property.",
        "7": "MACRS 7-year — general manufacturing equipment; the common "
             "choice for a chemical plant.",
        "10": "MACRS 10-year — certain petrochemical and biomass assets.",
        "15": "MACRS 15-year — pipelines and some utility property.",
        "20": "MACRS 20-year — long-lived utility plant; NETL's convention.",
    },

    # -- equipment -------------------------------------------------------
    # -- operating time --------------------------------------------------
    # These two are multiplied together against every hourly rate, and the
    # commonest error in a TEA is to express the same derate in both.
    "operating_time": {
        "operating_hours": "hours the plant runs in a year. Divided by the "
                           "8,760 hours in a calendar year this is the stream "
                           "factor, or on-stream factor: 8,000 h/yr is 91.3%. "
                           "It is the time the plant is available.",
        "capacity_factor": "output while it is running, as a fraction of "
                           "nameplate. Leave it at 100% when the hours above "
                           "already carry the derate and the annual production "
                           "you entered is the actual figure; use it when your "
                           "production is nameplate and the plant runs below "
                           "it. Every hourly rate is multiplied by hours AND "
                           "by this, so putting the same derate in both counts "
                           "it twice.",
        "stream_factor": "operating hours as a fraction of the 8,760-hour "
                         "calendar year. Derived, not entered - it is the "
                         "hours restated.",
        "full_load_hours": "operating hours x capacity factor: the hours the "
                           "plant would run at full nameplate rate to make the "
                           "same output. This is the number that actually "
                           "multiplies an hourly rate.",
    },

    "stream_basis": {
        "hour": "the rate is an hourly draw and is multiplied by the operating "
                "hours on this panel. This is the normal case for a utility: "
                "quote the design figure at full production and let the "
                "capacity factor scale it down.",
        "year": "the rate is already an annual total, so the operating hours "
                "are not applied. Use it for a lump sum - set the rate to 1 "
                "and the price to the whole annual figure - or for a charge "
                "on a calendar schedule, such as a catalyst replaced every "
                "three years whether or not the plant ran hard.",
    },

    "product_basis": {
        "hour": "the output figure is per operating hour and is multiplied by "
                "the operating hours on the Operating cost panel, then by the "
                "capacity factor. Enter it this way when the flowsheet gives "
                "you a design rate - it keeps the product on the same footing "
                "as the feed, so changing the operating time moves both "
                "instead of leaving one behind.",
        "year": "the figure is already a year's output at full rate. The "
                "operating hours are not applied to it; the capacity factor "
                "still is, unless the line is pinned.",
    },

    "exponent_basis": {
        "fitted": "the median of the DOE/NETL-2002/1169 Appendix B "
                  "correlations of this equipment type, regressed from real "
                  "vendor quotes. Correlations the report itself flags as "
                  "unreliable are left out. This is the best evidence the "
                  "package has, and it is the same data every catalogue "
                  "correlation is built on.",
        "literature": "the value the design texts quote for this type of "
                      "machine (Peters & Timmerhaus; Towler & Sinnott; "
                      "Turton), with the range they give. Used where the "
                      "catalogue has no correlation of this type to fit.",
        "six-tenths rule": "no published exponent for this type, so the "
                           "six-tenths rule (Williams 1947) stands in. It is "
                           "a fallback, not a default: if the cost matters, "
                           "fit your own exponent from two quoted sizes.",
    },

    "installation_by_type": {
        "factor": "installed cost as a multiple of this type's purchased "
                  "cost. Derived from DOE/NETL-2002/1169: the bulk material "
                  "and labour factors for the service this kind of machine "
                  "sits in (Tables 2-5), plus the labour to set that kind of "
                  "machine (Table 6). Type your own over it if you have a "
                  "better number; the default stays visible beside it.",
        "unknown": "DOE/NETL-2002/1169 does not name this type, so it "
                   "borrows the plant-level service and setting class chosen "
                   "above. Set the item's equipment type, or type a factor "
                   "here, if that is not what you want.",
    },

    "cost_index": {
        "cepci": "the Chemical Engineering Plant Cost Index for that year "
                 "(1957-59 = 100). Every cost in the estimate is escalated "
                 "between dollar-years by the ratio of two of these, so it is "
                 "the one shared number the whole capital estimate rests on.",
        "dollar_year": "the year your estimate is quoted in. Correlations are "
                       "escalated from their own basis year to this one. Past "
                       "2025 there is no published index, so you have to "
                       "supply one - the row will be empty until you do, and "
                       "the run will say so rather than guess.",
        "basis_year": "the year the equipment correlations themselves are "
                      "quoted in: 1998 Q1, US Gulf Coast, carbon steel. It is "
                      "the bottom of every escalation in the study.",
        "provisional": "an estimate, not a published figure. Chemical "
                       "Engineering stopped publishing the CEPCI free of "
                       "charge in September 2024; if you have a subscription, "
                       "type the published value over it.",
        "override": "your value for that year, used in place of the shipped "
                    "one and saved with the project - so re-opening the study "
                    "reproduces the number it was quoted on rather than "
                    "whatever ships today.",
    },

    "land": {
        "land_cost": "what the site costs, as an amount of money - not an "
                     "area, and not a percentage. It is added to owner's "
                     "costs whole and is not depreciated, because land does "
                     "not wear out; a DCF run returns it at the end of the "
                     "project life along with the working capital.",
        "land_area_acres": "site area, if you would rather work the cost out "
                           "by the acre. Area times price per acre replaces "
                           "the amount above, and both are saved with the "
                           "study so the working is still there when you "
                           "re-open it.",
        "land_cost_per_acre": "price per acre. NETL uses $3,000/acre for "
                              "rural US sites - 300 acres for an IGCC or PC "
                              "plant, 100 for an NGCC.",
    },

    "installation": {
        "effective_factor": "installed cost divided by purchased cost, for "
                            "the items that go through installation. It is "
                            "the single number the whole purchased-to-BEC "
                            "step comes to, whichever method produced it, and "
                            "it is the one to quote and to sanity-check: 2.5 "
                            "to 4 is the usual range for a fluid-processing "
                            "plant.",
        "share_of_bec": "everything except the machines themselves - bulk "
                        "material and construction labour - as a share of the "
                        "bare erected cost. The complement is the purchased "
                        "equipment, which is typically only 15-30% of it.",
    },

    "equipment_parameter_role": {
        "driver": "the size the cost correlation reads. Exactly one parameter "
                  "per item is the driver, and it is the one worth getting "
                  "right - everything else on the item is description.",
        "process": "recorded, reported, and not used in the costing. Duty, "
                   "flow, temperature and pressure belong here.",
    },

    "equipment_mode": {
        "catalogue": "a power-law correlation regressed from the DOE/NETL "
                     "Appendix B cost tables. Give a size and it returns a "
                     "purchased cost.",
        "custom": "your own correlation: base cost, base size, exponent and "
                  "dollar-year. Use it for anything proprietary or "
                  "technology-defining, which is exactly what the catalogue "
                  "cannot know about.",
        "direct": "a single price, escalated but never scaled. Use it for a "
                  "vendor quote. Mark it installed if the quote was.",
    },

    # -- equipment parameters, for the expandable editor on each item ----
    # Keys are EquipmentItem field names. The interface shows these beside the
    # input, which is the whole point: "exponent" means nothing to a reader who
    # has not read DOE/NETL-2002/1169, and an unexplained field gets left at a
    # default that may be wrong for the item.
    "equipment_param": {
        "tag": "your equipment number. It labels this item everywhere — the "
               "tables, the charts, the report and the workbook.",
        "kind": "which correlation prices this item. Pick the closest match by "
                "duty; the scaled parameter it wants is shown beside the size.",
        "size": "the scaled parameter, in the unit shown. This is the one "
                "number that drives the cost, so it is the one worth getting "
                "right.",
        "size_unit": "the unit the size is quoted in. For a catalogue item it "
                     "comes from the correlation; for your own correlation you "
                     "set it, and it is carried into the report and the "
                     "workbook.",
        "base_size": "the reference size of the correlation — the size at "
                     "which the base cost applies. Catalogue values sit at the "
                     "geometric mean of the fitted data, where a power law is "
                     "best behaved.",
        "base_cost": "the cost at the base size, in the base year. Override it "
                     "when you have a firm price at a known size and want to "
                     "scale from that instead.",
        "exponent": "the scale factor n in C = C_base x (S/S_base)^n. Below 1 "
                    "it means economy of scale: doubling the size costs less "
                    "than twice as much. Fitted values across the catalogue "
                    "run from about 0.17 to 1.39; the six-tenths rule is a "
                    "fallback, not a default.",
        "base_year": "the dollar-year the base cost is quoted in. teakit "
                     "escalates from here to your project dollar-year by "
                     "CEPCI. Catalogue correlations are 1998.",
        "quantity": "how many of this item the plant needs. Cost is multiplied "
                    "by quantity plus spares.",
        "spare": "installed spares. They cost the same as duty units and are "
                 "included in the capital, so a 2+1 pump set is quantity 2, "
                 "spare 1.",
        "material": "material of construction. The correlations are carbon "
                    "steel; anything else applies a material factor from "
                    "DOE/NETL-2002/1169 Table 7.",
        "section": "the plant section this item belongs to. Used only for "
                   "rolling the equipment cost up by section in the report — "
                   "but that rollup is usually the most useful table in it.",
        "direct_cost": "the price as quoted, in the basis year below. It is "
                       "escalated to your dollar-year but never scaled, "
                       "because a quote is for one specific machine.",
        "installation_factor": "installed cost as a multiple of this item's "
                               "purchased cost, when this one machine is "
                               "genuinely unlike the rest of its type. Leave "
                               "it blank and the item takes its equipment "
                               "type's factor. Only the per-item installation "
                               "method reads it; the plant-wide methods apply "
                               "one factor to the whole list by construction.",
        "cost_is_installed": "tick this only if the price already includes "
                             "installation. Such items skip the installation "
                             "factors and enter the capital cascade at BEC. "
                             "Leaving it unticked on an installed price is the "
                             "classic and expensive error.",
        "note": "free text. It becomes the item's description in the report "
                "when there is no catalogue entry to supply one.",
        "category": "what kind of machine this is - pump, compressor, heat "
                    "exchanger. Plant section says where an item sits; this "
                    "says what it is, and it is what lets three blowers of "
                    "different sizes appear as one line when the equipment "
                    "cost is rolled up by type. Left blank, a catalogue item "
                    "takes the family of its correlation.",
        "consumables": "parts this item wears out and has replaced on a "
                       "schedule. They are neither a utility nor capital: they "
                       "are bought again and again, so teakit annualises each "
                       "over its replacement interval and adds it to the "
                       "operating cost under this item's tag.",
        "name": "what this item is called in plain words - 'Syngas "
                "compressor', not 'K-101'. The tag identifies it; the name "
                "makes the equipment schedule readable. Left blank, the "
                "description or the tag is used.",
        "parameters": "process parameters that do not drive the cost: duty, "
                      "inlet flow, temperature, pressure, area. teakit does "
                      "not read them - the cost comes from the size above - "
                      "but they are the basis of the utility figures beside "
                      "them, they appear in the equipment schedule, and they "
                      "are where a flowsheet import puts what it knows.",
        "utilities": "what this item consumes when it runs: power for a "
                     "compressor, cooling water for a condenser, steam for a "
                     "reboiler. Each line is priced and rolled into the "
                     "operating cost, tagged with this item, so the "
                     "electricity bill can be traced back to the machines "
                     "that incur it rather than appearing as one "
                     "unattributable plant total.",
    },

    # -- one replacement part, for the editor on each item --------------
    "equipment_consumable": {
        "name": "the part that gets replaced - electrodes, a catalyst charge, "
                "membranes, filter elements, a mill liner.",
        "quantity": "how many go into one machine at each replacement. A "
                    "reactor taking six electrodes is 6, not 1.",
        "unit": "what one of them is - set, piece, m2, kg. It is only a label; "
                "the cost below is per one of these.",
        "unit_cost": "delivered cost of one, in project dollars. Installation "
                     "labour for the swap belongs in maintenance, not here.",
        "interval_years": "how often the whole lot is replaced, in years. A "
                          "quarter is 0.25, eighteen months is 1.5, every four "
                          "years is 4. teakit spreads the cost evenly over the "
                          "interval - a set lasting 18 months costs two-thirds "
                          "of a set a year - because a levelised cost is an "
                          "average and a lumpy replacement schedule is not "
                          "something a single annual figure can carry.",
        "per_unit": "on, the quantity is per machine and is multiplied by the "
                    "item's quantity. Installed spares are excluded: a spare "
                    "is not running and is not wearing anything out.",
        "scales_with_rate": "on, replacement is driven by run time, so a plant "
                            "at 80% capacity replaces 80% as often. Off pins "
                            "it to the calendar - a desiccant that ages on the "
                            "shelf, or a certificate-driven change-out.",
        "category": "which operating-cost group it is reported in. Catalyst "
                    "and chemicals is the usual home for a consumable part.",
    },

    # -- one equipment utility line, for the editor on each item ---------
    "equipment_utility": {
        "name": "which utility. Picking one from the catalogue brings its unit "
                "and its published price with it, so a change of tariff moves "
                "every item at once.",
        "rate": "the draw at full production. It is scaled by the capacity "
                "factor unless you say otherwise, so quote the design figure, "
                "not an annual average. A NEGATIVE rate is generation: a steam "
                "turbine, an expander or a waste-heat set that puts power back "
                "rather than taking it. It nets against everything else drawing "
                "on that utility, and if the plant makes more than it uses the "
                "line becomes a credit - which is the right answer only if you "
                "can actually sell it, so an export you are paid for is better "
                "modelled as a byproduct on the Products panel, where it "
                "carries its own price.",
        "unit": "the physical unit the rate is in. It has to match the unit the "
                "price is quoted per, and the catalogue supplies both together.",
        "price": "cost per unit. Left blank it comes from the utility "
                 "catalogue, which is what you want: one tariff, set once, "
                 "applied everywhere. Fill it in only to override the price "
                 "for this item alone.",
        "basis": "whether the rate is per operating hour or per year. Hourly "
                 "is the normal case for a utility; per year is for a lump sum "
                 "or a charge on a calendar schedule.",
        "scales_with_rate": "on, consumption follows the capacity factor, "
                            "which is right for almost every utility. Off pins "
                            "it to a fixed annual amount - a take-or-pay "
                            "contract, or a minimum demand charge.",
        "per_unit": "on, the rate is one unit's draw and is multiplied by the "
                    "item's quantity. Installed spares are never counted: a "
                    "spare pump is in the capital but it is not running and "
                    "not drawing power. Off means you have already summed the "
                    "whole bank.",
        "category": "which operating-cost panel this line lands on. Utility is "
                    "the usual answer; waste covers an effluent the item "
                    "produces, and raw material a reagent it consumes.",
    },

    # -- sensitivity -----------------------------------------------------
    "sensitivity_kind": {
        "tornado": "swings each parameter low and high one at a time and ranks "
                   "them by how far they move the answer. Start here.",
        "sweep": "walks one parameter across a range and plots the response — "
                 "it shows curvature that a tornado bar cannot.",
        "monte_carlo": "samples every uncertain parameter together and returns "
                       "a distribution. Only as good as the distributions you "
                       "give it.",
        "breakeven": "solves for the parameter value that hits a target metric "
                     "— the feedstock price at which the project works.",
    },

    # -- charts ----------------------------------------------------------
    "chart_source": {
        "type_shares": "equipment cost by kind of machine, adding every pump "
                       "together, every compressor, every exchanger. Plant "
                       "section answers where the money went; this answers "
                       "what it was spent on.",
        "equipment_shares": "purchased cost of every equipment item.",
        "section_shares": "purchased cost rolled up by plant section.",
        "capex_breakdown": "the capital ladder, element by element.",
        "opex_items": "every operating-cost line, variable and fixed.",
        "opex_variable": "operating lines that scale with production.",
        "opex_fixed": "operating lines that do not scale with production.",
        "opex_by_category": "operating cost grouped by category.",
        "cost_stack": "the levelised cost split into capital, fixed, variable "
                      "and byproduct credit.",
    },
    "chart_kind": {
        "bar": "magnitudes side by side — the safest default.",
        "donut": "shares of a whole. Only honest when the parts are positive "
                 "and sum to something meaningful.",
        "waterfall": "how a total is built up step by step.",
    },

    # -- export ----------------------------------------------------------
    "export": {
        "xlsx": "the full workbook: cover, basis, equipment, capital, "
                "operating cost, cash flow, charts and the method appendix — "
                "with live formulas, so you can change an input in Excel and "
                "watch the estimate move.",
        "html": "a standalone report with the charts embedded. Opens offline "
                "and prints properly.",
        "markdown": "the same report as text, for a repository or a pull "
                    "request.",
        "json": "the project itself, so you or a colleague can reopen and "
                "re-run it. This is the file to keep.",
        "equipment_csv": "the equipment list with its full audit trail.",
        "cashflow_csv": "the year-by-year cash flow.",
        "equipment_utility_csv": "what every equipment item consumes, priced, "
                                 "one row per line — the tag, the utility, the "
                                 "rate for the running units, the price and its "
                                 "source, and the annual cost.",
        "opex_csv": "the operating cost sheet as CSV: every variable and fixed "
                    "line with its quantity, its unit and its annual cost.",
    },
}


def _fill_setting_help() -> None:
    """
    Populate ``OPTION_HELP["loh_setting"]`` from the factor table itself.

    There are forty setting classes, each a self-describing piece of
    equipment; the useful fact about one is not a sentence of prose but its
    setting-labour factor. Generating them from the table also means the help
    cannot go stale when the table changes, which a hand-written list would.
    """
    from .capital import LOH_SETTING_FACTORS
    OPTION_HELP["loh_setting"] = {
        name: (f"setting labour at {factor:.0%} of purchased cost. Pick the "
               f"class your equipment most resembles — the factor is what it "
               f"contributes, not the name.")
        for name, factor in sorted(LOH_SETTING_FACTORS.items())
    }


_fill_setting_help()


def help_for(field: str, value) -> str:
    """The help line for one option, or ``""``.

    >>> help_for("method", "simple")[:16]
    'recovers capital'
    >>> help_for("method", "nonesuch")
    ''
    """
    return OPTION_HELP.get(field, {}).get(str(value), "")


def option_help_flat() -> dict[str, dict[str, str]]:
    """:data:`OPTION_HELP` as plain nested dicts, for the JSON API."""
    return {k: dict(v) for k, v in OPTION_HELP.items()}


# ===========================================================================
# 2. The manual — what the Info section shows
# ===========================================================================
def _p(text):
    return {"kind": "p", "text": text}


def _ul(items):
    return {"kind": "ul", "items": list(items)}


def _eq(expr, note=""):
    return {"kind": "eq", "expr": expr, "note": note}


def _tbl(headers, rows):
    return {"kind": "table", "headers": list(headers),
            "rows": [list(r) for r in rows]}


def _note(text, tone="note"):
    return {"kind": "note", "text": text, "tone": tone}


#: The in-application manual, as structured blocks the interface renders and
#: the HTML report can reuse. Ordered as the workflow is ordered.
GUIDE: list[dict] = [
    {
        "id": "what",
        "title": "What teakit is",
        "blurb": "A techno-economic estimate of a process plant, built on "
                 "public methodology you can cite.",
        "blocks": [
            _p("teakit turns an equipment list into a levelised cost. It sizes "
               "and prices the equipment from published correlations, walks "
               "that up to total capital through the DOE/NETL cascade, adds "
               "the annual cost of running the plant, and then charges the "
               "capital against production by whichever of three costing "
               "conventions you choose."),
            _p("Every number it produces is traceable to a public source. That "
               "is the point: an estimate you cannot defend line by line is "
               "not an estimate, it is an opinion with decimal places."),
            _tbl(["stage", "what it does", "source"], [
                ["Equipment", "power-law cost correlations, 42 of them, "
                              "escalated by CEPCI",
                 "DOE/NETL-2002/1169 App. B"],
                ["Capital", "purchased -> installed -> BEC -> EPCC -> TPC -> "
                            "TOC -> TASC", "NETL-PUB-22580 §2.1"],
                ["Operating", "variable streams, labour, factored fixed costs",
                 "NREL / Peters & Timmerhaus / NETL"],
                ["Finance", "discounted cash flow, fixed charge rate, or "
                            "straight line", "NREL/TP-5100-47764, NETL Eq. 3/4"],
            ]),
            _note("The application in the window and the application in the "
                  "browser are the same program — the window only swaps the "
                  "frame around it. A number that appears in one appears in "
                  "the other."),
        ],
    },
    {
        "id": "accuracy",
        "title": "How accurate this is",
        "blurb": "AACE Class 5-4. Read this before quoting a number to two "
                 "decimal places.",
        "blocks": [
            _p("The equipment correlations come from Aspen ICARUS runs "
               "tabulated in 1998 Q1 US Gulf Coast dollars. The source report "
               "quotes +50%/-30% for order-of-magnitude use and +30%/-15% for "
               "a budget estimate — and that is before any escalation error."),
            _p("Escalating from 1998 to a recent dollar-year roughly doubles "
               "the cost, and CEPCI is a single national index that knows "
               "nothing about your steel supply or your labour market. A long "
               "escalation widens the band; teakit reports the estimate class "
               "on every export so the reader cannot miss it."),
            _ul([
                "Treat the answer as a range, not a point.",
                "The ranking of options is far more reliable than the absolute "
                "level — use it to choose between routes, not to set a budget.",
                "Anything technology-defining will not be in the catalogue. "
                "Enter it as a custom correlation or a vendor price, or the "
                "estimate is about a plant you are not building.",
            ]),
        ],
    },
    {
        "id": "workflow",
        "title": "The order to work in",
        "blurb": "Nine steps, and they are in the rail in the order they "
                 "should be done.",
        "blocks": [
            _tbl(["step", "what to settle", "why it comes first"], [
                ["01 Project", "dollar-year, location, currency, costing "
                               "method", "every number downstream is quoted "
                                         "on this basis"],
                ["02 Equipment", "the equipment list and its sizes",
                 "purchased cost drives the whole capital ladder"],
                ["03 Capital", "installation route, contingency, owner's costs",
                 "purchased cost is only 15-30% of what a plant costs"],
                ["04 Operating cost", "feeds, utilities, waste, labour, fixed "
                                      "factors", "usually the larger half of a "
                                                 "levelised cost"],
                ["05 Products", "the slate, and how cost is allocated to it",
                 "the allocation rule can move the answer by a factor of two"],
                ["06 Finance", "discount rate, tax, life, timing, debt",
                 "sets what the capital charge actually is"],
                ["07 Results", "read the basis and the warnings, then the "
                               "number", "a number without its basis is a "
                                         "rumour"],
                ["08 Charts", "where the money goes",
                 "shows you which assumption is worth another hour"],
                ["09 Sensitivity", "which assumptions drive the answer",
                 "usually three or four; the rest could be wrong by 2x "
                 "without mattering"],
            ]),
        ],
    },
    {
        "id": "equipment-guide",
        "title": "The equipment list",
        "blurb": "Four ways to price a line, and when each is the right one.",
        "blocks": [
            _p("Every item is priced as a power law in one scaled parameter — "
               "a pump by flow, an exchanger by area, a compressor by shaft "
               "power. Expand any row to see and edit every parameter that "
               "goes into its cost, with the catalogue default shown beside "
               "your value and a reset beside that."),
            _tbl(["basis", "what you supply", "when to use it"], [
                ["catalogue", "a kind and a size",
                 "standard equipment inside the fitted range"],
                ["catalogue, overridden", "a size, plus any of base cost, base "
                                          "size or exponent",
                 "you have a quote at one size and want to scale it, or you "
                 "trust a different exponent"],
                ["custom correlation", "base cost, base size, exponent, "
                                       "dollar-year, unit",
                 "proprietary or technology-defining equipment"],
                ["direct cost", "one price and its dollar-year",
                 "a vendor quote for a specific machine"],
            ]),
            _note("If a vendor's price is an <em>installed</em> price, tick "
                  "'already an installed cost'. Otherwise it goes through the "
                  "installation factors a second time — the classic and "
                  "expensive error this application tries hardest to prevent.",
                  "warn"),
            _p("Past the fitted maximum, economy of scale stops: teakit splits "
               "the duty into parallel trains at roughly constant unit cost "
               "rather than extrapolating the power law, because extrapolating "
               "it is one of the commonest ways to under-estimate a large "
               "plant. Below the fitted minimum it refuses unless you allow "
               "extrapolation, and records that you did."),
        ],
    },
    {
        "id": "capital-guide",
        "title": "The capital ladder",
        "blurb": "BEC to TASC, and what each rung actually contains.",
        "blocks": [
            _eq("BEC -> EPCC -> TPC -> TOC -> TASC",
                "NETL-PUB-22580 §2.1, verbatim"),
            _tbl(["rung", "what it adds"], [
                ["BEC", "bare erected cost — process equipment, on-site "
                        "support facilities, and the labour to install them"],
                ["EPCC", "+ EPC contractor services: detailed design, "
                         "procurement, construction management, permitting"],
                ["TPC", "+ process contingency (technology immaturity) and "
                        "project contingency (estimate immaturity)"],
                ["TOC", "+ owner's costs: pre-production, spares, financing "
                        "fees, land, owner's engineering"],
                ["TASC", "x escalation and carrying cost over the construction "
                         "period — mixed current-year dollars"],
            ]),
            _note("Process contingency and project contingency are not "
                  "interchangeable. The first covers a technology you have not "
                  "built before; the second covers an estimate you have not "
                  "finished. A first-of-a-kind plant needs both."),
            _p("TOC is an overnight cost in base-year dollars. TASC is what the "
               "money actually costs by the time it is spent, and it is the "
               "quantity the NETL fixed-charge-rate equation multiplies."),
        ],
    },
    {
        "id": "opex-guide",
        "title": "Operating cost",
        "blurb": "What the plant spends every year — and what does not belong "
                 "here.",
        "blocks": [
            _note("Depreciation and interest are <b>not</b> operating costs. "
                  "The costing method already charges for capital; putting "
                  "them in the operating sheet counts the plant twice.",
                  "warn"),
            _p("Variable lines scale with production: feedstock, catalyst, "
               "utilities, waste disposal. Fixed lines do not: labour, "
               "maintenance, insurance, property tax, overhead. teakit keeps "
               "them apart because the costing methods treat them "
               "differently and because the split is what a sensitivity study "
               "needs."),
            _p("The factored fixed costs come from one of three published "
               "conventions. Pick one and name it in your report. Mixing "
               "them — a maintenance factor from one and an overhead factor "
               "from another — double-counts overhead in a way that is very "
               "hard to spot afterwards."),
        ],
    },
    {
        "id": "products-guide",
        "title": "Products and allocation",
        "blurb": "Exactly one product is primary; its price is what gets "
                 "solved for.",
        "blocks": [
            _p("Everything else is either credited against total cost or "
               "allocated a share of it. Which of those you choose can move "
               "the answer by a factor of two, so it is a decision to make "
               "deliberately and state plainly."),
            _tbl(["rule", "what it does", "the trap"], [
                ["byproduct credit", "subtract secondary revenue from total "
                                     "cost", "when credits approach total "
                                             "cost, the answer is really a "
                                             "byproduct price forecast"],
                ["market value", "split cost in proportion to revenue",
                 "needs a reference price for the primary product, so it is "
                 "mildly circular"],
                ["mass", "split cost by tonnes",
                 "only defensible if a tonne of each is worth about the same"],
                ["energy", "split cost by heating value",
                 "needs an energy content on every product"],
            ]),
        ],
    },
    {
        "id": "finance-guide",
        "title": "Finance, and the one rule that matters",
        "blurb": "Keep one basis throughout.",
        "blocks": [
            _note("All real with a real discount rate, or all nominal with "
                  "escalation. Mixing them is the commonest error in a "
                  "techno-economic analysis, and it always flatters the "
                  "project.", "warn"),
            _p("If the discount rate you entered is already a weighted average "
               "cost of capital, leave the debt fraction at zero. Modelling "
               "debt as well charges the project for the same borrowing "
               "twice."),
            _ul([
                "<b>dcf</b> — the price at which NPV is exactly zero, from a "
                "full after-tax cash flow with MACRS depreciation. Quote "
                "this one.",
                "<b>fcr</b> — a fixed charge rate against as-spent capital. "
                "Reproducible and directly comparable with published NETL "
                "figures.",
                "<b>simple</b> — straight-line recovery with no cost of "
                "capital. For screening only; it will understate by 30-50%.",
            ]),
        ],
    },
    {
        "id": "reports-guide",
        "title": "Getting the work out",
        "blurb": "Six exports; the Excel workbook and the project file are the "
                 "two that matter.",
        "blocks": [
            _tbl(["export", "what it is for"], [
                ["Excel workbook", "the full estimate across sectioned, "
                                   "coloured sheets with live formulas and "
                                   "charts — change an input in Excel and the "
                                   "workbook recomputes"],
                ["HTML report", "a standalone document with charts embedded; "
                                "opens offline, prints properly"],
                ["Markdown", "the same report as text, for a repository"],
                ["Save project", "the project itself as JSON — the file to "
                                 "keep and to send a colleague"],
                ["Equipment CSV", "the equipment list with its audit trail"],
                ["Cash flow CSV", "the year-by-year cash flow"],
            ]),
            _p("The workbook and the HTML report both end with a method "
               "appendix that states the equations actually used for this run, "
               "with your own numbers substituted, so a reviewer can reproduce "
               "the result with a calculator."),
        ],
    },
    {
        "id": "sources",
        "title": "Sources",
        "blurb": "Everything here is public. Cite it.",
        "blocks": [
            _tbl(["reference", "used for"], [
                ["Loh, Lyons & White (2002), DOE/NETL-2002/1169",
                 "equipment cost correlations, material factors, "
                 "distributive installation factors"],
                ["NETL-PUB-22580, Quality Guidelines for Energy Systems "
                 "Studies", "the capital cascade, owner's costs, TASC/TOC, "
                            "the FCR method"],
                ["NREL/TP-5100-47764", "cash-flow conventions, factored fixed "
                                       "costs, staffing template"],
                ["AACE 16R-90 / 18R-97", "contingency bands and estimate "
                                         "classification"],
                ["Chemical Engineering Plant Cost Index (CEPCI)",
                 "escalation between dollar-years"],
                ["Peters & Timmerhaus, 5th ed.",
                 "the alternative factored fixed-cost convention"],
                ["U.S. EIA / BLS series", "default utility prices and "
                                          "operator salaries"],
            ]),
        ],
    },
]


# ===========================================================================
# 3. The method appendix — equations with this run's numbers in them
# ===========================================================================
def _money(v, cur="$"):
    try:
        return f"{cur}{float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _pctf(v, dp=2):
    try:
        return f"{float(v) * 100:.{dp}f}%"
    except (TypeError, ValueError):
        return "—"


def _num(v, dp=4):
    try:
        return f"{float(v):,.{dp}f}"
    except (TypeError, ValueError):
        return "—"


def _charge_chain(result, capital, capital_label, charge_label, opex, cur):
    """
    The annual-revenue-requirement arithmetic, as steps that actually
    reconcile to the reported unit cost.

    The naive chain — capital charge, plus operating cost, divided by
    production — does *not* close whenever there is a byproduct credit or a
    cost share other than 100%. Showing it that way invites a reviewer to
    conclude the tool cannot add up, so the credit and any allocation share
    are written out as their own lines.
    """
    q = result.annual_production
    steps = [
        {"label": capital_label, "detail": _money(capital, cur)},
        {"label": charge_label,
         "detail": (_money(result.capital_component * q, cur) + " per year")
                   if q else "—"},
        {"label": "+ annual operating cost", "detail": _money(opex.total, cur)},
    ]
    # ProjectResult stores byproduct_component as a positive magnitude that is
    # subtracted (see ProjectResult.cost_stack, which negates it), so it is a
    # deduction here, not another addend.
    credit = result.byproduct_component * q if q else 0.0
    if abs(credit) > 0.5:
        steps.append({"label": "- byproduct credit",
                      "detail": _money(credit, cur)})
    allocated = (result.capital_component + result.fixed_component
                 + result.variable_component - result.byproduct_component) * q
    charged = result.capital_component * q + opex.total - credit
    if q and abs(allocated - charged) > max(1.0, 0.001 * abs(charged)):
        # A market-value, mass or energy split gives the primary product only
        # part of the total, so say what part rather than leaving a gap.
        steps.append({"label": "x share allocated to the primary product",
                      "detail": _money(allocated, cur)})
    steps += [
        {"label": "/ annual production",
         "detail": f"{q:,.0f} {result.unit}"},
        {"label": "= levelised cost",
         "detail": f"{result.unit_cost:,.4f} {cur}/{result.unit}"},
    ]
    return steps


def _section(sid, title, summary, source="", equations=None, symbols=None,
             steps=None, notes=None):
    return {"id": sid, "title": title, "summary": summary, "source": source,
            "equations": equations or [], "symbols": symbols or [],
            "steps": steps or [], "notes": notes or []}


def explain(project, result) -> list[dict]:
    """
    The method appendix for one run.

    Returns a list of sections. Each carries a plain-language ``summary``, the
    ``equations`` actually evaluated, a ``symbols`` table with this run's
    values substituted, and ``steps`` — the arithmetic, in order, so the result
    can be reproduced by hand.

    Only the selected methods are explained in full; the alternatives are named
    so the reader knows a choice was made.

    >>> import teakit
    >>> p = teakit.demo("methanol")
    >>> ids = [s["id"] for s in explain(p, p.run())]
    >>> "equipment" in ids and "capital" in ids and "costing" in ids
    True
    """
    cur = result.currency if result.currency != "USD" else "$"
    f, c, o = project.finance, project.capital, project.opex
    cap, opex = result.capital, result.opex
    out: list[dict] = []

    # -- 1. equipment ----------------------------------------------------
    n_cat = sum(1 for r in project.equipment if r.mode == "catalogue")
    n_cus = sum(1 for r in project.equipment if r.mode == "custom")
    n_dir = sum(1 for r in project.equipment if r.mode == "direct")
    out.append(_section(
        "equipment", "Purchased equipment cost",
        "Each item is priced as a power law in one scaled parameter, escalated "
        "from the correlation's dollar-year to yours by CEPCI, then adjusted "
        "for material of construction and location.",
        source=f"{_eqdata.SOURCE} — {_eqdata.BASIS_YEAR} Q{_eqdata.BASIS_QUARTER} "
               f"{_eqdata.BASIS_LOCATION}, {_eqdata.BASIS_MATERIAL} basis",
        equations=[
            {"label": "purchased cost of one unit",
             "expr": "C = C_base x (S / S_base)^n x (I_target / I_base) "
                     "x F_M x F_L"},
            {"label": "line total",
             "expr": "C_line = C x (quantity + spares)"},
        ],
        symbols=[
            {"sym": "C_base, S_base", "meaning": "reference cost and size of "
                                                 "the correlation",
             "value": "per item — see the equipment sheet"},
            {"sym": "n", "meaning": "fitted scale factor (the six-tenths rule "
                                    "is a fallback, not a default)",
             "value": "0.17 to 1.39 across the catalogue"},
            {"sym": "I_base", "meaning": f"CEPCI, {_eqdata.BASIS_YEAR} basis",
             "value": f"{_eqdata.BASIS_CEPCI:g}"},
            {"sym": "I_target", "meaning": f"CEPCI, {result.dollar_year}",
             "value": "see the basis sheet"},
            {"sym": "F_M", "meaning": "material factor, carbon steel = 1.00",
             "value": "per item"},
            {"sym": "F_L", "meaning": "location factor, US Gulf Coast = 1.00",
             "value": f"{project.effective_location_factor():.3f} "
                      f"({project.location})"},
        ],
        steps=[
            {"label": "items priced",
             "detail": f"{len(project.equipment)} lines — {n_cat} from the "
                       f"catalogue, {n_cus} user correlations, {n_dir} direct "
                       f"costs"},
            {"label": "purchased equipment cost",
             "detail": _money(result.purchased_equipment_cost, cur)},
        ],
        notes=[
            "Above a correlation's fitted maximum the duty is split into "
            "parallel trains at roughly constant unit cost, rather than "
            "extrapolating the power law.",
            "Items entered as an installed cost bypass the installation step "
            "and enter the cascade at BEC.",
        ] + list(result.notes or []),
    ))

    # -- 2. installation -------------------------------------------------
    if c.installation_method == "loh":
        inst_eq = [{"label": "per item",
                    "expr": "C_installed = C_purchased x (1 + sum(bulk material "
                            "factors) + sum(labour factors) + setting labour)"}]
        inst_sum = ("Bulk materials and labour are built up separately for each "
                    "item — foundations, structural steel, piping, electrical, "
                    "instrumentation, insulation and paint — each with its own "
                    "material and labour factor, plus setting labour by "
                    "equipment class.")
        inst_syms = [
            {"sym": "service", "meaning": "piping intensity of the duty",
             "value": c.loh_service},
            {"sym": "setting class",
             "meaning": "equipment class driving setting labour",
             "value": c.loh_setting},
        ]
        inst_src = "DOE/NETL-2002/1169 Tables 2-6"
    elif c.installation_method == "type":
        inst_eq = [{"label": "per item",
                    "expr": "C_installed = C_purchased x f(equipment type)"}]
        inst_sum = ("The same DOE/NETL build-up, but the service regime and "
                    "the setting-labour class are taken from each item's own "
                    "equipment type rather than one pair standing for the "
                    "whole list. Bulk material and setting labour are not the "
                    "same fraction of a pump's cost as of a crusher's, and "
                    "this is the only installation method here that says so. "
                    "The factor quoted below is the weighted average the run "
                    "produced, not a number anyone chose.")
        used = sorted({(r.get("category") or "other"),
                       } for r in result.equipment_rows if not r.get("installed"))
        inst_syms = [
            {"sym": "f", "meaning": "installed over purchased, weighted across "
                                    "the equipment list",
             "value": _num(result.installation_factor, 3)},
            {"sym": "types", "meaning": "equipment types installed separately",
             "value": str(len({r.get("category") or "other"
                               for r in result.equipment_rows
                               if not r.get("installed")}))},
        ]
        inst_src = "DOE/NETL-2002/1169 Tables 2-6, resolved per equipment type"
    elif c.installation_method == "lang":
        inst_eq = [{"label": "whole plant",
                    "expr": "C_installed = F_Lang x C_purchased"}]
        inst_sum = ("A single whole-plant multiplier on total purchased cost. "
                    "It cannot distinguish a pump from a tower, so it is an "
                    "order-of-magnitude device.")
        from .capital import LANG_FACTORS
        inst_syms = [{"sym": "F_Lang", "meaning": f"Lang factor, {c.lang_type}",
                      "value": _num(LANG_FACTORS.get(c.lang_type, 0), 2)}]
        inst_src = "Lang (1948); factors as tabulated in NETL and the textbooks"
    else:
        inst_eq = [{"label": "whole plant",
                    "expr": "C_installed = f x C_purchased"}]
        inst_sum = ("A single multiplier supplied by the user. Nobody outside "
                    "your organisation can reproduce it, so state it in the "
                    "report.")
        inst_syms = [{"sym": "f", "meaning": "user installation factor",
                      "value": _num(c.installation_factor, 2)}]
        inst_src = "user-supplied"

    alternatives = {"loh": "the same factors resolved per equipment type, a "
                           "Lang factor, and a single user factor",
                    "type": "one service and setting class for the whole list, "
                            "a Lang factor, and a single user factor",
                    "lang": "DOE/NETL distributive factors and a user factor",
                    "factor": "DOE/NETL distributive factors and the Lang "
                              "factor",
                    }.get(c.installation_method, "the other installation methods")
    out.append(_section(
        "installation", "Purchased cost to installed cost", inst_sum,
        source=inst_src, equations=inst_eq, symbols=inst_syms,
        steps=[
            {"label": "installed direct cost",
             "detail": _money(result.installed_direct, cur)},
            {"label": "bare erected cost (BEC)", "detail": _money(result.bec, cur)},
        ],
        notes=[f"Alternatives not used on this run: {alternatives}.",
               "An already-installed cost must not pass through this step; "
               "such items enter at BEC directly."],
    ))

    # -- 3. capital ladder -----------------------------------------------
    owners = "; ".join(f"{k} {_money(v, cur)}"
                       for k, v in (cap.owners_costs or {}).items()) or "none"
    out.append(_section(
        "capital", "The capital ladder: BEC to TASC",
        "Bare erected cost is walked up to as-spent capital through EPC "
        "services, two kinds of contingency, and the owner's costs. Purchased "
        "equipment is typically only 15-30% of the final figure.",
        source="NETL-PUB-22580 §2.1 and Exhibit 2-4",
        equations=[
            {"label": "EPC cost", "expr": "EPCC = BEC x (1 + epc_fee)"},
            {"label": "total plant cost",
             "expr": "TPC = EPCC + process contingency + project contingency"},
            {"label": "total overnight cost",
             "expr": "TOC = TPC + owner's costs + land"},
            {"label": "total as-spent capital",
             "expr": "TASC = TOC x (TASC/TOC factor)"},
        ],
        symbols=[
            {"sym": "epc_fee", "meaning": "EPC contractor services, % of BEC "
                                          "(NETL uses 15-20%)",
             "value": _pctf(c.epc_fee_frac, 1)},
            {"sym": "process contingency",
             "meaning": "technology immaturity, % of BEC",
             "value": _pctf(c.process_contingency_frac, 1)},
            {"sym": "project contingency",
             "meaning": "estimate immaturity (AACE 16R-90: 15-30% for a budget "
                        "estimate)",
             "value": _pctf(c.project_contingency_frac, 1)},
            {"sym": "TASC/TOC", "meaning": f"escalation and carrying cost over "
                                           f"{f.construction_years} years of "
                                           f"construction, {c.basis} basis",
             "value": _num(cap.tasc_toc_factor, 4)},
        ],
        steps=[
            {"label": "BEC", "detail": _money(cap.bec, cur)},
            {"label": "+ EPC services", "detail": _money(cap.epc_fee, cur)},
            {"label": "= EPCC", "detail": _money(cap.epcc, cur)},
            {"label": "+ process contingency",
             "detail": _money(cap.process_contingency, cur)},
            {"label": "+ project contingency",
             "detail": _money(cap.project_contingency, cur)},
            {"label": "= TPC", "detail": _money(cap.tpc, cur)},
            {"label": "+ owner's costs",
             "detail": f"{_money(cap.total_owners_cost, cur)} ({owners})"},
            {"label": "= TOC", "detail": _money(cap.toc, cur)},
            {"label": f"x TASC/TOC {_num(cap.tasc_toc_factor, 4)}",
             "detail": _money(cap.tasc, cur)},
        ],
        notes=["TOC is an overnight cost in base-year dollars; TASC is mixed "
               "current-year dollars over the build period.",
               "Land is not depreciable and is excluded from the depreciable "
               "basis."],
    ))

    # -- 4. operating cost -----------------------------------------------
    conv = o.convention
    from . import opex as _opex
    conv_src = (_opex.FIXED_CONVENTIONS.get(conv) or {}).get("source", "")
    out.append(_section(
        "opex", "Annual operating cost",
        "Variable lines scale with production; fixed lines do not. Depreciation "
        "and interest are deliberately absent — the costing method charges for "
        "capital, and repeating it here would count the plant twice.",
        source=conv_src,
        equations=[
            {"label": "a variable line",
             "expr": "cost = rate x price x operating hours x capacity factor"},
            {"label": "maintenance", "expr": "cost = maintenance % x capital"},
            {"label": "overhead", "expr": "cost = overhead % x labour"},
        ],
        symbols=[
            {"sym": "operating hours", "meaning": "hours per year at rate",
             "value": f"{opex.operating_hours:,.0f} h/yr"},
            {"sym": "capacity factor",
             "meaning": "fraction of nameplate actually produced",
             "value": _pctf(opex.capacity_factor, 1)},
            {"sym": "convention", "meaning": "factored fixed-cost convention",
             "value": conv},
        ],
        steps=[
            {"label": "variable total", "detail": _money(opex.variable_total, cur)},
            {"label": "fixed total", "detail": _money(opex.fixed_total, cur)},
            {"label": "total annual operating cost",
             "detail": _money(opex.total, cur)},
        ] + ([{"label": "labour headcount",
               "detail": f"{opex.labor.headcount:.1f} employees"}]
             if opex.labor else []),
        notes=["Pick one fixed-cost convention and name it in the report. "
               "Mixing conventions double-counts overhead."]
        + list(opex.notes or []),
    ))

    # -- 5. allocation ---------------------------------------------------
    alloc = result.allocation
    shares = "; ".join(f"{k} {v:.1%}" for k, v in (alloc.shares or {}).items())
    credits = "; ".join(f"{k} {_money(v, cur)}"
                        for k, v in (alloc.credits or {}).items())
    out.append(_section(
        "allocation", f"Cost allocation: {alloc.method}",
        OPTION_HELP["allocation"].get(alloc.method, "").capitalize()
        or "How total cost is divided between the products.",
        source="Convention; state it explicitly in any published result.",
        equations=[{
            "label": "cost borne by the primary product",
            "expr": {
                "byproduct credit": "C_primary = C_total - sum(byproduct "
                                    "revenue)",
                "market value": "C_primary = C_total x (revenue_primary / "
                                "revenue_total)",
                "mass": "C_primary = C_total x (mass_primary / mass_total)",
                "energy": "C_primary = C_total x (energy_primary / "
                          "energy_total)",
            }.get(alloc.method, "C_primary = C_total")}],
        symbols=[
            {"sym": "primary product", "meaning": "the product whose price is "
                                                  "solved for",
             "value": f"{alloc.primary} ({alloc.primary_unit})"},
            {"sym": "annual quantity", "meaning": "primary production per year",
             "value": f"{alloc.primary_quantity:,.0f} {alloc.primary_unit}"},
        ],
        steps=[
            {"label": "total annual cost to allocate",
             "detail": _money(alloc.total_cost, cur)},
        ] + ([{"label": "credits", "detail": credits}] if credits else [])
          + ([{"label": "shares", "detail": shares}] if shares else [])
          + [{"label": "cost borne by the primary product",
              "detail": _money(alloc.cost_to_primary, cur)}],
        notes=list(alloc.notes or []),
    ))

    # -- 6. the costing method -------------------------------------------
    if result.method == "dcf":
        cf = result.cash_flow
        eqs = [
            {"label": "solve for the price P such that",
             "expr": "NPV = sum_t [ (P x Q_t - OPEX_t - Tax_t - CAPEX_t) / "
                     "(1 + r)^t ] = 0"},
            {"label": "tax in year t",
             "expr": "Tax_t = ETR x (Revenue_t - OPEX_t - Depreciation_t "
                     "- Interest_t)"},
        ]
        syms = [
            {"sym": "r", "meaning": f"discount rate, {f.basis}",
             "value": _pctf(f.discount_rate)},
            {"sym": "ETR", "meaning": "effective tax rate, federal plus state",
             "value": _pctf(f.tax_rate)},
            {"sym": "Depreciation",
             "meaning": f"MACRS {f.depreciation_years}-year schedule",
             "value": f"{f.depreciation_years} yr"},
            {"sym": "plant life", "meaning": "operating years modelled",
             "value": f"{f.plant_life_years} yr"},
            {"sym": "construction", "meaning": "years of capital spend before "
                                               "start-up",
             "value": f"{f.construction_years} yr"},
        ]
        steps = [{"label": "solved price",
                  "detail": f"{result.unit_cost:,.4f} {cur}/{result.unit}"}]
        if cf is not None:
            steps = [
                {"label": "total capital in the cash flow",
                 "detail": _money(cf.total_capital, cur)},
                {"label": "NPV at the solved price",
                 "detail": _money(cf.npv, cur) + " (zero by construction)"},
                {"label": "IRR at that price",
                 "detail": _pctf(cf.irr) if cf.irr is not None else "—"},
                {"label": "payback",
                 "detail": (f"year {cf.payback_year:.1f}"
                            if cf.payback_year is not None else "not within "
                                                                "the modelled "
                                                                "life")},
            ] + steps
        sec = _section(
            "costing", "Costing method: dcf — discounted cash flow",
            "A full after-tax cash flow is built year by year over "
            "construction and operation, and the product price is solved so "
            "that the net present value is exactly zero. That price is the "
            "minimum selling price: the lowest price at which the project "
            "still earns exactly the discount rate.",
            source="NREL/TP-5100-47764; H2A/NREL cash-flow convention",
            equations=eqs, symbols=syms, steps=steps,
            notes=["The most rigorous of the three methods, and the one to "
                   "quote in a report.",
                   "Working capital is recovered in the final year; land is "
                   "not depreciated."])
    elif result.method == "fcr":
        sec = _section(
            "costing", "Costing method: fcr — fixed charge rate",
            "The annual capital charge is a fixed charge rate applied to "
            "as-spent capital. The FCR grosses capital recovery up so it "
            "survives income tax, then gives back the present value of the "
            "depreciation tax shield.",
            source="NETL-PUB-22580 Eq. 3, 4 and 9",
            equations=[
                {"label": "levelised cost",
                 "expr": "LC = (FCR x TASC + FOM + VOM) / annual production"},
                {"label": "fixed charge rate",
                 "expr": "FCR = CRF / (1 - ETR) - ETR x D / (1 - ETR)"},
                {"label": "capital recovery factor",
                 "expr": "CRF = r (1 + r)^N / [ (1 + r)^N - 1 ]"},
                {"label": "depreciation shield",
                 "expr": "D = CRF x sum_n [ d_n / (1 + r)^n ]"},
            ],
            symbols=[
                {"sym": "r", "meaning": f"discount rate (ATWACC), {f.basis}",
                 "value": _pctf(f.discount_rate)},
                {"sym": "N", "meaning": "capital recovery period",
                 "value": f"{f.plant_life_years} yr"},
                {"sym": "ETR", "meaning": "effective tax rate",
                 "value": _pctf(f.tax_rate)},
                {"sym": "d_n", "meaning": f"MACRS {f.depreciation_years}-year "
                                          f"depreciation fractions",
                 "value": f"{f.depreciation_years} yr schedule"},
                {"sym": "FCR", "meaning": "resulting fixed charge rate",
                 "value": _pctf(result.charge_rate)
                          if result.charge_rate else "—"},
            ],
            steps=_charge_chain(result, cap.tasc, "TASC",
                                f"x FCR {_pctf(result.charge_rate)}"
                                if result.charge_rate else "x FCR",
                                opex, cur),
            notes=["The FCR is charged against TASC, not TOC — that is the "
                   "NETL convention and it matters by several percent.",
                   "NETL reference values for comparison: FCR 0.0707 real, "
                   "0.0886 nominal (Exhibit 3-5)."])
    elif result.method == "crf":
        sec = _section(
            "costing", "Costing method: crf — annualised capital",
            "Capital is turned into an equal annual payment with the capital "
            "recovery factor — the annuity that repays the whole investment "
            "over the plant life at the discount rate — and that payment is "
            "added to the operating cost, less byproduct revenue, and divided "
            "by production. It charges the cost of capital but not income "
            "tax, so it sits between the straight-line method and the full "
            "cash flow.",
            source="NETL-PUB-22580 Eq. 10; identical in the NREL ATB",
            equations=[
                {"label": "levelised cost",
                 "expr": "LC = (CRF x TOC + FOM + VOM - byproducts) / "
                         "annual production"},
                {"label": "capital recovery factor",
                 "expr": "CRF = r (1 + r)^N / [ (1 + r)^N - 1 ]"},
            ],
            symbols=[
                {"sym": "r", "meaning": f"discount rate, {f.basis}",
                 "value": _pctf(f.discount_rate)},
                {"sym": "N", "meaning": "plant life",
                 "value": f"{f.plant_life_years} yr"},
                {"sym": "CRF", "meaning": "resulting capital recovery factor",
                 "value": _pctf(result.charge_rate)
                          if result.charge_rate else "—"},
                {"sym": "TOC", "meaning": "total overnight cost",
                 "value": _money(cap.toc, cur)},
            ],
            steps=_charge_chain(result, cap.toc, "TOC",
                                f"x CRF {_pctf(result.charge_rate)}"
                                if result.charge_rate else "x CRF",
                                opex, cur),
            notes=["The CRF is charged against TOC — the overnight cost in "
                   "dollars of the dollar-year — because a CRF is a pre-tax, "
                   "constant-dollar device and TASC is neither.",
                   "No income tax is charged, so this understates a taxable "
                   "project. Compare it against the dcf answer before "
                   "quoting it."])
    else:
        sec = _section(
            "costing", "Costing method: simple — straight-line recovery",
            "Capital is recovered in equal annual slices over the plant life "
            "with no charge for the cost of capital at all. This is a "
            "screening device.",
            source="No published convention — a teaching approximation.",
            equations=[{"label": "levelised cost",
                        "expr": "LC = (TOC / N + FOM + VOM) / annual "
                                "production"}],
            symbols=[{"sym": "N", "meaning": "plant life",
                      "value": f"{f.plant_life_years} yr"},
                     {"sym": "TOC", "meaning": "total overnight cost",
                      "value": _money(cap.toc, cur)}],
            steps=_charge_chain(result, cap.toc, "TOC",
                                f"/ {f.plant_life_years} years", opex, cur),
            notes=["Charges no cost of capital and will understate a real "
                   "project by roughly 30-50%. Do not publish this figure "
                   "without saying which method produced it."])
    out.append(sec)

    # -- 7. the answer ---------------------------------------------------
    # Shares are taken against gross cost before the credit: a credit is not a
    # cost and giving it a percentage of the total makes the other three add
    # to more than 100%.
    gross = (result.capital_component + result.fixed_component
             + result.variable_component)

    def share(v):
        return f" ({v / gross:.1%} of gross)" if gross else ""

    out.append(_section(
        "result", "How the levelised cost is assembled",
        "The three cost components sum to the gross levelised cost; the "
        "byproduct credit is then deducted to give the reported unit cost.",
        source="",
        equations=[{"label": "levelised cost",
                    "expr": "LC = capital + fixed + variable - byproduct "
                            "credit, all per unit of primary product"}],
        symbols=[],
        steps=[
            {"label": "capital charge",
             "detail": f"{result.capital_component:,.4f} {cur}/{result.unit}"
                       f"{share(result.capital_component)}"},
            {"label": "+ fixed operating",
             "detail": f"{result.fixed_component:,.4f} {cur}/{result.unit}"
                       f"{share(result.fixed_component)}"},
            {"label": "+ variable operating",
             "detail": f"{result.variable_component:,.4f} {cur}/{result.unit}"
                       f"{share(result.variable_component)}"},
            {"label": "= gross levelised cost",
             "detail": f"{gross:,.4f} {cur}/{result.unit}"},
            {"label": "- byproduct credit",
             "detail": f"{result.byproduct_component:,.4f} {cur}/{result.unit}"},
            {"label": "= LEVELISED COST",
             "detail": f"{result.unit_cost:,.4f} {cur}/{result.unit}"},
        ],
        notes=["AACE Class 5-4: -25%/+50% at best. The correlations carry "
               "+50%/-30% before escalation, and CEPCI escalation adds its "
               "own error on top."]
        + list(result.warnings or []),
    ))
    return out


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
