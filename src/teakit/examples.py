"""
teakit.examples — Fully populated demonstration projects.
=========================================================

Three complete studies, so that a new user can run something real before
building an equipment list, and so the graphical application has something to
open on first launch. They are illustrations of the *method*, not statements
about the economics of any particular technology: the flowsheet quantities are
plausible but invented, and the equipment sizes are round numbers.

    >>> from teakit.examples import build_demo
    >>> p = build_demo("methanol")
    >>> r = p.run()
    >>> r.unit_cost > 0
    True
"""

from __future__ import annotations

from .opex import LaborModel, Stream
from .products import Product
from .project import EquipmentItem, EquipmentParameter, EquipmentUtility, Project

__all__ = ["build_demo", "DEMOS"]

DEMOS = {
    "methanol": "Natural-gas methanol plant, 330 kt/yr, USGC",
    "electrolysis": "100 MW PEM hydrogen plant with an oxygen byproduct",
    "biorefinery": "Cellulosic ethanol, NREL nth-plant basis, power co-product",
}


def build_demo(kind: str = "methanol") -> Project:
    """Return a ready-to-run :class:`~teakit.project.Project`."""
    if kind not in DEMOS:
        raise KeyError(f"Unknown demo {kind!r}. Options: {', '.join(DEMOS)}")
    return {"methanol": _methanol,
            "electrolysis": _electrolysis,
            "biorefinery": _biorefinery}[kind]()


# ---------------------------------------------------------------------------
def _methanol() -> Project:
    p = Project(
        name="Methanol from natural gas — 330 kt/yr",
        description=(
            "Illustrative steam-reforming methanol plant on the U.S. Gulf Coast. "
            "Equipment sizes are round numbers and the flowsheet quantities are "
            "plausible rather than balanced; the point is the costing method, "
            "not the process design."),
        dollar_year=2025, location="USGC", method="dcf")
    p.equipment = [
        # The compressor and the blower carry their own power draw, and the
        # air cooler its fans, rather than the whole plant load sitting in one
        # unattributable line on the operating cost panel. What is left there
        # is genuinely plant-level: lighting, HVAC, small drives.
        EquipmentItem(
            "K-101", kind="compressor_centrifugal_150psia", size=14_000,
            material="ss304", section="Syngas", name="Synthesis gas compressor",
            note="synthesis gas compressor",
            parameters=[EquipmentParameter("duty", 4_900, "kW"),
                        EquipmentParameter("discharge pressure", 1_150, "psig"),
                        EquipmentParameter("inlet flow", 14_000, "actual ft3/min")],
            utilities=[EquipmentUtility("electricity", 5_200, "kWh"),
                       EquipmentUtility("cooling water", 700, "m3")]),
        EquipmentItem(
            "K-102", kind="blower_rotary", size=4_000, section="Reforming",
            name="Combustion air blower",
            parameters=[EquipmentParameter("discharge pressure", 8, "psig")],
            utilities=[EquipmentUtility("electricity", 310, "kWh")]),
        EquipmentItem("E-101", kind="hx_shell_tube", size=12_000, material="ss316",
                      section="Reforming", name="Reformer waste-heat boiler",
                      note="reformer waste-heat boiler",
                      parameters=[EquipmentParameter("duty", 62_000, "kW"),
                                  EquipmentParameter("area", 12_000, "ft2")],
                      utilities=[EquipmentUtility("boiler feedwater", 62, "m3")]),
        EquipmentItem("E-102", kind="hx_shell_tube", size=9_000, material="ss304",
                      section="Synthesis"),
        EquipmentItem("E-103", kind="hx_air_cooler", size=7_500,
                      section="Synthesis", name="Synthesis loop air cooler",
                      utilities=[EquipmentUtility("electricity", 240, "kWh")]),
        EquipmentItem("V-101", kind="separator", size=9_000, quantity=2,
                      section="Synthesis", note="crude methanol knockout"),
        # 3 duty + 1 spare: four pumps are bought and three draw power. The
        # spare is in the capital and not in the electricity bill.
        EquipmentItem("P-101", kind="pump", size=1_400, quantity=3, spare=1,
                      material="ss316", section="Distillation",
                      name="Crude methanol feed pumps",
                      utilities=[EquipmentUtility("electricity", 95, "kWh")]),
        EquipmentItem("TK-101", kind="tank_storage_cone_roof", size=500_000,
                      section="Storage", note="product tankage"),
        EquipmentItem("CT-101", kind="cooling_tower", size=9_000,
                      section="Utilities", name="Cooling tower",
                      parameters=[EquipmentParameter("circulation", 9_000, "gal/min")],
                      utilities=[EquipmentUtility("electricity", 480, "kWh")]),
        # The reformer itself is technology-defining and is not in the DOE/NETL
        # catalogue. It enters as an already-INSTALLED cost and therefore
        # bypasses the installation factors — see EquipmentItem.cost_is_installed.
        EquipmentItem("F-101", mode="direct", direct_cost=48_000_000,
                      base_year=2022, cost_is_installed=True, section="Reforming",
                      note="steam methane reformer, licensor budget price"),
    ]
    p.opex.raw_materials = [
        Stream("natural gas, feed + fuel", 1_150, "MMBtu", 4.39,
               category="raw_material", source="EIA industrial price, 2024"),
        Stream("catalyst and chemicals", 1_400_000, "yr", 1.0, basis="year",
               category="catalyst", scales_with_rate=False),
    ]
    # What is left after the equipment above took its own share: the balance
    # of plant. The totals are the same as before the split — 8,500 kW, 2,400
    # m3/h and 90 m3/h — they are simply attributed now.
    p.opex.utilities = [
        Stream("electricity", 1_985, "kWh", 0.081, category="utility",
               note="balance of plant — lighting, HVAC, small drives"),
        Stream("cooling water", 1_700, "m3", 0.055, category="utility",
               note="balance of plant"),
        Stream("boiler feedwater", 28, "m3", 2.60, category="utility",
               note="balance of plant"),
    ]
    p.opex.waste = [
        Stream("wastewater treatment", 45, "m3", 1.60, category="waste"),
    ]
    p.opex.labor = LaborModel(operators_per_shift=5, supervision_frac=0.25)
    p.opex.operating_hours = 8_000
    p.opex.capacity_factor = 0.95
    p.opex.convention = "NREL"
    p.products.products = [
        Product("methanol", 330_000, "tonne", role="primary"),
        Product("export steam", 120_000, "tonne", price=18.0, role="byproduct"),
    ]
    p.capital.loh_service = "gas_gt400F_gt150psig"
    p.capital.loh_setting = "fractionator"
    p.capital.process_contingency_frac = 0.05
    p.capital.project_contingency_frac = 0.20
    p.capital.land_cost = 150 * 3_000
    p.apply_finance_preset("Merchant chemical project (levered)")
    return p


def _electrolysis() -> Project:
    p = Project(
        name="PEM electrolysis — 100 MW hydrogen plant",
        description=(
            "Illustrative 100 MW PEM water electrolysis plant. The stacks come "
            "in as an installed cost from DOE Hydrogen Program Record 24005 "
            "(~$2,000/kW, 2022$) because no generic correlation covers them; the "
            "balance of plant comes from the DOE/NETL catalogue. This is the "
            "normal shape of a real estimate."),
        dollar_year=2025, location="USGC", method="dcf")
    p.equipment = [
        EquipmentItem("EL-101", mode="direct", direct_cost=2_000 * 100_000,
                      base_year=2022, cost_is_installed=True, section="Electrolysis",
                      note="PEM stacks + power electronics, DOE Record 24005"),
        EquipmentItem("K-101", kind="compressor_centrifugal_150psia", size=9_000,
                      material="ss316", section="Compression"),
        EquipmentItem("E-101", kind="hx_shell_tube", size=6_000, material="ss316",
                      section="Cooling"),
        EquipmentItem("E-102", kind="hx_air_cooler", size=5_000, section="Cooling"),
        EquipmentItem("V-101", kind="separator", size=6_000, quantity=2,
                      material="ss316", section="Separation"),
        EquipmentItem("P-101", kind="pump", size=700, quantity=2, spare=1,
                      material="ss316", section="Water treatment"),
        EquipmentItem("CT-101", kind="cooling_tower", size=6_000, section="Utilities"),
    ]
    p.opex.utilities = [
        Stream("electricity", 105_000, "kWh", 0.045, category="utility",
               source="assumed PPA, well below the EIA industrial average"),
        Stream("process water", 22, "m3", 0.85, category="utility"),
        Stream("cooling water", 900, "m3", 0.055, category="utility"),
    ]
    p.opex.raw_materials = [
        Stream("stack replacement reserve", 6_000_000, "yr", 1.0, basis="year",
               category="catalyst", scales_with_rate=False,
               note="7-year stack life amortised annually"),
    ]
    p.opex.labor = LaborModel(operators_per_shift=2, supervision_frac=0.20)
    p.opex.operating_hours = 8_000
    p.opex.capacity_factor = 0.90
    p.products.products = [
        Product("hydrogen", 15_500_000, "kg", role="primary"),
        Product("oxygen", 124_000, "tonne", price=25.0, role="byproduct",
                note="credit only realisable with a local off-taker"),
    ]
    p.capital.process_contingency_frac = 0.20   # AACE 16R-90 pilot-data band
    p.capital.project_contingency_frac = 0.25
    p.capital.land_cost = 100 * 3_000
    p.apply_finance_preset("NREL nth-plant")
    return p


def _biorefinery() -> Project:
    p = Project(
        name="Cellulosic ethanol — 2,000 dry t/day",
        description=(
            "Illustrative biochemical conversion plant on the NREL nth-plant "
            "basis, with surplus electricity as a byproduct. Follows the "
            "structure of NREL/TP-5100-47764 without reproducing its equipment "
            "list."),
        dollar_year=2025, location="US Midwest", method="dcf")
    p.equipment = [
        EquipmentItem("M-101", kind="mill_ball", size=90, section="Feed handling"),
        EquipmentItem("R-101", kind="vessel_vertical_150psig", size=20_000, material="ss316",
                      section="Pretreatment", note="pretreatment reactor train"),
        EquipmentItem("V-101", kind="tank_storage_cone_roof", size=900_000,
                      quantity=4, section="Fermentation", note="fermenters"),
        EquipmentItem("E-101", kind="hx_shell_tube", size=14_000, material="ss304",
                      section="Distillation"),
        EquipmentItem("P-101", kind="pump", size=2_000, quantity=6, spare=2,
                      material="ss316", section="Distillation"),
        EquipmentItem("F-101", kind="filter_rotary_drum_vacuum", size=800, section="Solids"),
        EquipmentItem("CT-101", kind="cooling_tower", size=12_000, section="Utilities"),
        EquipmentItem("B-101", mode="direct", direct_cost=64_000_000, base_year=2020,
                      cost_is_installed=True, section="Boiler/turbogenerator",
                      note="biomass boiler and turbogenerator, installed"),
    ]
    p.opex.raw_materials = [
        Stream("corn stover", 105, "dry tonne", 82.0, category="raw_material",
               source="delivered feedstock cost, NREL design case basis"),
        Stream("enzymes", 14_000_000, "yr", 1.0, basis="year", category="catalyst"),
        Stream("nutrients and chemicals", 9_000_000, "yr", 1.0, basis="year",
               category="raw_material"),
    ]
    p.opex.utilities = [
        Stream("purchased electricity", 1_200, "kWh", 0.081, category="utility"),
        Stream("process water", 180, "m3", 0.85, category="utility"),
    ]
    p.opex.waste = [
        Stream("wastewater treatment", 320, "m3", 1.60, category="waste"),
        Stream("ash disposal", 4.5, "tonne", 60.0, category="waste"),
    ]
    p.opex.labor = LaborModel(operators_per_shift=6, supervision_frac=0.25)
    p.opex.operating_hours = 8_406       # NREL 0.96 on-stream factor
    p.opex.capacity_factor = 1.0
    p.products.products = [
        Product("ethanol", 61_000_000, "gal", role="primary"),
        Product("surplus electricity", 120_000, "MWh", price=45.0, role="byproduct"),
    ]
    p.capital.process_contingency_frac = 0.10
    p.capital.project_contingency_frac = 0.20
    p.apply_finance_preset("NREL nth-plant")
    return p


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
