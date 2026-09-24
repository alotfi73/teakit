"""
tea.equipment_data — Power-law cost correlations for common process equipment.
=============================================================================

AUTO-GENERATED. Do not hand-edit; regenerate with build/fit_exponents.py.

Every entry is a fit of

    C = base_cost * (S / base_size) ** exponent

to the tabulated purchased-equipment costs in Appendix B of

    Loh, H.P., Lyons, J. and White, C.W. III (2002),
    "Process Equipment Cost Estimation, Final Report",
    DOE/NETL-2002/1169, U.S. Department of Energy, National Energy
    Technology Laboratory, January 2002.
    Full text: https://www.osti.gov/servlets/purl/797810

Those tables were generated with Aspen ICARUS Process Evaluator v5.0 for
carbon-steel equipment at stated design temperature and pressure, and are
quoted in **1st Quarter 1998 US dollars, US Gulf Coast basis**. The report
states an expected accuracy of +50%/-30% for order-of-magnitude use and
+30%/-15% for budget estimates -- *before* any escalation error.

WHAT IS AND IS NOT INCLUDED (Loh et al., "Results and Usage")
------------------------------------------------------------
Included in purchased cost: internals, shells, nozzles, manholes, covers;
vendor engineering, shop drawings, shop testing, certification; shop
fabrication labour; typical manuals, small tools, accessories; packaging for
land shipment; FOB vendor.

NOT included: owner/contractor indirects (engineering, shop inspection,
start-up/commissioning); overseas or air freight, modularisation; freight,
insurance, taxes, duties; field setting costs; installation bulks.
Use tea.capital.installed_cost_loh() to add setting labour and bulks.

FITTING NOTES
-------------
`base_size` is set at the geometric mean of each fitted data set, which is
where a power law is best conditioned, and `base_cost` is the correlation
evaluated there. `r_squared` and `rel_rmse` describe the log-log fit quality.
Entries with `reliable = False` carry a `caution` string and should be used
only with the underlying tabulated points in hand.

The exponents recovered here sit where published experience says they should:
pumps ~0.5-0.7, shell-and-tube exchangers ~0.7, centrifugal compressors
~0.5-0.6, pressure vessels ~0.3-0.6, storage tanks ~0.5-0.7. See
tea.equipment.LITERATURE_EXPONENTS for an independent cross-check.
"""

from __future__ import annotations

#: Dollar-year basis of every correlation in EQUIPMENT.
BASIS_YEAR = 1998
BASIS_QUARTER = 1
#: CEPCI annual average for 1998 (1957-59 = 100), used to escalate forward.
BASIS_CEPCI = 389.5
BASIS_LOCATION = "US Gulf Coast"
BASIS_MATERIAL = "carbon steel"
SOURCE = "DOE/NETL-2002/1169 (Loh, Lyons & White, 2002), Appendix B"
SOURCE_URL = "https://www.osti.gov/servlets/purl/797810"

#: equipment_id -> correlation parameters.
EQUIPMENT: dict[str, dict] = {

    # ----------------------------------------------------------------------
    # Pumps
    # ----------------------------------------------------------------------
    "pump_centrifugal": {
        "description": "Centrifugal pump, single/multistage, CS, 150 psig, incl. motor driver",
        "size_unit": "gal/min",
        "exponent": 0.6072,
        "base_size": 1748.0,
        "base_cost": 13870.0,
        "valid_min": 100.0,
        "valid_max": 10000.0,
        "r_squared": 0.9564,
        "rel_rmse": 0.2003,
        "n_points": 15,
        "reliable": True,
    },
    "pump_rotary": {
        "description": "Rotary (sliding vane) pump, cast iron, incl. motor driver",
        "size_unit": "gal/min",
        "exponent": 0.4836,
        "base_size": 209.4,
        "base_cost": 4421.4,
        "valid_min": 10.0,
        "valid_max": 750.0,
        "r_squared": 0.864,
        "rel_rmse": 0.2229,
        "n_points": 12,
        "reliable": True,
    },
    "pump_inline": {
        "description": "General-service in-line pump, CS, incl. motor driver",
        "size_unit": "gal/min",
        "exponent": 0.4836,
        "base_size": 209.4,
        "base_cost": 4421.4,
        "valid_min": 10.0,
        "valid_max": 750.0,
        "r_squared": 0.864,
        "rel_rmse": 0.2229,
        "n_points": 12,
        "reliable": True,
    },
    "pump_reciprocating_triplex": {
        "description": "Reciprocating triplex (plunger) pump with motor driver, CS",
        "size_unit": "gal/min",
        "exponent": 0.6291,
        "base_size": 270.5,
        "base_cost": 35613.0,
        "valid_min": 25.0,
        "valid_max": 1000.0,
        "r_squared": 0.9952,
        "rel_rmse": 0.0499,
        "n_points": 11,
        "reliable": True,
    },
    "pump_reciprocating_duplex": {
        "description": "Reciprocating duplex pump with steam driver, CS",
        "size_unit": "gal/min",
        "exponent": 0.5672,
        "base_size": 270.5,
        "base_cost": 16359.0,
        "valid_min": 25.0,
        "valid_max": 1000.0,
        "r_squared": 0.9949,
        "rel_rmse": 0.0463,
        "n_points": 11,
        "reliable": True,
    },
    "pump_vacuum_1stage": {
        "description": "Mechanical oil-sealed vacuum pump, 1 stage, CS",
        "size_unit": "gal/min",
        "exponent": 0.6869,
        "base_size": 228.5,
        "base_cost": 14143.0,
        "valid_min": 30.0,
        "valid_max": 700.0,
        "r_squared": 0.9791,
        "rel_rmse": 0.1005,
        "n_points": 9,
        "reliable": True,
    },
    "pump_vacuum_2stage": {
        "description": "Mechanical oil-sealed vacuum pump, 2 stage, CS",
        "size_unit": "gal/min",
        "exponent": 0.5722,
        "base_size": 228.5,
        "base_cost": 16605.0,
        "valid_min": 30.0,
        "valid_max": 700.0,
        "r_squared": 0.9694,
        "rel_rmse": 0.1016,
        "n_points": 9,
        "reliable": True,
    },

    # ----------------------------------------------------------------------
    # Compressors, blowers and fans
    # ----------------------------------------------------------------------
    "compressor_centrifugal_50psia": {
        "description": "Centrifugal compressor, 4 stages, 50 psia discharge, air (MW 29), motor driver",
        "size_unit": "actual ft3/min",
        "exponent": 0.4897,
        "base_size": 15730.0,
        "base_cost": 2085500.0,
        "valid_min": 500.0,
        "valid_max": 200000.0,
        "r_squared": 0.9077,
        "rel_rmse": 0.3688,
        "n_points": 8,
        "reliable": True,
    },
    "compressor_centrifugal_150psia": {
        "description": "Centrifugal compressor, 7-9 stages, 150 psia discharge, motor driver",
        "size_unit": "actual ft3/min",
        "exponent": 0.5432,
        "base_size": 15730.0,
        "base_cost": 3839400.0,
        "valid_min": 500.0,
        "valid_max": 200000.0,
        "r_squared": 0.9,
        "rel_rmse": 0.443,
        "n_points": 8,
        "reliable": True,
    },
    "compressor_centrifugal_1900psia": {
        "description": "Centrifugal compressor, 9 stages, 1900 psia discharge, motor driver",
        "size_unit": "actual ft3/min",
        "exponent": 0.3675,
        "base_size": 3272.0,
        "base_cost": 2545500.0,
        "valid_min": 500.0,
        "valid_max": 15000.0,
        "r_squared": 0.9074,
        "rel_rmse": 0.167,
        "n_points": 5,
        "reliable": True,
    },
    "compressor_recip_60psia": {
        "description": "Reciprocating compressor, 1 stage, 60 psia discharge, MW 30",
        "size_unit": "actual ft3/min",
        "exponent": 0.5842,
        "base_size": 5115.0,
        "base_cost": 832610.0,
        "valid_min": 250.0,
        "valid_max": 60000.0,
        "r_squared": 0.9519,
        "rel_rmse": 0.2796,
        "n_points": 8,
        "reliable": True,
    },
    "compressor_recip_440psia": {
        "description": "Reciprocating compressor, 3 stages, 440 psia discharge, MW 30",
        "size_unit": "actual ft3/min",
        "exponent": 0.5802,
        "base_size": 3420.0,
        "base_cost": 1022500.0,
        "valid_min": 250.0,
        "valid_max": 35000.0,
        "r_squared": 0.9391,
        "rel_rmse": 0.286,
        "n_points": 7,
        "reliable": True,
    },
    "compressor_recip_5000psia": {
        "description": "Reciprocating compressor, 3 stages, 5000 psia discharge, MW 30",
        "size_unit": "actual ft3/min",
        "exponent": 0.7766,
        "base_size": 1343.0,
        "base_cost": 1317400.0,
        "valid_min": 250.0,
        "valid_max": 7000.0,
        "r_squared": 0.9946,
        "rel_rmse": 0.0769,
        "n_points": 5,
        "reliable": True,
    },
    "blower_rotary": {
        "description": "Rotary (lobe) blower, CI casing / ductile iron impellers, 8 psig exit, incl. silencers",
        "size_unit": "actual ft3/min",
        "exponent": 0.5392,
        "base_size": 1031.0,
        "base_cost": 16035.0,
        "valid_min": 100.0,
        "valid_max": 4000.0,
        "r_squared": 0.9933,
        "rel_rmse": 0.0542,
        "n_points": 6,
        "reliable": True,
    },
    "fan_centrifugal": {
        "description": "Centrifugal fan, CS, 6 in H2O exit pressure, 1800 rpm",
        "size_unit": "actual ft3/min",
        "exponent": 0.7346,
        "base_size": 16130.0,
        "base_cost": 6199.8,
        "valid_min": 700.0,
        "valid_max": 150000.0,
        "r_squared": 0.9381,
        "rel_rmse": 0.3622,
        "n_points": 9,
        "reliable": True,
    },

    # ----------------------------------------------------------------------
    # Heat transfer equipment
    # ----------------------------------------------------------------------
    "hx_shell_tube": {
        "description": "Shell & tube heat exchanger, floating/fixed head, CS, 150 psig, 650 F",
        "size_unit": "ft2",
        "exponent": 0.7077,
        "base_size": 3455.0,
        "base_cost": 66278.0,
        "valid_min": 100.0,
        "valid_max": 70000.0,
        "r_squared": 0.9516,
        "rel_rmse": 0.2725,
        "n_points": 26,
        "reliable": True,
    },
    "hx_air_cooler": {
        "description": "Air cooler (fin-fan), CS tubes, 150 psig, 300 F inlet",
        "size_unit": "ft2 bare tube",
        "exponent": 0.533,
        "base_size": 1022.0,
        "base_cost": 49781.0,
        "valid_min": 100.0,
        "valid_max": 10000.0,
        "r_squared": 0.9479,
        "rel_rmse": 0.155,
        "n_points": 15,
        "reliable": True,
    },
    "hx_spiral_plate": {
        "description": "Spiral plate heat exchanger, SS304, 150 psig",
        "size_unit": "ft2",
        "exponent": 0.6596,
        "base_size": 258.9,
        "base_cost": 19267.0,
        "valid_min": 40.0,
        "valid_max": 700.0,
        "r_squared": 0.9645,
        "rel_rmse": 0.1192,
        "n_points": 8,
        "reliable": True,
    },
    "evaporator_vertical_tube": {
        "description": "Standard vertical-tube evaporator, CS",
        "size_unit": "ft2",
        "exponent": 0.5494,
        "base_size": 1565.0,
        "base_cost": 283750.0,
        "valid_min": 100.0,
        "valid_max": 6000.0,
        "r_squared": 1.0,
        "rel_rmse": 0.0001,
        "n_points": 8,
        "reliable": True,
    },
    "evaporator_horizontal_tube": {
        "description": "Standard horizontal-tube evaporator, CS",
        "size_unit": "ft2",
        "exponent": 0.5301,
        "base_size": 2743.0,
        "base_cost": 199800.0,
        "valid_min": 100.0,
        "valid_max": 10000.0,
        "r_squared": 1.0,
        "rel_rmse": 0.0005,
        "n_points": 12,
        "reliable": True,
    },
    "furnace_fired_heater": {
        "description": "Gas/oil fired vertical cylindrical process heater, refractory lined, 500 psig",
        "size_unit": "MMBtu/h",
        "exponent": 0.6407,
        "base_size": 67.73,
        "base_cost": 931580.0,
        "valid_min": 2.0,
        "valid_max": 500.0,
        "r_squared": 0.9836,
        "rel_rmse": 0.1474,
        "n_points": 9,
        "reliable": True,
    },
    "cooling_tower": {
        "description": "Factory-assembled cooling tower incl. fans, drivers, basin; 15 F range / 10 F approach",
        "size_unit": "gal/min",
        "exponent": 0.886,
        "base_size": 1391.0,
        "base_cost": 25868.0,
        "valid_min": 150.0,
        "valid_max": 6000.0,
        "r_squared": 0.9975,
        "rel_rmse": 0.0549,
        "n_points": 9,
        "reliable": True,
    },
    "boiler_package_steam": {
        "description": "Package steam boiler, 250 psig, 100 F superheat, shop assembled",
        "size_unit": "lb/h steam",
        "exponent": 0.6391,
        "base_size": 85340.0,
        "base_cost": 325190.0,
        "valid_min": 10000.0,
        "valid_max": 300000.0,
        "r_squared": 0.9842,
        "rel_rmse": 0.0933,
        "n_points": 8,
        "reliable": True,
    },

    # ----------------------------------------------------------------------
    # Vessels, separators and tanks
    # ----------------------------------------------------------------------
    "vessel_vertical_15psig": {
        "description": "Vertical pressure vessel, CS A515, 15 psig, 650 F, L/D~3 (incl. heads, skirt, nozzles)",
        "size_unit": "gal",
        "exponent": 0.3161,
        "base_size": 1013.0,
        "base_cost": 12690.0,
        "valid_min": 100.0,
        "valid_max": 5000.0,
        "r_squared": 0.9847,
        "rel_rmse": 0.05,
        "n_points": 9,
        "reliable": True,
    },
    "vessel_vertical_150psig": {
        "description": "Vertical pressure vessel, CS A515, 150 psig, 650 F",
        "size_unit": "gal",
        "exponent": 0.3857,
        "base_size": 1013.0,
        "base_cost": 15573.0,
        "valid_min": 100.0,
        "valid_max": 5000.0,
        "r_squared": 0.9869,
        "rel_rmse": 0.0555,
        "n_points": 9,
        "reliable": True,
    },
    "vessel_horizontal_15psig": {
        "description": "Horizontal drum / KO separator, CS A515, 15 psig, 650 F, saddle supported",
        "size_unit": "gal",
        "exponent": 0.405,
        "base_size": 4099.0,
        "base_cost": 21440.0,
        "valid_min": 100.0,
        "valid_max": 100000.0,
        "r_squared": 0.9879,
        "rel_rmse": 0.0925,
        "n_points": 13,
        "reliable": True,
    },
    "vessel_horizontal_150psig": {
        "description": "Horizontal drum / KO separator, CS A515, 150 psig, 650 F",
        "size_unit": "gal",
        "exponent": 0.5742,
        "base_size": 4099.0,
        "base_cost": 34904.0,
        "valid_min": 100.0,
        "valid_max": 100000.0,
        "r_squared": 0.9754,
        "rel_rmse": 0.1859,
        "n_points": 13,
        "reliable": True,
    },
    "tank_storage_cone_roof": {
        "description": "Cone-roof atmospheric storage tank, field fabricated CS (<2 psia vapour pressure)",
        "size_unit": "gal",
        "exponent": 0.7154,
        "base_size": 494200.0,
        "base_cost": 179410.0,
        "valid_min": 50000.0,
        "valid_max": 10000000.0,
        "r_squared": 0.9868,
        "rel_rmse": 0.1362,
        "n_points": 9,
        "reliable": True,
    },
    "tank_storage_floating_roof": {
        "description": "Floating-roof storage tank, CS (2-15 psia vapour pressure)",
        "size_unit": "gal",
        "exponent": 0.5378,
        "base_size": 494200.0,
        "base_cost": 321640.0,
        "valid_min": 50000.0,
        "valid_max": 10000000.0,
        "r_squared": 0.9637,
        "rel_rmse": 0.1735,
        "n_points": 9,
        "reliable": True,
    },

    # ----------------------------------------------------------------------
    # Solid-liquid separation
    # ----------------------------------------------------------------------
    "filter_rotary_drum_vacuum": {
        "description": "Rotary vacuum drum filter, multi-compartment, PP cloth, medium filtration rate",
        "size_unit": "ft2",
        "exponent": 0.4134,
        "base_size": 600.4,
        "base_cost": 130880.0,
        "valid_min": 100.0,
        "valid_max": 2000.0,
        "r_squared": 0.9956,
        "rel_rmse": 0.0268,
        "n_points": 7,
        "reliable": True,
    },
    "filter_cartridge": {
        "description": "Cartridge filter, 5 micron cotton element",
        "size_unit": "ft3/min",
        "exponent": 0.5072,
        "base_size": 289.0,
        "base_cost": 3045.4,
        "valid_min": 30.0,
        "valid_max": 1200.0,
        "r_squared": 0.9575,
        "rel_rmse": 0.1471,
        "n_points": 6,
        "reliable": True,
    },
    "filter_tubular_fabric": {
        "description": "Tubular fabric filter (baghouse), bank of three, no auto-clean",
        "size_unit": "ft3/min",
        "exponent": 0.6525,
        "base_size": 1183.0,
        "base_cost": 27562.0,
        "valid_min": 100.0,
        "valid_max": 3400.0,
        "r_squared": 1.0,
        "rel_rmse": 0.0005,
        "n_points": 8,
        "reliable": True,
    },
    "centrifuge_vibratory": {
        "description": "Continuous filtration vibratory centrifuge, CS",
        "size_unit": "in screen dia.",
        "exponent": 3.1593,
        "base_size": 51.92,
        "base_cost": 75112.0,
        "valid_min": 48.0,
        "valid_max": 56.0,
        "r_squared": 1.0,
        "rel_rmse": 0.0003,
        "n_points": 5,
        "reliable": False,
        "caution": "exponent outside 0.25-1.05; narrow size span (1.2x)",
    },

    # ----------------------------------------------------------------------
    # Solids handling
    # ----------------------------------------------------------------------
    "dryer_rotary_direct": {
        "description": "Direct-contact rotary dryer incl. motor and drive",
        "size_unit": "ft2",
        "exponent": 0.9538,
        "base_size": 705.1,
        "base_cost": 170780.0,
        "valid_min": 100.0,
        "valid_max": 2000.0,
        "r_squared": 1.0,
        "rel_rmse": 0.0003,
        "n_points": 6,
        "reliable": True,
    },
    "mill_ball": {
        "description": "Ball mill incl. bearings, gears, lube system, initial ball charge",
        "size_unit": "hp",
        "exponent": 0.7414,
        "base_size": 97.4,
        "base_cost": 174810.0,
        "valid_min": 7.5,
        "valid_max": 450.0,
        "r_squared": 0.9958,
        "rel_rmse": 0.0703,
        "n_points": 8,
        "reliable": True,
    },
    "mill_roller": {
        "description": "Roller mill incl. bearings, gears, lube system",
        "size_unit": "hp",
        "exponent": 0.6113,
        "base_size": 170.3,
        "base_cost": 177470.0,
        "valid_min": 30.0,
        "valid_max": 400.0,
        "r_squared": 1.0,
        "rel_rmse": 0.0001,
        "n_points": 8,
        "reliable": True,
    },
    "crusher_gyratory": {
        "description": "Gyratory crusher (hard/medium-hard feed) incl. motor and drive",
        "size_unit": "hp",
        "exponent": 1.3889,
        "base_size": 335.2,
        "base_cost": 636350.0,
        "valid_min": 40.0,
        "valid_max": 1250.0,
        "r_squared": 0.9963,
        "rel_rmse": 0.0958,
        "n_points": 6,
        "reliable": False,
        "caution": "exponent outside 0.25-1.05",
    },
    "crusher_ring_granulator": {
        "description": "Ring granulator (coal, lignite, gypsum) incl. motor and drive",
        "size_unit": "hp",
        "exponent": 0.9372,
        "base_size": 347.4,
        "base_cost": 110970.0,
        "valid_min": 75.0,
        "valid_max": 1250.0,
        "r_squared": 0.99,
        "rel_rmse": 0.0961,
        "n_points": 6,
        "reliable": True,
    },
    "agitator": {
        "description": "Fixed propeller mixer, 1800 rpm, incl. motor, gear drive, shaft, impeller",
        "size_unit": "hp",
        "exponent": 0.5388,
        "base_size": 23.92,
        "base_cost": 24900.0,
        "valid_min": 2.0,
        "valid_max": 100.0,
        "r_squared": 0.9537,
        "rel_rmse": 0.1669,
        "n_points": 6,
        "reliable": True,
    },

    # ----------------------------------------------------------------------
    # Drivers and power recovery
    # ----------------------------------------------------------------------
    "turbine_gas": {
        "description": "Gas turbine incl. fuel-gas combustion chamber and multistage expander",
        "size_unit": "hp",
        "exponent": 0.7951,
        "base_size": 63930.0,
        "base_cost": 10718000.0,
        "valid_min": 1000.0,
        "valid_max": 370000.0,
        "r_squared": 0.9949,
        "rel_rmse": 0.1135,
        "n_points": 11,
        "reliable": True,
    },
    "turbine_steam_large": {
        "description": "Steam turbine driver >1000 hp, 400 psig, 3600 rpm, incl. condenser",
        "size_unit": "hp",
        "exponent": 0.941,
        "base_size": 7341.0,
        "base_cost": 684510.0,
        "valid_min": 1000.0,
        "valid_max": 30000.0,
        "r_squared": 0.9841,
        "rel_rmse": 0.1291,
        "n_points": 8,
        "reliable": True,
    },
    "turbine_steam_small": {
        "description": "Steam turbine driver <1000 hp, 400 psig, 3600 rpm, incl. condenser",
        "size_unit": "hp",
        "exponent": 0.1738,
        "base_size": 118.9,
        "base_cost": 29349.0,
        "valid_min": 10.0,
        "valid_max": 950.0,
        "r_squared": 1.0,
        "rel_rmse": 0.001,
        "n_points": 5,
        "reliable": False,
        "caution": "exponent outside 0.25-1.05",
    },
}


#: Convenience aliases so that everyday words resolve to a correlation.
ALIASES: dict[str, str] = {
    "pump":                    "pump_centrifugal",
    "centrifugal pump":        "pump_centrifugal",
    "blower":                  "blower_rotary",
    "fan":                     "fan_centrifugal",
    "compressor":              "compressor_centrifugal_150psia",
    "centrifugal compressor":  "compressor_centrifugal_150psia",
    "reciprocating compressor":"compressor_recip_440psia",
    "heat exchanger":          "hx_shell_tube",
    "exchanger":               "hx_shell_tube",
    "air cooler":              "hx_air_cooler",
    "condenser":               "hx_shell_tube",
    "reboiler":                "hx_shell_tube",
    "vessel":                  "vessel_vertical_150psig",
    "drum":                    "vessel_horizontal_150psig",
    "separator":               "vessel_horizontal_150psig",
    "knockout drum":           "vessel_horizontal_150psig",
    "flash drum":              "vessel_vertical_150psig",
    "reflux drum":             "vessel_horizontal_150psig",
    "tank":                    "tank_storage_cone_roof",
    "storage tank":            "tank_storage_cone_roof",
    "filter":                  "filter_rotary_drum_vacuum",
    "baghouse":                "filter_tubular_fabric",
    "centrifuge":              "centrifuge_vibratory",
    "dryer":                   "dryer_rotary_direct",
    "mill":                    "mill_ball",
    "crusher":                 "crusher_ring_granulator",
    "furnace":                 "furnace_fired_heater",
    "fired heater":            "furnace_fired_heater",
    "boiler":                  "boiler_package_steam",
    "cooling tower":           "cooling_tower",
    "evaporator":              "evaporator_horizontal_tube",
    "gas turbine":             "turbine_gas",
    "steam turbine":           "turbine_steam_large",
    "expander":                "turbine_steam_large",
    "mixer":                   "agitator",
}


def resolve(name: str) -> str:
    """Map a free-text equipment name onto an EQUIPMENT key."""
    key = name.strip().lower().replace("-", " ").replace("_", " ")
    if name in EQUIPMENT:
        return name
    compact = key.replace(" ", "_")
    if compact in EQUIPMENT:
        return compact
    if key in ALIASES:
        return ALIASES[key]
    raise KeyError(
        f"Unknown equipment {name!r}. Try one of: "
        f"{', '.join(sorted(EQUIPMENT)[:6])}, ... "
        f"(see tea.equipment.catalogue())"
    )


# ============================================================================
# Multi-column (two-parameter) correlations
# ============================================================================
# A distillation or absorption column does not have one "size" -- cost depends
# on BOTH diameter and height/stage count, and the two scale very differently.
# Forcing a single-parameter power law onto a column is a common and material
# error, so these are fitted as
#
#     C = base_cost * (D/D_base)**exp_1 * (S/S_base)**exp_2
#
# where D is shell diameter (ft) and S is either the number of trays or the
# packed height (ft). Fitted from the same DOE/NETL-2002/1169 Appendix B
# tables as EQUIPMENT above; 1st Quarter 1998 US$, carbon steel, 650 F.
#
# The diameter exponents come out at 1.37-1.68 for tray columns -- well ABOVE
# 1.0, because shell wall thickness must rise with diameter at a given design
# pressure, so mass grows faster than area. Diameter is where column cost
# lives; stage count is a weak lever (exponent ~0.5).
#
# Tray costs are included in the tray-column correlations. Packing is NOT
# included in the packed-column correlations -- add it from PACKING_COST below.

COLUMNS: dict[str, dict] = {
    "column_valve_tray_15psig": {
        "description": "Valve tray distillation column, CS, 15 psig, 650 F, 24 in tray spacing (shell + trays)",
        "kind": "tray",
        "size_unit_1": "ft diameter",
        "size_unit_2": "number of trays",
        "exponent_1": 1.3874,
        "exponent_2": 0.5597,
        "base_size_1": 11.07,
        "base_size_2": 19.67,
        "base_cost": 231810.0,
        "valid_1": (5.0, 20.0),
        "valid_2": (2.0, 60.0),
        "r_squared": 0.9758,
        "rel_rmse": 0.141,
        "n_points": 44,
    },
    "column_valve_tray_150psig": {
        "description": "Valve tray distillation column, CS, 150 psig, 650 F, 24 in tray spacing",
        "kind": "tray",
        "size_unit_1": "ft diameter",
        "size_unit_2": "number of trays",
        "exponent_1": 1.677,
        "exponent_2": 0.5053,
        "base_size_1": 11.07,
        "base_size_2": 19.67,
        "base_cost": 333520.0,
        "valid_1": (5.0, 20.0),
        "valid_2": (2.0, 60.0),
        "r_squared": 0.9783,
        "rel_rmse": 0.1486,
        "n_points": 44,
    },
    "column_sieve_tray_15psig": {
        "description": "Sieve tray distillation column, CS, 15 psig, 650 F, 24 in tray spacing",
        "kind": "tray",
        "size_unit_1": "ft diameter",
        "size_unit_2": "number of trays",
        "exponent_1": 1.3678,
        "exponent_2": 0.5535,
        "base_size_1": 11.07,
        "base_size_2": 19.67,
        "base_cost": 220870.0,
        "valid_1": (5.0, 20.0),
        "valid_2": (2.0, 60.0),
        "r_squared": 0.9739,
        "rel_rmse": 0.1446,
        "n_points": 44,
    },
    "column_sieve_tray_150psig": {
        "description": "Sieve tray distillation column, CS, 150 psig, 650 F, 24 in tray spacing",
        "kind": "tray",
        "size_unit_1": "ft diameter",
        "size_unit_2": "number of trays",
        "exponent_1": 1.6732,
        "exponent_2": 0.4991,
        "base_size_1": 11.07,
        "base_size_2": 19.67,
        "base_cost": 322620.0,
        "valid_1": (5.0, 20.0),
        "valid_2": (2.0, 60.0),
        "r_squared": 0.9774,
        "rel_rmse": 0.1511,
        "n_points": 44,
    },
    "column_packed_15psig": {
        "description": "Packed absorption column shell, CS, 15 psig, 650 F (packing NOT included)",
        "kind": "packed",
        "size_unit_1": "ft diameter",
        "size_unit_2": "ft packed height",
        "exponent_1": 0.8125,
        "exponent_2": 0.3689,
        "base_size_1": 2.426,
        "base_size_2": 23.28,
        "base_cost": 20987.0,
        "valid_1": (1.0, 3.5),
        "valid_2": (8.0, 68.0),
        "r_squared": 0.9762,
        "rel_rmse": 0.0734,
        "n_points": 27,
    },
    "column_packed_150psig": {
        "description": "Packed absorption column shell, CS, 150 psig, 650 F (packing NOT included)",
        "kind": "packed",
        "size_unit_1": "ft diameter",
        "size_unit_2": "ft packed height",
        "exponent_1": 0.8655,
        "exponent_2": 0.3815,
        "base_size_1": 2.426,
        "base_size_2": 23.28,
        "base_cost": 22913.0,
        "valid_1": (1.0, 3.5),
        "valid_2": (8.0, 68.0),
        "r_squared": 0.9639,
        "rel_rmse": 0.095,
        "n_points": 27,
    },
}

#: Uninstalled packing cost, US$ per cubic foot, 1st Quarter 1998.
#: Source: DOE/NETL-2002/1169, Table 1. Keys are nominal packing size in inches.
PACKING_COST: dict[str, dict[float, float]] = {
    "pall rings polypropylene": {0.5: 33, 1.0: 29, 1.5: 21, 2.0: 8},
    "pall rings stainless":     {0.5: 130, 1.0: 118, 1.5: 92, 2.0: 76},
    "intalox saddles ceramic":  {0.5: 31, 1.0: 28, 1.5: 23, 2.0: 21},
    "intalox saddles porcelain":{0.5: 32, 1.0: 29, 1.5: 24, 2.0: 21},
    "raschig rings ceramic":    {0.5: 119, 1.0: 14, 1.5: 12, 2.0: 12, 3.0: 11},
    "raschig rings porcelain":  {1.0: 17, 1.5: 15, 2.0: 12, 3.0: 11},
    "raschig rings stainless":  {1.0: 111, 1.5: 94, 2.0: 59, 3.0: 54},
    "raschig rings carbon steel": {1.0: 37, 1.5: 31, 2.0: 20, 3.0: 18},
}

#: Adsorbent cost, US$ per cubic foot, 1st Quarter 1998 (same table).
ADSORBENT_COST: dict[str, float] = {
    "activated carbon": 25.0,
    "13x molecular sieve": 61.0,
    "silica gel": 94.0,
    "calcium chloride": 11.0,
}
