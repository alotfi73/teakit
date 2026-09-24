"""
teakit.project — One object that holds a whole study and runs it end to end.
===========================================================================

The other modules are deliberately free functions and small dataclasses, because
that is what you want when you are checking one number. This module is the other
thing you want: a single container holding the equipment list, the capital
configuration, the operating cost model, the product slate and the financing
assumptions, which can be saved to JSON, mutated by name, and re-run.

That last property is what makes sensitivity analysis and the graphical
application possible. Every input is addressable by a dotted path::

    p["finance.discount_rate"] = 0.12
    p["opex.utilities.electricity.price"] = 0.095
    p["equipment.K-101.size"] = 15_000

so :mod:`teakit.sensitivity` can sweep anything without knowing what it is, and
the app can build its forms from :meth:`Project.parameters` rather than
hard-coding a field list.

THE PIPELINE
------------
::

    equipment list                       teakit.equipment
        -> purchased equipment cost
        -> installed cost / BEC          teakit.capital
        -> EPCC -> TPC -> TOC -> TASC    teakit.capital
        -> annual operating cost         teakit.opex
        -> levelised cost or MSP         teakit.levelized / teakit.dcf
        -> allocation across products    teakit.products

Three costing methods are available and they do not agree with each other. That
is not a defect — see :meth:`ProjectResult.method_comparison`, which runs all
three on the same inputs so the spread is visible rather than hidden.

    ``"dcf"``      full after-tax cash flow, price solved at NPV = 0.
                   The most rigorous, and the NREL convention.
    ``"fcr"``      fixed charge rate against TASC, plus annual O&M.
                   The NETL convention. Faster, and transparent.
    ``"crf"``      annualised capital via the capital recovery factor, plus
                   annual O&M, less byproduct revenue, over production. The
                   textbook annuity form and the NREL ATB convention. Charges
                   the cost of capital but not tax.
    ``"simple"``   capital divided by life, no cost of capital at all.
                   Only for screening; it will understate by 30-50%.
"""

from __future__ import annotations

import copy as _copy
import json
from dataclasses import dataclass, field, asdict

from . import capital as _capital
from . import currency as _currency
from . import dcf as _dcf
from . import defaults as _defaults
from . import equipment as _equipment
from . import equipment_data as _eqdata
from . import indices as _indices
from . import levelized as _lev
from . import opex as _opex
from . import products as _products

__all__ = [
    "EquipmentItem", "EquipmentParameter", "EquipmentUtility",
    "EquipmentConsumable", "CapitalConfig", "FinanceConfig",
    "Project", "ProjectResult", "COSTING_METHODS",
]

COSTING_METHODS = ("dcf", "fcr", "crf", "simple")


# ============================================================================
# 1. Inputs
# ============================================================================
@dataclass
class EquipmentParameter:
    """
    One named process parameter on an equipment item — power, inlet flow, duty,
    area, temperature, pressure.

    These do not enter the cost correlation. The parameter that *does* is the
    item's :attr:`EquipmentItem.size`, which is a separate field precisely so
    that the number driving the cost cannot be lost in a list of others. What
    these are for is the rest of the picture: the report's equipment schedule,
    the basis of a utility figure sitting beside them, and a place for a
    flowsheet import to put what it knows.

    >>> EquipmentParameter("duty", 4100.0, "kW").label()
    'duty = 4,100 kW'
    """
    name: str
    value: float = 0.0
    unit: str = ""
    note: str = ""

    def label(self) -> str:
        """One-line rendering, for a table cell or a report row."""
        v = f"{self.value:,.4g}" if isinstance(self.value, (int, float)) else self.value
        return f"{self.name} = {v}{' ' + self.unit if self.unit else ''}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EquipmentParameter":
        if not isinstance(d, dict):
            raise TypeError(f"parameter must be an object, got {type(d).__name__}")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


#: Catalogue key families, spelled out. The key prefix is an identifier -
#: "hx" is a heat exchanger and nobody outside the file calls it that - and
#: this is the label a chart legend or a report table should carry.
CATEGORY_LABELS: dict[str, str] = {
    "agitator": "agitator", "blower": "blower", "boiler": "boiler",
    "centrifuge": "centrifuge", "compressor": "compressor",
    "cooling": "cooling tower", "crusher": "crusher", "dryer": "dryer",
    "evaporator": "evaporator", "fan": "fan", "filter": "filter",
    "furnace": "fired heater", "hx": "heat exchanger", "mill": "mill",
    "pump": "pump", "tank": "tank", "turbine": "turbine",
    "vessel": "vessel",
}


@dataclass
class EquipmentConsumable:
    """
    A part an equipment item consumes and has to have replaced: electrodes in
    a plasma reactor, a catalyst charge, membranes in an electrolyser, filter
    elements, a mill liner.

    It is not a utility — nothing flows through a meter — and it is not
    capital, because it is bought again and again over the plant's life. It is
    an operating cost with a *schedule*, and the schedule is the only thing
    that makes it different from any other consumable: a set of electrodes
    replaced every 18 months costs two-thirds of a set per year.

        annual cost = quantity x unit cost x running units / interval

    ``interval_years`` is what the interval is expressed in, so quarterly is
    0.25 and "every four years" is 4. It must be positive; a part that is never
    replaced is capital, not a consumable.

    ``scales_with_rate`` decides whether the schedule is driven by run time or
    by the calendar. Electrodes wear while the plant runs, so the default is
    True and a plant at 80% capacity replaces them 80% as often. A part that
    ages on the shelf - a desiccant, a certificate-driven replacement - should
    be set False.

    >>> c = EquipmentConsumable("electrodes", quantity=6, unit="set",
    ...                         unit_cost=42_000, interval_years=1.5)
    >>> round(c.annual_cost(quantity=1))
    168000
    >>> round(c.annual_cost(quantity=2))
    336000
    """
    name: str
    quantity: float = 1.0
    unit: str = ""
    unit_cost: float = 0.0
    interval_years: float = 1.0
    per_unit: bool = True
    scales_with_rate: bool = True
    category: str = "catalyst"          # where it lands in the opex rollup
    source: str = ""
    note: str = ""

    def interval_label(self) -> str:
        """The interval as a person would say it."""
        y = float(self.interval_years or 0)
        if y <= 0:
            return "no interval set"
        if abs(y - round(y)) < 1e-9:
            n = int(round(y))
            return "every year" if n == 1 else f"every {n} years"
        months = y * 12
        if abs(months - round(months)) < 1e-6:
            m = int(round(months))
            return "every month" if m == 1 else f"every {m} months"
        return f"every {y:g} years"

    def annual_quantity(self, quantity: int = 1) -> float:
        """Replacement units consumed per year, before the capacity factor."""
        if not self.interval_years or self.interval_years <= 0:
            return 0.0
        n = (max(int(quantity), 0) if self.per_unit else 1)
        return float(self.quantity) * n / float(self.interval_years)

    def as_stream(self, tag: str = "", quantity: int = 1) -> _opex.Stream:
        """
        This part as an annual operating-cost stream.

        ``basis="year"`` because the rate above is already a per-year figure:
        the schedule, not the clock, sets how much is bought.
        """
        label = f"{self.name} — {tag}" if tag else self.name
        return _opex.Stream(
            name=label, rate=self.annual_quantity(quantity),
            unit=self.unit or "unit", price=float(self.unit_cost or 0.0),
            category=self.category or "catalyst", basis="year",
            scales_with_rate=self.scales_with_rate,
            source=self.source or f"replaced {self.interval_label()}",
            note=self.note)

    def annual_cost(self, capacity_factor: float = 1.0, quantity: int = 1) -> float:
        """Annual cost of keeping this item in parts."""
        return self.as_stream("", quantity).annual_cost(0.0, capacity_factor)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EquipmentConsumable":
        if not isinstance(d, dict):
            raise TypeError(f"consumable must be an object, got {type(d).__name__}")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class EquipmentUtility:
    """
    One utility an equipment item consumes: electricity for a compressor,
    cooling water for a condenser, steam for a reboiler.

    It is deliberately the same shape as :class:`teakit.opex.Stream` — a rate, a
    unit, a price, a basis and a capacity-factor flag — because that is what it
    becomes when the project runs. The two things it adds are where it came
    from and how it multiplies:

    ``per_unit``
        ``True`` (the default) means ``rate`` is the draw of **one** unit, and
        the plant total is multiplied by the item's ``quantity``. Installed
        spares are *not* counted: a spare pump is bought and is in the capital,
        but it is not running and it is not drawing power. Set ``per_unit``
        false when you have already summed the bank.

    ``price``
        ``None`` — the default — means "look it up in the utility catalogue by
        name", so a change of tariff moves every item at once and no price is
        typed twice. Give a number to override it for this item alone.

    >>> u = EquipmentUtility("electricity", 6200.0, "kWh")
    >>> u.resolved_price()
    0.081
    >>> round(u.annual_cost(8000, 1.0, quantity=1))
    4017600
    """
    name: str
    rate: float = 0.0
    unit: str = ""
    price: float | None = None
    basis: str = "hour"                    # hour | year, as teakit.opex.Stream
    scales_with_rate: bool = True
    per_unit: bool = True
    category: str = "utility"              # utility | waste | raw_material | other
    source: str = ""
    note: str = ""

    # -- catalogue lookup ------------------------------------------------
    def catalogue_entry(self) -> dict | None:
        """The utility catalogue record behind this line, matched by name."""
        if not self.name:
            return None
        rec = _defaults.UTILITY_CATALOGUE.get(self.name)
        if rec is not None:
            return rec
        wanted = self.name.strip().lower()
        for k, v in _defaults.UTILITY_CATALOGUE.items():
            if k.lower() == wanted:
                return v
        return None

    def resolved_price(self, book: dict | None = None) -> float:
        """
        The price in force for this utility.

        ``book`` is the project's own price list — see
        :meth:`Project.utility_price_book`. It wins over the shipped
        catalogue, because a tariff the user typed is the tariff for the whole
        study; the catalogue is only a starting point. A price set on this
        line itself wins over both, but the interface no longer offers that:
        one utility, one price, is the point of the book.
        """
        if self.price is not None:
            return float(self.price)
        if book is not None and self.name in book:
            return float(book[self.name]["price"])
        rec = self.catalogue_entry()
        return float(rec["price"]) if rec else 0.0

    def resolved_unit(self, book: dict | None = None) -> str:
        """The unit in force. A blank unit takes the book's, then the catalogue's."""
        if self.unit:
            return self.unit
        if book is not None and self.name in book:
            return str(book[self.name]["unit"])
        rec = self.catalogue_entry()
        return str(rec["unit"]) if rec else ""

    def price_source(self, book: dict | None = None) -> str:
        """Provenance, for the report and for the line under the control."""
        if self.source:
            return self.source
        if self.price is not None:
            return "entered on this line, overriding the project price"
        if book is not None and self.name in book:
            return book[self.name]["source"]
        rec = self.catalogue_entry()
        return rec["source"] if rec else "no price — not in the utility catalogue"

    def is_priced(self, book: dict | None = None) -> bool:
        """False when nothing supplies a price, so the interface can say so."""
        return (self.price is not None
                or (book is not None and self.name in book)
                or self.catalogue_entry() is not None)

    # -- what the plant actually consumes --------------------------------
    def plant_rate(self, quantity: int = 1) -> float:
        """
        The rate for the whole bank, spares excluded.

        A negative rate is a *generation*: a turbine or an expander that puts
        power back rather than taking it. It costs a negative amount, which is
        a credit, and it is deliberately the same field — netting generation
        against consumption is what a utility balance is.
        """
        return float(self.rate) * (max(int(quantity), 0) if self.per_unit else 1)

    def generates(self) -> bool:
        """True when this line puts a utility back rather than drawing it."""
        return float(self.rate or 0.0) < 0

    def as_stream(self, tag: str = "", quantity: int = 1,
                  book: dict | None = None) -> _opex.Stream:
        """
        This line as an operating-cost stream, ready to price.

        The name carries the tag so the operating-cost table, the charts and
        the report all say which item the consumption came from.
        """
        label = f"{self.name} — {tag}" if tag else self.name
        return _opex.Stream(
            name=label, rate=self.plant_rate(quantity),
            unit=self.resolved_unit(book), price=self.resolved_price(book),
            category=self.category or "utility",
            basis=self.basis, scales_with_rate=self.scales_with_rate,
            source=self.price_source(book), note=self.note)

    def annual_cost(self, operating_hours: float, capacity_factor: float = 1.0,
                    quantity: int = 1, book: dict | None = None) -> float:
        """Annual cost of this line for the whole bank."""
        return self.as_stream("", quantity, book).annual_cost(operating_hours,
                                                              capacity_factor)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EquipmentUtility":
        if not isinstance(d, dict):
            raise TypeError(f"utility must be an object, got {type(d).__name__}")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class EquipmentItem:
    """
    One line of the equipment list. Three ways to define it, in increasing
    order of user effort and decreasing order of dependence on the catalogue:

    **1. Catalogue** — give ``kind`` (a key or alias from
    :data:`teakit.equipment_data.EQUIPMENT`) and a ``size``. The base cost, base
    size and scale factor come from the DOE/NETL regression.

    >>> EquipmentItem("P-101", kind="pump", size=1200).evaluate(2025)["cost"] > 0
    True

    **2. Catalogue, overridden** — same, but set any of ``base_cost``,
    ``base_size``, ``exponent`` or ``base_year`` and yours wins. Use this when
    you have a vendor quote at one size and want to scale it with the
    catalogue's exponent, or vice versa.

    >>> e = EquipmentItem("K-101", kind="compressor_centrifugal_150psia",
    ...                   size=8000, exponent=0.70)
    >>> e.evaluate(2025)["exponent"]
    0.7

    **3. From scratch** — set ``mode="custom"`` and supply ``base_cost``,
    ``base_size``, ``exponent`` and ``base_year``. No catalogue entry is
    consulted. This is how proprietary or technology-defining equipment enters
    the estimate.

    >>> e = EquipmentItem("EL-101", mode="custom", size=210_000,
    ...                   base_cost=2000*210_000, base_size=210_000,
    ...                   exponent=1.0, base_year=2022, size_unit="kW",
    ...                   cost_is_installed=True)
    >>> round(e.evaluate(2025)["cost"] / 1e6)
    417

    **4. Direct** — set ``mode="direct"`` and ``direct_cost``. No scaling at
    all; the number is used as given, escalated from ``base_year``.

    Parameters
    ----------
    cost_is_installed : bool
        Critical flag. A vendor's *installed* price must not go through the
        installation factors again. Items flagged installed bypass the
        purchased-to-installed step and enter the cascade directly at BEC.
        Mixing purchased and installed costs in one subtotal is the classic
        expensive error.
    """
    tag: str
    kind: str = ""
    size: float = 0.0
    quantity: int = 1
    spare: int = 0
    material: str = "carbon steel"
    mode: str = "catalogue"          # catalogue | custom | direct
    # overrides / custom correlation
    base_cost: float | None = None
    base_size: float | None = None
    exponent: float | None = None
    base_year: int | None = None
    size_unit: str = ""
    direct_cost: float | None = None
    cost_is_installed: bool = False
    #: Installed cost as a multiple of this item's purchased cost, when the
    #: capital model is installing item by item and you know better than the
    #: type default for this one machine. ``None`` takes the factor its
    #: equipment type carries. Ignored by the plant-wide methods, which apply
    #: one factor to the whole equipment list by construction.
    installation_factor: float | None = None
    section: str = "Process"
    #: What kind of machine this is — "pump", "compressor", "heat exchanger".
    #: Blank means "work it out from the catalogue key", so a catalogue item
    #: is categorised without anyone typing anything. It exists so an
    #: equipment list can be rolled up by type as well as by plant section:
    #: three blowers of different sizes are one line on a chart.
    category: str = ""
    name: str = ""
    note: str = ""
    #: Named process parameters that do not drive the cost — power, inlet flow,
    #: duty, area, temperature, pressure. The cost driver is ``size``, kept
    #: separate so it cannot be lost among them.
    parameters: list[EquipmentParameter] = field(default_factory=list)
    #: What this item consumes when it runs. These are priced and rolled into
    #: the operating cost; see :meth:`utility_streams`.
    utilities: list[EquipmentUtility] = field(default_factory=list)
    #: Parts it wears out and has replaced on a schedule — electrodes, a
    #: catalyst charge, membranes, liners. See :class:`EquipmentConsumable`.
    consumables: list[EquipmentConsumable] = field(default_factory=list)

    @property
    def total_quantity(self) -> int:
        """Units bought — duty plus installed spares. This is what costs money."""
        return self.quantity + self.spare

    @property
    def running_quantity(self) -> int:
        """
        Units running — duty only.

        Spares are in the capital and not in the utility bill. A 2+1 pump set is
        three pumps purchased and two pumps drawing power, and charging the
        plant for the third is a straightforward overstatement of operating
        cost.
        """
        return max(int(self.quantity), 0)

    @property
    def display_name(self) -> str:
        """What to call this item: your name, else the note, else the tag."""
        return (self.name or self.note or self.tag).strip() or self.tag

    @property
    def effective_category(self) -> str:
        """
        The type this item rolls up under.

        Yours if you set one. Otherwise the catalogue key's own family —
        ``blower_rotary`` and ``blower_centrifugal`` are both "blower", which
        is the grouping someone asking "what did the blowers cost" wants. An
        item with no catalogue behind it falls back to its mode, because
        "direct price" is at least an honest answer.
        """
        if self.category:
            return self.category.strip()
        if self.mode == "catalogue" and self.kind:
            try:
                key = _equipment.resolve(self.kind)
            except Exception:                              # noqa: BLE001
                key = self.kind
            family = key.split("_")[0]
            return CATEGORY_LABELS.get(family, family.replace("-", " "))
        return {"direct": "direct price",
                "custom": "user correlation"}.get(self.mode, "other")

    # ------------------------------------------------------------------
    # process parameters
    # ------------------------------------------------------------------
    def driver_parameter(self) -> EquipmentParameter:
        """
        The cost-driving size, presented as a parameter.

        The interface lists this beside :attr:`parameters` so one table shows
        everything known about the item, while the value itself stays in
        ``size`` where the correlation reads it.
        """
        unit = self.size_unit
        if not unit and self.mode == "catalogue" and self.kind:
            try:
                unit = _equipment.EQUIPMENT[_equipment.resolve(self.kind)]["size_unit"]
            except Exception:                    # noqa: BLE001 - unknown key
                unit = ""
        return EquipmentParameter(name="size", value=float(self.size),
                                  unit=unit or "", note="drives the cost")

    def all_parameters(self) -> list[EquipmentParameter]:
        """The cost driver first, then every other recorded parameter."""
        return [self.driver_parameter(), *self.parameters]

    def parameter(self, name: str) -> EquipmentParameter | None:
        """One parameter by name, case-insensitively. ``None`` if absent."""
        wanted = str(name).strip().lower()
        for prm in self.parameters:
            if prm.name.strip().lower() == wanted:
                return prm
        return None

    # ------------------------------------------------------------------
    # utilities
    # ------------------------------------------------------------------
    def utility_streams(self) -> list["_opex.Stream"]:
        """
        This item's consumption as operating-cost streams, spares excluded.

        Lines with no rate are dropped rather than carried as zeros: an empty
        row someone started and abandoned should not appear in the operating
        cost table or on a chart.
        """
        n = self.running_quantity
        return [u.as_stream(self.tag, n) for u in self.utilities if u.rate]

    def utility_cost(self, operating_hours: float,
                     capacity_factor: float = 1.0) -> float:
        """Annual cost of everything this item consumes."""
        return sum(st.annual_cost(operating_hours, capacity_factor)
                   for st in self.utility_streams())

    def unpriced_utilities(self, book: dict | None = None) -> list[str]:
        """Names of utility lines with a rate but nothing to price it at."""
        return [u.name or "(unnamed)" for u in self.utilities
                if u.rate and not u.is_priced(book)]

    # ------------------------------------------------------------------
    # consumable parts
    # ------------------------------------------------------------------
    def consumable_streams(self) -> list["_opex.Stream"]:
        """
        The parts this item eats, as annual operating-cost streams.

        Lines with no interval or no cost are dropped rather than carried as
        zeros — an abandoned half-filled row should not appear in the estimate.
        """
        n = self.running_quantity
        return [c.as_stream(self.tag, n) for c in self.consumables
                if c.interval_years and c.interval_years > 0 and c.unit_cost]

    def consumable_cost(self, capacity_factor: float = 1.0) -> float:
        """Annual cost of keeping this item in replacement parts."""
        return sum(st.annual_cost(0.0, capacity_factor)
                   for st in self.consumable_streams())

    def evaluate(self, year: int = 2025, location_factor: float = 1.0,
                 allow_extrapolation: bool = False) -> dict:
        """
        Cost this line. Returns a dict with the full audit trail: the base
        values used, the exponent, the escalation, and the final cost for all
        units.

        ``base_cost_year`` is the dollar-year the line was escalated *from* --
        1998 for a catalogue correlation, the quote's own year for a vendor
        price. It is on the row because it is the only honest way to say which
        cost indices a study actually depends on.
        """
        notes: list[str] = []
        n = self.total_quantity

        if self.mode == "direct":
            if self.direct_cost is None:
                raise ValueError(f"{self.tag}: mode='direct' needs direct_cost")
            by = self.base_year or year
            unit = _equipment.indices.escalate(self.direct_cost, by, year) \
                if by != year else self.direct_cost
            if by != year:
                notes.append(f"escalated {by}->{year} by CEPCI")
            return dict(tag=self.tag, description=self.note or "direct cost entry",
                        size=self.size, size_unit=self.size_unit, exponent=0.0,
                        base_cost=self.direct_cost, base_size=0.0,
                        base_cost_year=by,
                        unit_cost=unit, quantity=n, cost=unit * n,
                        installed=self.cost_is_installed, section=self.section,
                        material=self.material, notes=notes, mode="direct")

        if self.mode == "custom":
            missing = [k for k in ("base_cost", "base_size", "exponent")
                       if getattr(self, k) is None]
            if missing:
                raise ValueError(f"{self.tag}: mode='custom' needs {missing}")
            if self.base_size <= 0 or self.size <= 0:
                raise ValueError(f"{self.tag}: sizes must be positive")
            scaled = _equipment.scale_cost(self.base_cost, self.base_size,
                                           self.size, self.exponent)
            by = self.base_year or year
            unit = _equipment.indices.escalate(scaled, by, year) if by != year else scaled
            mf = _equipment.MATERIAL_FACTORS.get(
                self.material.strip().lower(), {}).get("other", 1.0)
            unit *= mf * location_factor
            notes.append(f"user correlation C = {self.base_cost:,.0f} "
                         f"(S/{self.base_size:,.4g})^{self.exponent:.3f}, "
                         f"{by} basis")
            if mf != 1.0:
                notes.append(f"material factor {mf:.2f} ({self.material})")
            return dict(tag=self.tag, description=self.note or "user correlation",
                        size=self.size, size_unit=self.size_unit,
                        exponent=self.exponent, base_cost=self.base_cost,
                        base_size=self.base_size, base_cost_year=by,
                        unit_cost=unit, quantity=n,
                        cost=unit * n, installed=self.cost_is_installed,
                        section=self.section, material=self.material,
                        notes=notes, mode="custom")

        # --- catalogue, with optional overrides -----------------------------
        key = _equipment.resolve(self.kind)
        rec = dict(_equipment.EQUIPMENT[key])
        overridden = []
        for attr, field_name in (("base_cost", "base_cost"),
                                 ("base_size", "base_size"),
                                 ("exponent", "exponent")):
            v = getattr(self, attr)
            if v is not None:
                rec[field_name] = v
                overridden.append(attr)
        base_year = self.base_year or _eqdata.BASIS_YEAR

        if overridden or self.base_year:
            scaled = _equipment.scale_cost(rec["base_cost"], rec["base_size"],
                                           self.size, rec["exponent"])
            unit = _equipment.indices.escalate(scaled, base_year, year)
            mf = _equipment.material_factor(key, self.material)
            unit *= mf * location_factor
            notes.append(f"catalogue entry {key} with overrides: "
                         f"{', '.join(overridden) or 'base_year'}")
            desc = rec.get("description", key)
            su = self.size_unit or rec.get("size_unit", "")
        else:
            r = _equipment.purchased_cost(
                key, self.size, year=year, material=self.material,
                location_factor=location_factor,
                allow_extrapolation=allow_extrapolation, quiet=True)
            unit = r.cost
            notes.extend(r.notes)
            desc, su = r.description, r.size_unit

        return dict(tag=self.tag, description=desc, size=self.size, size_unit=su,
                    exponent=rec["exponent"], base_cost=rec["base_cost"],
                    base_size=rec["base_size"], base_cost_year=base_year,
                    unit_cost=unit, quantity=n,
                    cost=unit * n, installed=self.cost_is_installed,
                    section=self.section, material=self.material,
                    notes=notes, mode="catalogue", catalogue_key=key)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EquipmentItem":
        """
        Rebuild from JSON. Projects written before parameters and utilities
        existed simply have neither key and load unchanged.
        """
        kw = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        kw["parameters"] = [EquipmentParameter.from_dict(x)
                            for x in (kw.get("parameters") or [])
                            if isinstance(x, dict)]
        kw["utilities"] = [EquipmentUtility.from_dict(x)
                           for x in (kw.get("utilities") or [])
                           if isinstance(x, dict)]
        kw["consumables"] = [EquipmentConsumable.from_dict(x)
                             for x in (kw.get("consumables") or [])
                             if isinstance(x, dict)]
        return cls(**kw)


@dataclass
class CapitalConfig:
    """
    How purchased equipment becomes total capital.

    ``installation_method`` picks the purchased -> installed step:

    ``"loh"``     DOE/NETL distributive factors, one service and one
                  setting-labour class for the whole equipment list. The
                  default, and what every earlier version of teakit did.
    ``"type"``    the same factors, but resolved per item from its equipment
                  type, so a conveyor is not installed at a fired heater's
                  factor. Any type's factor, or any single item's, can be
                  overridden. See :meth:`Project.installation_factors`.
    ``"lang"``    one Lang factor for the whole plant. Order-of-magnitude.
    ``"factor"``  a single user-supplied installation factor.

    The three plant-wide methods multiply the whole purchased total by one
    number. ``"type"`` is the only one that gives two machines different
    factors, which is the point of it: bulk material and setting labour are
    not the same fraction of a pump's cost as of a crusher's.
    """
    installation_method: str = "loh"
    loh_service: str = "gas_lt400F_lt150psig"
    loh_setting: str = "heat exchanger"
    lang_type: str = "fluid processing"
    installation_factor: float = 3.0
    #: Installed-cost multiples by equipment type, for
    #: ``installation_method="type"``. Anything absent takes the factor
    #: :func:`teakit.equipment.type_installation_basis` derives for that type
    #: from DOE/NETL-2002/1169; anything present is yours and is saved with
    #: the study, so a reviewer sees which types you overrode and to what.
    type_installation_factors: dict[str, float] = field(default_factory=dict)

    epc_fee_frac: float = 0.175
    process_contingency_frac: float = 0.0
    project_contingency_frac: float = 0.20

    preproduction_frac_tpc: float = 0.02
    spare_parts_frac_tpc: float = 0.005
    financing_frac_tpc: float = 0.027
    other_owners_frac_tpc: float = 0.15
    #: What the site costs, as an absolute amount in project dollars -- not an
    #: area, and not a fraction of anything. It is added to owner's costs whole
    #: and is not depreciated.
    land_cost: float = 0.0
    #: How that amount was arrived at, when it was arrived at by the acre:
    #: area in acres and price per acre. They are provenance, carried so the
    #: working is saved with the study and can be re-opened and adjusted --
    #: :attr:`land_cost` remains the number the model reads, so a sweep or a
    #: sensitivity on land moves the figure that is actually used.
    #: NETL's rural benchmark is $3,000/acre.
    land_area_acres: float = 0.0
    land_cost_per_acre: float = 3000.0
    extra_owners_costs: dict[str, float] = field(default_factory=dict)

    basis: str = "real"
    wacc_pretax: float | None = None
    capital_escalation: float | None = None
    spend_profile: list[float] | None = None
    escalation_offset: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CapitalConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class FinanceConfig:
    """Financing, tax and timing. Load a published basis with
    :meth:`Project.apply_finance_preset`."""
    discount_rate: float = 0.10
    tax_rate: float = 0.2574
    depreciation_years: int = 7
    plant_life_years: int = 30
    construction_years: int = 3
    debt_frac: float = 0.0
    debt_interest_rate: float = 0.075
    debt_term_years: int = 12
    working_capital_frac: float = 0.05
    startup_revenue_frac: float = 0.50
    startup_variable_cost_frac: float = 0.75
    startup_fixed_cost_frac: float = 1.00
    salvage_frac: float = 0.0
    basis: str = "real"
    inflation: float = 0.03
    preset: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FinanceConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ============================================================================
# 2. Result
# ============================================================================
@dataclass
class ProjectResult:
    """Everything a run produces. Serialisable, chartable, printable."""
    name: str
    method: str
    currency: str
    dollar_year: int
    equipment_rows: list[dict]
    purchased_equipment_cost: float
    installed_direct: float
    bec: float
    capital: _capital.CapitalResult
    opex: _opex.OpexResult
    allocation: _products.AllocationResult
    unit_cost: float
    unit: str
    product: str
    annual_production: float
    capital_component: float
    fixed_component: float
    variable_component: float
    byproduct_component: float
    cash_flow: _dcf.DCFResult | None = None
    charge_rate: float | None = None
    charge_rate_name: str = ""
    #: One row per equipment utility line, priced. This is what lets the
    #: operating cost say which item each figure came from, rather than
    #: presenting an unattributable plant total.
    equipment_utilities: list[dict] = field(default_factory=list)
    #: One row per replacement part, annualised over its interval.
    equipment_consumables: list[dict] = field(default_factory=list)
    #: One entry per utility: its annual quantity and cost, and which items
    #: draw it. See :meth:`Project.utility_distribution`.
    utility_distribution: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exchange_rate: float = 1.0
    exchange_rate_source: str = "USD base"
    #: Installed cost over purchased cost for the items that went through
    #: installation. Dimensionless, so currency conversion leaves it alone.
    installation_factor: float = 1.0

    # -- currency --------------------------------------------------------
    def convert_currency(self, rate: float, code: str,
                         source: str = "manual") -> "ProjectResult":
        """
        Restate every monetary field from USD into ``code``, in place.

        ``rate`` is units of ``code`` per USD, so it multiplies. This is a
        presentation step applied to a finished result — see
        :mod:`teakit.currency` for where a rate should come from, and for why a
        converted US-basis estimate is still a US-basis estimate.

        Ratios, physical quantities, years, headcount, IRR and the TASC/TOC
        factor are dimensionless or non-monetary and are deliberately left
        alone. Calling this twice compounds the rate, so :meth:`Project.run`
        applies it exactly once.

        >>> import teakit
        >>> r = teakit.demo().run()
        >>> toc_usd = r.capital.toc
        >>> _ = r.convert_currency(0.9, "EUR", "test")
        >>> round(r.capital.toc / toc_usd, 6), r.currency
        (0.9, 'EUR')
        """
        if rate <= 0:
            raise ValueError(f"exchange rate must be positive, got {rate}")

        def money(v):
            return v * rate if isinstance(v, (int, float)) else v

        def scale_obj(obj, keys):
            for k in keys:
                v = getattr(obj, k, None)
                if isinstance(v, list):
                    setattr(obj, k, [money(x) for x in v])
                elif isinstance(v, dict):
                    setattr(obj, k, {kk: money(vv) for kk, vv in v.items()})
                elif isinstance(v, (int, float)):
                    setattr(obj, k, money(v))

        for row in self.equipment_rows:
            for k in ("unit_cost", "cost", "base_cost", "installed_cost"):
                if isinstance(row.get(k), (int, float)):
                    row[k] = money(row[k])
        # The equipment consumption rows carry a unit price and an annual cost.
        # Rates and quantities are physical and stay put.
        for row in self.equipment_utilities:
            for k in ("price", "annual_cost"):
                if isinstance(row.get(k), (int, float)):
                    row[k] = money(row[k])
        for row in self.equipment_consumables:
            for k in ("unit_cost", "annual_cost"):
                if isinstance(row.get(k), (int, float)):
                    row[k] = money(row[k])
        # The utility distribution repeats those costs in its own shape;
        # quantities, rates and shares are physical and stay put.
        for e in self.utility_distribution:
            for k in ("price", "annual_cost"):
                if isinstance(e.get(k), (int, float)):
                    e[k] = money(e[k])
            for group in (e.get("items"), e.get("by_section"), e.get("by_type")):
                for row in group or []:
                    if isinstance(row.get("annual_cost"), (int, float)):
                        row["annual_cost"] = money(row["annual_cost"])

        scale_obj(self, ("purchased_equipment_cost", "installed_direct", "bec",
                         "unit_cost", "capital_component", "fixed_component",
                         "variable_component", "byproduct_component"))
        # tasc_toc_factor is a ratio and must not move.
        scale_obj(self.capital, ("bec", "epc_fee", "epcc", "process_contingency",
                                 "project_contingency", "tpc", "owners_costs",
                                 "total_owners_cost", "toc", "tasc"))
        # operating_hours and capacity_factor are not money.
        scale_obj(self.opex, ("variable_total", "fixed_total", "total",
                              "variable_items", "fixed_items", "by_category"))
        if self.opex.labor is not None:
            # headcount stays a headcount.
            scale_obj(self.opex.labor, ("base_payroll", "burden", "supervision",
                                        "total_labor", "by_role"))
        # shares are fractions; primary_quantity is a physical output.
        scale_obj(self.allocation, ("cost_to_primary", "unit_cost_primary",
                                    "credits", "total_cost"))
        if self.cash_flow is not None:
            # years, periods, discount_rate, irr and payback_year are not money.
            scale_obj(self.cash_flow, (
                "price", "npv", "capex", "revenue", "opex", "depreciation",
                "interest", "principal", "taxable_income", "tax",
                "net_cash_flow", "discounted_cash_flow", "cumulative_dcf",
                "total_capital"))
        # charge_rate is a fixed-charge *rate* (1/yr), not an amount.

        self.currency = str(code).upper()
        self.exchange_rate = float(rate)
        self.exchange_rate_source = source
        return self

    # -- rollups used by charts ------------------------------------------
    def capex_breakdown(self) -> dict[str, float]:
        c = self.capital
        d = {"bare erected cost": c.bec,
             "EPC services": c.epc_fee,
             "process contingency": c.process_contingency,
             "project contingency": c.project_contingency}
        d.update({k: v for k, v in c.owners_costs.items() if v})
        return {k: v for k, v in d.items() if v}

    def equipment_shares(self) -> dict[str, float]:
        """
        Cost by line item, with installed-basis items marked.

        An item entered at an already-installed price is not comparable with a
        purchased cost. Putting both in one unlabelled chart repeats the error
        the cascade refuses to make, so the label carries the basis.
        """
        out: dict[str, float] = {}
        for r in self.equipment_rows:
            desc = r["description"]
            desc = desc if len(desc) <= 17 else desc[:16].rstrip() + "\u2026"
            label = f"{r['tag']} — {desc}"
            if r["installed"]:
                label += " [inst.]"
            n = 2
            while label in out:            # keep duplicate tags distinct
                label, n = f"{label} ({n})", n + 1
            out[label] = r["cost"]
        return out

    def purchased_shares(self) -> dict[str, float]:
        """Only items costed on a purchased basis — a like-for-like chart."""
        return {f"{r['tag']} — {r['description'][:17]}": r["cost"]
                for r in self.equipment_rows if not r["installed"]}

    def section_shares(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in self.equipment_rows:
            out[r["section"]] = out.get(r["section"], 0.0) + r["cost"]
        return out

    def type_shares(self) -> dict[str, float]:
        """
        Cost by kind of machine, not by where it sits.

        Three blowers of different sizes are three lines on the equipment
        list, three lines in the by-item chart and — until this — nothing at
        all in any rollup, because plant section answers "where" and not
        "what". This is the "what".
        """
        out: dict[str, float] = {}
        for r in self.equipment_rows:
            k = r.get("category") or "other"
            out[k] = out.get(k, 0.0) + r["cost"]
        return dict(sorted(out.items(), key=lambda kv: -abs(kv[1])))

    def cost_stack(self) -> dict[str, float]:
        """Levelised cost split into its four components, in $/unit."""
        return {"capital charge": self.capital_component,
                "fixed operating": self.fixed_component,
                "variable operating": self.variable_component,
                "byproduct credit": -self.byproduct_component}

    def report(self, width: int = 46) -> str:
        cur = self.currency
        out = [f"{'=' * 72}", f"  {self.name}",
               f"  method: {self.method}   basis: {self.dollar_year} {cur}",
               f"{'=' * 72}", "",
               self.capital.report(), "", self.opex.report(cur), "",
               self.allocation.report(cur), ""]
        w = width
        out += ["LEVELISED COST BUILD-UP", "=" * (w + 18)]
        for k, v in self.cost_stack().items():
            out.append(f"{'  ' + k:<{w}}{v:>18,.4f}")
        out += ["-" * (w + 18),
                f"{self.product.upper() + ' COST':<{w}}{self.unit_cost:>18,.4f} "
                f"{cur}/{self.unit}"]
        if self.charge_rate is not None:
            out.append(f"{'  (' + self.charge_rate_name + ')':<{w}}"
                       f"{self.charge_rate:>18.4%}")
        if self.warnings:
            out += ["", "WARNINGS"]
            out += [f"  ! {w_}" for w_ in self.warnings]
        return "\n".join(out)

    def to_dict(self) -> dict:
        d = {
            "name": self.name, "method": self.method, "currency": self.currency,
            "exchange_rate": self.exchange_rate,
            "exchange_rate_source": self.exchange_rate_source,
            "dollar_year": self.dollar_year,
            "equipment_rows": self.equipment_rows,
            "purchased_equipment_cost": self.purchased_equipment_cost,
            "installed_direct": self.installed_direct, "bec": self.bec,
            "installation_factor": self.installation_factor,
            "capital": asdict(self.capital),
            "opex": {
                "total": self.opex.total, "fixed_total": self.opex.fixed_total,
                "variable_total": self.opex.variable_total,
                "variable_items": self.opex.variable_items,
                "variable_categories": self.opex.variable_categories,
                "fixed_items": self.opex.fixed_items,
                "by_category": self.opex.by_category,
                "operating_hours": self.opex.operating_hours,
                "capacity_factor": self.opex.capacity_factor,
                "headcount": self.opex.labor.headcount if self.opex.labor else 0.0,
                "notes": self.opex.notes,
            },
            "allocation": asdict(self.allocation),
            "unit_cost": self.unit_cost, "unit": self.unit,
            "product": self.product, "annual_production": self.annual_production,
            "cost_stack": self.cost_stack(),
            "capex_breakdown": self.capex_breakdown(),
            "equipment_shares": self.equipment_shares(),
            "purchased_shares": self.purchased_shares(),
            "section_shares": self.section_shares(),
            "charge_rate": self.charge_rate,
            "charge_rate_name": self.charge_rate_name,
            "equipment_utilities": self.equipment_utilities,
            "equipment_utility_total": sum(
                r.get("annual_cost", 0.0) for r in self.equipment_utilities),
            "equipment_consumables": self.equipment_consumables,
            "equipment_consumable_total": sum(
                r.get("annual_cost", 0.0) for r in self.equipment_consumables),
            "utility_distribution": self.utility_distribution,
            "type_shares": self.type_shares(),
            "notes": self.notes, "warnings": self.warnings,
        }
        if self.cash_flow:
            cf = self.cash_flow
            d["cash_flow"] = {
                "years": cf.years, "capex": cf.capex, "revenue": cf.revenue,
                "opex": cf.opex, "depreciation": cf.depreciation,
                "tax": cf.tax, "net_cash_flow": cf.net_cash_flow,
                "discounted_cash_flow": cf.discounted_cash_flow,
                "cumulative_dcf": cf.cumulative_dcf, "npv": cf.npv,
                "irr": cf.irr, "payback_year": cf.payback_year,
            }
        return d


# ============================================================================
# 3. The Project
# ============================================================================
@dataclass
class Project:
    """
    A complete techno-economic study.

    Examples
    --------
    >>> p = Project(name="demo", dollar_year=2025)
    >>> p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000),
    ...                EquipmentItem("P-101", kind="pump", size=900, quantity=2)]
    >>> p.opex.raw_materials = [_opex.Stream("feed", 5.0, "tonne", 300.0)]
    >>> p.opex.labor = _opex.LaborModel(operators_per_shift=3)
    >>> p.products.products = [_products.Product("widget", 40_000, "tonne")]
    >>> r = p.run()
    >>> r.unit_cost > 0
    True

    Parameters are addressable by dotted path, which is what makes sweeps and
    the graphical application possible:

    >>> p["finance.discount_rate"]
    0.1
    >>> p["finance.discount_rate"] = 0.12
    >>> p["equipment.E-101.size"] = 7500
    >>> p["opex.raw_materials.feed.price"] = 350.0
    >>> round(p["opex.raw_materials.feed.price"])
    350
    """
    name: str = "Untitled project"
    description: str = ""
    dollar_year: int = 2025
    currency: str = "USD"
    #: Units of :attr:`currency` per USD, applied to the finished result. Stored
    #: in the project file so an old study reproduces on the rate it was quoted
    #: at rather than on today's. See :mod:`teakit.currency`.
    exchange_rate: float = 1.0
    exchange_rate_source: str = "USD base"
    location: str = "USGC"
    location_factor: float | None = None      # None -> look up from location
    method: str = "dcf"
    allow_extrapolation: bool = False
    #: Cost-index values set for this study, ``{year: CEPCI}``. They are
    #: installed over :data:`teakit.indices.CEPCI_ANNUAL` for the length of a
    #: run and take precedence over it, which is what lets a study be costed in
    #: a dollar-year the shipped series does not reach -- it stops at 2025 --
    #: and what lets someone with a Chemical Engineering subscription replace
    #: the provisional 2024/2025 estimates with the published figures.
    #: Saved with the project, so an old study reproduces on the index it was
    #: quoted against rather than on whatever ships today.
    cepci_overrides: dict[int, float] = field(default_factory=dict)

    equipment: list[EquipmentItem] = field(default_factory=list)
    capital: CapitalConfig = field(default_factory=CapitalConfig)
    opex: _opex.OperatingCost = field(default_factory=_opex.OperatingCost)
    products: _products.ProductSlate = field(default_factory=_products.ProductSlate)
    finance: FinanceConfig = field(default_factory=FinanceConfig)

    # ------------------------------------------------------------------
    # presets
    # ------------------------------------------------------------------
    def apply_finance_preset(self, name: str) -> "Project":
        """Set every finance field from a published basis.

        >>> Project().apply_finance_preset("NREL nth-plant").finance.discount_rate
        0.1
        """
        if name not in _defaults.FINANCE_PRESETS:
            raise KeyError(f"Unknown preset {name!r}. "
                           f"Options: {list(_defaults.FINANCE_PRESETS)}")
        preset = _defaults.FINANCE_PRESETS[name]
        for k, v in preset.items():
            if k == "source":
                continue
            if hasattr(self.finance, k):
                setattr(self.finance, k, v)
        self.finance.preset = name
        self.capital.basis = preset.get("basis", self.capital.basis)
        self.capital.construction_years = getattr(
            self.finance, "construction_years", 3)
        return self

    def effective_location_factor(self) -> float:
        if self.location_factor is not None:
            return self.location_factor
        try:
            return _defaults.location_factor(self.location, "capital")
        except KeyError:
            return 1.0

    # ------------------------------------------------------------------
    # dotted-path parameter access
    # ------------------------------------------------------------------
    def __getitem__(self, path: str):
        obj, attr = self._resolve(path)
        if isinstance(obj, dict):
            return obj[attr]
        return getattr(obj, attr)

    def __setitem__(self, path: str, value) -> None:
        obj, attr = self._resolve(path)
        if isinstance(obj, dict):
            obj[attr] = value
        else:
            setattr(obj, attr, value)

    def _resolve(self, path: str):
        """Return ``(container, final_attribute)`` for a dotted path."""
        parts = path.split(".")
        obj = self
        for i, part in enumerate(parts[:-1]):
            nxt = self._step(obj, part, path)
            obj = nxt
        return obj, parts[-1]

    @staticmethod
    def _step(obj, part: str, full: str):
        # list of tagged/named objects -> index by tag or name
        if isinstance(obj, list):
            for el in obj:
                if getattr(el, "tag", None) == part or getattr(el, "name", None) == part:
                    return el
            raise KeyError(f"{full}: no element named {part!r}")
        if isinstance(obj, dict):
            if part in obj:
                return obj[part]
            raise KeyError(f"{full}: no key {part!r}")
        if hasattr(obj, part):
            return getattr(obj, part)
        # ProductSlate / OperatingCost / EquipmentItem convenience: search
        # their lists by name. The isinstance check is not decoration: Project
        # itself has a `parameters()` *method*, and iterating a bound method
        # here would raise instead of falling through to the message below.
        for container in ("products", "raw_materials", "utilities", "waste",
                          "other_variable", "equipment", "staff", "parameters"):
            seq = getattr(obj, container, None)
            if not isinstance(seq, list):
                continue
            for el in seq:
                if getattr(el, "name", None) == part or \
                   getattr(el, "tag", None) == part or \
                   getattr(el, "role", None) == part:
                    return el
        raise KeyError(f"{full}: cannot resolve {part!r} on {type(obj).__name__}")

    def parameters(self) -> list[dict]:
        """
        Every numeric input, as ``{path, label, value, group, unit}``.

        This is the list a sensitivity study picks from, and the list the
        graphical application builds its parameter-picker from. It is generated,
        not hard-coded, so a new field on any config object appears
        automatically.

        >>> paths = [p["path"] for p in Project().parameters()]
        >>> "finance.discount_rate" in paths
        True
        """
        out: list[dict] = []

        def scan(prefix: str, obj, group: str, skip=()):
            for k in getattr(obj, "__dataclass_fields__", {}):
                if k in skip:
                    continue
                v = getattr(obj, k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append(dict(path=f"{prefix}.{k}", label=k.replace("_", " "),
                                    value=float(v), group=group))

        scan("finance", self.finance, "Finance & tax")
        # The two land provenance fields are how land_cost was worked out, not
        # an input the model reads; offering them for a sweep would sweep a
        # number nothing consumes.
        scan("capital", self.capital, "Capital",
             skip=("escalation_offset", "land_area_acres", "land_cost_per_acre"))
        scan("opex", self.opex, "Operating cost")
        for e in self.equipment:
            out.append(dict(path=f"equipment.{e.tag}.size",
                            label=f"{e.tag} size", value=float(e.size),
                            group="Equipment", unit=e.size_unit))
            out.append(dict(path=f"equipment.{e.tag}.quantity",
                            label=f"{e.tag} quantity", value=float(e.quantity),
                            group="Equipment"))
            # A recorded process parameter does not drive the cost, so it is
            # listed for completeness and for a study that sweeps it against a
            # user correlation — not because teakit will read it.
            for prm in e.parameters:
                if not prm.name:
                    continue
                out.append(dict(path=f"equipment.{e.tag}.{prm.name}.value",
                                label=f"{e.tag} {prm.name}",
                                value=float(prm.value), group="Equipment",
                                unit=prm.unit))
            for util in e.utilities:
                if not util.name:
                    continue
                out.append(dict(path=f"equipment.{e.tag}.{util.name}.rate",
                                label=f"{e.tag} {util.name} rate",
                                value=float(util.rate), group="Equipment utilities",
                                unit=f"{util.resolved_unit()}/{util.basis}"))
        for lst, grp in ((self.opex.raw_materials, "Raw materials"),
                         (self.opex.utilities, "Utilities"),
                         (self.opex.waste, "Waste"),
                         (self.opex.other_variable, "Other variable")):
            for s in lst:
                out.append(dict(path=f"opex.{_container_of(s)}.{s.name}.price",
                                label=f"{s.name} price", value=float(s.price),
                                group=grp, unit=f"$/{s.unit}"))
                out.append(dict(path=f"opex.{_container_of(s)}.{s.name}.rate",
                                label=f"{s.name} rate", value=float(s.rate),
                                group=grp, unit=f"{s.unit}/{s.basis}"))
        for p in self.products.products:
            out.append(dict(path=f"products.{p.name}.annual_production",
                            label=f"{p.name} production",
                            value=float(p.annual_production),
                            group="Products",
                            unit=f"{p.unit}/h" if p.basis == "hour" else p.unit))
            if p.price is not None:
                out.append(dict(path=f"products.{p.name}.price",
                                label=f"{p.name} price", value=float(p.price),
                                group="Products", unit=f"$/{p.unit}"))
        if self.opex.labor:
            out.append(dict(path="opex.labor.operators_per_shift",
                            label="operators per shift",
                            value=float(self.opex.labor.operators_per_shift),
                            group="Labour"))
            out.append(dict(path="opex.labor.operator_salary",
                            label="operator salary",
                            value=float(self.opex.labor.operator_salary),
                            group="Labour", unit="$/yr"))
        return out

    def copy(self) -> "Project":
        """Deep copy, via the JSON round-trip, so a sweep cannot mutate the base."""
        return Project.from_dict(json.loads(json.dumps(self.to_dict())))

    # ------------------------------------------------------------------
    # the pipeline
    # ------------------------------------------------------------------
    def cost_equipment(self) -> tuple[list[dict], float, float]:
        """Cost every line. Returns ``(rows, purchased_total, installed_total)``."""
        lf = self.effective_location_factor()
        hours = self.opex.operating_hours
        cf = self.opex.capacity_factor
        rows, purchased, installed = [], 0.0, 0.0
        for item in self.equipment:
            r = item.evaluate(self.dollar_year, lf, self.allow_extrapolation)
            # evaluate() answers "what does this cost". Everything the item
            # also knows about itself is attached here rather than threaded
            # through three return paths inside it.
            r["name"] = item.display_name
            r["parameters"] = [prm.to_dict() for prm in item.parameters]
            r["parameter_summary"] = "; ".join(prm.label()
                                               for prm in item.parameters)
            r["category"] = item.effective_category
            r["installation_factor_override"] = item.installation_factor
            r["utility_cost"] = item.utility_cost(hours, cf)
            r["utility_count"] = sum(1 for u in item.utilities if u.rate)
            r["consumable_cost"] = item.consumable_cost(cf)
            r["consumable_summary"] = "; ".join(
                f"{c.name} {c.interval_label()}" for c in item.consumables
                if c.interval_years and c.interval_years > 0)
            rows.append(r)
            if r["installed"]:
                installed += r["cost"]
            else:
                purchased += r["cost"]
        return rows, purchased, installed

    #: Which OperatingCost list a stream category belongs in. Equipment
    #: consumption is nearly always a utility, but a scrubber producing
    #: effluent or a reactor consuming a reagent is the same kind of statement
    #: about the same item, and belongs on the same panel.
    _CATEGORY_LIST = {
        "utility": "utilities",
        "waste": "waste",
        "raw_material": "raw_materials",
        "catalyst": "raw_materials",
        "other": "other_variable",
    }

    def utility_price_book(self) -> dict[str, dict]:
        """
        One price per utility for the whole study.

        A tariff is a property of the project, not of the machine drawing on
        it: there is no sense in which electricity costs one thing at the
        compressor and another at the pump. This assembles the single price
        each named utility is charged at, in order of authority:

        1. ``opex.utility_prices`` — a price you set for the study.
        2. the plant-level line of the same name on the Operating cost panel.
        3. the shipped utility catalogue.

        Returns ``{name: {"price", "unit", "source"}}``. Equipment lines are
        priced through this, so changing a tariff moves every item at once and
        the estimate cannot hold two prices for one utility.
        """
        book: dict[str, dict] = {}
        for name, rec in _defaults.UTILITY_CATALOGUE.items():
            book[name] = {"price": float(rec["price"]), "unit": rec["unit"],
                          "source": rec["source"], "origin": "catalogue"}
        for lst in (self.opex.utilities, self.opex.waste,
                    self.opex.raw_materials, self.opex.other_variable):
            for st in lst or []:
                if not st.name:
                    continue
                book[st.name] = {
                    "price": float(st.price), "unit": st.unit,
                    "source": st.source or f"the {st.name} line on this project",
                    "origin": "project"}
        for name, price in (getattr(self.opex, "utility_prices", None) or {}).items():
            entry = book.get(name, {"unit": "", "source": "", "origin": "project"})
            book[name] = {"price": float(price), "unit": entry.get("unit", ""),
                          "source": "set for this project", "origin": "project"}
        return book

    def equipment_utility_streams(self) -> dict[str, list["_opex.Stream"]]:
        """
        Everything the equipment list consumes, sorted into the operating-cost
        containers it belongs in.

        Returns ``{"utilities": [...], "waste": [...], ...}`` — the same lists
        :class:`teakit.opex.OperatingCost` holds, so :meth:`run` can simply
        append. Nothing here is stored on the project: it is derived from the
        equipment on every run, which is the point. Change a compressor's
        power and the electricity bill moves with it.
        """
        book = self.utility_price_book()
        out: dict[str, list[_opex.Stream]] = {}
        for item in self.equipment:
            n = item.running_quantity
            for util in item.utilities:
                if not util.rate:
                    continue
                where = self._CATEGORY_LIST.get(util.category or "utility",
                                                "utilities")
                out.setdefault(where, []).append(util.as_stream(item.tag, n, book))
            # Replacement parts are an operating cost with a schedule; they
            # join the same rollup so nothing has to know they came from a
            # different list.
            for stream in item.consumable_streams():
                where = self._CATEGORY_LIST.get(
                    stream.category or "catalyst", "raw_materials")
                out.setdefault(where, []).append(stream)
        return out

    def equipment_utility_rows(self, operating_hours: float | None = None,
                               capacity_factor: float | None = None) -> list[dict]:
        """
        One priced row per equipment utility line, for the interface and the
        report: which item, which utility, the per-unit rate, the plant rate
        once quantity is applied, and the annual cost.
        """
        hours = self.opex.operating_hours if operating_hours is None else operating_hours
        cf = self.opex.capacity_factor if capacity_factor is None else capacity_factor
        book = self.utility_price_book()
        rows: list[dict] = []
        for item in self.equipment:
            for util in item.utilities:
                if not util.rate:
                    continue
                stream = util.as_stream(item.tag, item.running_quantity, book)
                rows.append(dict(
                    tag=item.tag, item=item.display_name, section=item.section,
                    category=item.effective_category,
                    utility=util.name, stream_category=util.category or "utility",
                    rate=float(util.rate), per_unit=bool(util.per_unit),
                    running_units=item.running_quantity,
                    plant_rate=stream.rate, unit=stream.unit,
                    # What the rate is *read* in, as against what it is priced
                    # in. A compressor drawing 5,200 kWh per operating hour
                    # draws 5,200 kW, and that is how it belongs on a
                    # schedule; the price stays per kWh.
                    rate_unit=_defaults.rate_unit(stream.unit, util.basis,
                                                  util.name),
                    basis=util.basis, scales_with_rate=bool(util.scales_with_rate),
                    price=stream.price, price_source=util.price_source(book),
                    priced=util.is_priced(book), generates=util.generates(),
                    annual_quantity=stream.annual_quantity(hours, cf),
                    annual_cost=stream.annual_cost(hours, cf),
                    line=stream.name, note=util.note))
        rows.sort(key=lambda r: abs(r["annual_cost"]), reverse=True)
        return rows

    def utility_distribution(self, operating_hours: float | None = None,
                             capacity_factor: float | None = None) -> list[dict]:
        """
        Where each utility goes: one entry per utility, listing what draws it.

        A cost breakdown answers "what does electricity cost". A process
        engineer asks the other question — *which machines are drawing it, and
        how much* — and until now nothing in teakit answered that, even though
        every figure needed for it was already recorded against the items.

        Each entry carries the utility's annual quantity and cost, the
        contributors sorted largest first, and the same totals rolled up by
        plant section and by equipment type. Plant-level lines from the
        Operating cost panel are included as contributors of their own, so the
        quantities reconcile with the operating cost rather than quietly
        omitting whatever was not entered against a machine.

        Generation is kept as a negative quantity rather than netted away: a
        turbine that exports power and a compressor that draws it are two
        facts about the plant, and averaging them into one hides both.

        Sorted by annual cost, largest first; unpriced utilities come last on
        quantity, because a consumption nobody has priced is still worth
        seeing.
        """
        hours = self.opex.operating_hours if operating_hours is None else operating_hours
        cf = self.opex.capacity_factor if capacity_factor is None else capacity_factor
        book = self.utility_price_book()
        out: dict[str, dict] = {}

        def entry(name: str, unit: str, basis: str) -> dict:
            e = out.get(name)
            if e is None:
                e = out[name] = {
                    "utility": name, "unit": unit,
                    "rate_unit": _defaults.rate_unit(unit, basis, name),
                    "category": "utility", "price": None, "priced": False,
                    "annual_quantity": 0.0, "annual_cost": 0.0,
                    "drawn": 0.0, "generated": 0.0, "items": [],
                }
            return e

        def add(e: dict, **row) -> None:
            e["annual_quantity"] += row["annual_quantity"]
            e["annual_cost"] += row["annual_cost"]
            if row["annual_quantity"] < 0:
                e["generated"] += -row["annual_quantity"]
            else:
                e["drawn"] += row["annual_quantity"]
            e["items"].append(row)

        for r in self.equipment_utility_rows(hours, cf):
            e = entry(r["utility"], r["unit"], r["basis"])
            e["category"] = r["stream_category"]
            if r["priced"]:
                e["priced"], e["price"] = True, r["price"]
            add(e, source="equipment", tag=r["tag"], label=r["item"],
                section=r["section"], equipment_type=r["category"],
                rate=r["plant_rate"], rate_unit=r["rate_unit"],
                basis=r["basis"], units=r["running_units"],
                annual_quantity=r["annual_quantity"],
                annual_cost=r["annual_cost"], priced=r["priced"])

        # Plant-level lines: site lighting, a flare pilot, a whole-plant figure
        # somebody preferred to enter in one place. They belong in the total.
        for lst in (self.opex.utilities, self.opex.waste, self.opex.raw_materials,
                    self.opex.other_variable):
            for st in lst or []:
                if not st.name or not st.rate:
                    continue
                e = entry(st.name, st.unit, st.basis)
                e["category"] = st.category or e["category"]
                if st.name in book:
                    e["priced"], e["price"] = True, st.price
                add(e, source="plant", tag="", label="plant-level line",
                    section="—", equipment_type="—", rate=st.rate,
                    rate_unit=_defaults.rate_unit(st.unit, st.basis, st.name),
                    basis=st.basis, units=1,
                    annual_quantity=st.annual_quantity(hours, cf),
                    annual_cost=st.annual_cost(hours, cf), priced=True)

        def rollup(items: list[dict], key: str) -> list[dict]:
            agg: dict[str, dict] = {}
            for it in items:
                k = it[key] or "—"
                a = agg.setdefault(k, {"name": k, "annual_quantity": 0.0,
                                       "annual_cost": 0.0, "n": 0})
                a["annual_quantity"] += it["annual_quantity"]
                a["annual_cost"] += it["annual_cost"]
                a["n"] += 1
            return sorted(agg.values(),
                          key=lambda a: -abs(a["annual_quantity"]))

        for e in out.values():
            e["items"].sort(key=lambda i: -abs(i["annual_quantity"]))
            q = sum(abs(i["annual_quantity"]) for i in e["items"]) or 1.0
            c = sum(abs(i["annual_cost"]) for i in e["items"]) or 1.0
            for it in e["items"]:
                it["quantity_share"] = abs(it["annual_quantity"]) / q
                it["cost_share"] = abs(it["annual_cost"]) / c
            e["by_section"] = rollup(e["items"], "section")
            e["by_type"] = rollup(e["items"], "equipment_type")
            e["n_items"] = sum(1 for i in e["items"] if i["source"] == "equipment")

        return sorted(out.values(),
                      key=lambda e: (-abs(e["annual_cost"]),
                                     -abs(e["annual_quantity"])))

    def equipment_consumable_rows(self,
                                  capacity_factor: float | None = None) -> list[dict]:
        """One priced row per replacement part, for the interface and report."""
        cf = self.opex.capacity_factor if capacity_factor is None else capacity_factor
        rows: list[dict] = []
        for item in self.equipment:
            for part in item.consumables:
                if not (part.interval_years and part.interval_years > 0):
                    continue
                stream = part.as_stream(item.tag, item.running_quantity)
                rows.append(dict(
                    tag=item.tag, item=item.display_name, section=item.section,
                    category=item.effective_category, part=part.name,
                    quantity=float(part.quantity), unit=part.unit,
                    unit_cost=float(part.unit_cost),
                    interval_years=float(part.interval_years),
                    interval=part.interval_label(),
                    per_unit=bool(part.per_unit),
                    running_units=item.running_quantity,
                    annual_quantity=stream.annual_quantity(0.0, cf),
                    scales_with_rate=bool(part.scales_with_rate),
                    annual_cost=stream.annual_cost(0.0, cf),
                    line=stream.name, note=part.note))
        rows.sort(key=lambda r: abs(r["annual_cost"]), reverse=True)
        return rows

    def type_installation_factor(self, equipment_type: str) -> dict:
        """
        The installed-cost multiple for one equipment type, and where it came
        from. Returns ``factor``, ``source``, ``default``, ``edited``.

        A type teakit does not know -- you are allowed to write "quench
        tower" -- falls back to the plant-level service and setting class
        rather than refusing, and says so.

        >>> p = Project()
        >>> round(p.type_installation_factor("fired heater")["factor"], 3)
        2.627
        >>> p.capital.type_installation_factors["pump"] = 4.0
        >>> p.type_installation_factor("pump")["edited"]
        True
        """
        cfg = self.capital
        basis = _equipment.type_installation_basis(equipment_type)
        service = basis["service"] or cfg.loh_service
        setting = basis["setting"] or cfg.loh_setting
        default = _capital.installed_cost_loh(
            1.0, service, setting)["installation_factor"]
        # Say which half fell back, not just that something did: Table 6 names
        # 39 kinds of machine and a pump is not among them, so a blower can
        # have its own service regime and still borrow the plant's setting
        # class. A reviewer needs to know which.
        borrowed = [w for w, got in (("service regime", basis["service"]),
                                     ("setting-labour class", basis["setting"]))
                    if got is None]
        known = not borrowed
        source = (f"DOE/NETL-2002/1169 Tables 2-6, {service} service, "
                  f"{setting} setting labour")
        if borrowed:
            source += (f" — {' and '.join(borrowed)} taken from the plant-level "
                       f"default, because the report does not name "
                       f"{equipment_type!r}")
        set_to = (cfg.type_installation_factors or {}).get(equipment_type)
        edited = set_to is not None and float(set_to) > 0
        return {"type": equipment_type,
                "factor": float(set_to) if edited else default,
                "default": default, "edited": edited, "source": source,
                "service": service, "setting": setting, "known": known}

    def installation_factors(self) -> dict[str, dict]:
        """
        The installed-cost multiple for every equipment type in this project.

        This is what the Capital panel lists and what a reviewer should read
        before believing a BEC: one line per kind of machine actually in the
        equipment list, with the sourced default beside anything you changed.
        """
        types = []
        for item in self.equipment:
            # An item entered at an installed price never meets an
            # installation factor, so listing its type here would invite
            # someone to tune a number that changes nothing.
            if item.cost_is_installed:
                continue
            t = item.effective_category
            if t not in types:
                types.append(t)
        return {t: self.type_installation_factor(t) for t in sorted(types)}

    def _bec(self, rows: list[dict], purchased: float,
             installed_direct: float) -> tuple[float, float, list[str]]:
        """
        Bare erected cost from purchased equipment.

        Every row is given its own ``installation_factor`` and
        ``installed_cost`` here -- the same number for all of them under the
        three plant-wide methods, and its type's own under ``"type"``. The
        equipment schedule, the report and the interface all read those two
        keys, so there is exactly one place that decides what an item costs
        installed.

        Returns ``(bec, factor, notes)``, where ``factor`` is the overall
        installed-over-purchased ratio -- for ``"type"`` that is a weighted
        average across the list rather than a number anyone chose, and it is
        reported as such.
        """
        notes: list[str] = []
        cfg = self.capital
        for r in rows:
            r["installation_factor"] = 1.0
            r["installed_cost"] = r["cost"]
        if purchased <= 0:
            return installed_direct, 1.0, notes

        payers = [r for r in rows if not r["installed"]]
        if cfg.installation_method == "type":
            used: dict[str, float] = {}
            for r in payers:
                own = r.get("installation_factor_override")
                if own is not None and float(own) > 0:
                    f = float(own)
                    notes.append(f"{r['tag']}: installation factor {f:.2f} set "
                                 f"on the item")
                else:
                    rec = self.type_installation_factor(r.get("category") or "other")
                    f = rec["factor"]
                    used[rec["type"]] = f
                r["installation_factor"] = f
                r["installed_cost"] = r["cost"] * f
            base = sum(r["installed_cost"] for r in payers)
            if used:
                spread = ", ".join(f"{t} {f:.2f}" for t, f in sorted(used.items()))
                notes.append("installation factors by equipment type from "
                             f"DOE/NETL distributive factors — {spread}")
        else:
            if cfg.installation_method == "loh":
                inst = _capital.installed_cost_loh(purchased, cfg.loh_service,
                                                   cfg.loh_setting)
                notes.append(f"installation factor {inst['installation_factor']:.2f} "
                             f"from DOE/NETL distributive factors "
                             f"({cfg.loh_service}, {cfg.loh_setting})")
                base = inst["installed_cost"]
            elif cfg.installation_method == "lang":
                lang = _capital.lang_factor_capital(purchased, cfg.lang_type)
                notes.append(f"Lang factor {lang['lang_factor']} ({cfg.lang_type}); "
                             f"this is an order-of-magnitude method")
                base = lang["fixed_capital"]
            else:
                base = purchased * cfg.installation_factor
                notes.append(f"user installation factor {cfg.installation_factor:.2f}")
            factor = base / purchased
            for r in payers:
                r["installation_factor"] = factor
                r["installed_cost"] = r["cost"] * factor

        if installed_direct:
            notes.append(f"{installed_direct:,.0f} of already-installed cost "
                         f"entered the cascade directly at BEC and was not "
                         f"multiplied by the installation factor")
        return base + installed_direct, base / purchased, notes

    def run(self, method: str | None = None) -> ProjectResult:
        """
        Run the whole pipeline and return a :class:`ProjectResult`.

        Any cost-index values set on :attr:`cepci_overrides` are installed for
        the length of the run and taken down again afterwards. Escalation
        happens in half a dozen places -- correlations, vendor quotes, utility
        prices -- and this is the one point that covers all of them without
        threading an index table through every signature between here and
        :func:`teakit.indices.cepci`.
        """
        with _indices.user_cepci(self.cepci_overrides):
            return self._run(method)

    def _run(self, method: str | None = None) -> ProjectResult:
        """The pipeline itself. Call :meth:`run`, which sets the index basis."""
        method = method or self.method
        if method not in COSTING_METHODS:
            raise ValueError(f"method must be one of {COSTING_METHODS}")
        notes: list[str] = []
        warnings: list[str] = []

        # --- 1. equipment -> BEC ---
        rows, purchased, installed_direct = self.cost_equipment()
        # _bec writes each row's own installation factor and installed cost —
        # "what did this machine cost once it was in the ground" — because
        # only it knows whether the factor is one plant-wide number or one per
        # equipment type.
        bec, inst_factor, bec_notes = self._bec(rows, purchased, installed_direct)
        notes.extend(bec_notes)
        for r in rows:
            warnings.extend(f"{r['tag']}: {n}" for n in r["notes"]
                            if any(k in n.upper() for k in
                                   ("EXTRAPOLAT", "OUTSIDE", "UNRELIABLE")))

        # --- 2. capital cascade ---
        cfg = self.capital
        cap_model = _capital.NETLCapitalCost(
            bec=bec, epc_fee_frac=cfg.epc_fee_frac,
            process_contingency_frac=cfg.process_contingency_frac,
            project_contingency_frac=cfg.project_contingency_frac,
            preproduction_frac_tpc=cfg.preproduction_frac_tpc,
            spare_parts_frac_tpc=cfg.spare_parts_frac_tpc,
            financing_frac_tpc=cfg.financing_frac_tpc,
            other_owners_frac_tpc=cfg.other_owners_frac_tpc,
            land_cost=cfg.land_cost,
            extra_owners_costs=dict(cfg.extra_owners_costs),
            construction_years=self.finance.construction_years,
            basis=cfg.basis, wacc_pretax=cfg.wacc_pretax,
            capital_escalation=cfg.capital_escalation,
            spend_profile=cfg.spend_profile,
            escalation_offset=cfg.escalation_offset)
        cap = cap_model.evaluate()

        # --- 3. operating cost ---
        # Evaluate against a shallow copy. run() must not mutate the project:
        # every sweep in teakit.sensitivity re-runs the same object, and a
        # side effect here would silently carry capital from one trial into
        # the next.
        op_cfg = _copy.copy(self.opex)
        op_cfg.fci = cap.toc
        op_cfg.tpc = cap.tpc
        if op_cfg.installed_equipment_cost is None:
            op_cfg.installed_equipment_cost = bec

        # What the equipment consumes is derived from the equipment list on
        # every run and merged in here, after the plant-level lines the user
        # typed on the Operating cost panel. New lists on every call: the copy
        # above is shallow, so appending to op_cfg.utilities in place would
        # append to the project's own list and grow it by one bill per run.
        derived = self.equipment_utility_streams()
        for where, extra in derived.items():
            op_cfg.__dict__[where] = [*getattr(op_cfg, where, []), *extra]
        book = self.utility_price_book()
        unpriced = [f"{it.tag}: {u}" for it in self.equipment
                    for u in it.unpriced_utilities(book)]
        if unpriced:
            warnings.append(
                "utility lines with a consumption but no price, so they cost "
                "nothing in this estimate — " + "; ".join(unpriced))

        op = op_cfg.evaluate()

        # --- 4. products ---
        if not self.products.products:
            raise ValueError("no products defined — nothing to levelise against")
        prim = self.products.primary()
        cf = op.capacity_factor
        # The operating hours are only read by products entered per hour, but
        # they have to reach every call: a slate that mixes an hourly primary
        # with an annual byproduct would otherwise price the two on different
        # years' worth of output.
        hours = op.operating_hours
        q = prim.quantity(cf, hours)
        byproduct_rev = self.products.byproduct_revenue(cf, hours)

        # --- 5. levelised cost by the chosen method ---
        cash_flow = None
        charge_rate = None
        charge_name = ""
        fin = self.finance

        if method == "dcf":
            model = _dcf.CashFlowModel(
                total_capital=cap.toc, annual_production=q,
                annual_fixed_opex=op.fixed_total,
                annual_variable_opex=op.variable_total,
                annual_byproduct_revenue=byproduct_rev,
                plant_life_years=fin.plant_life_years,
                construction_years=fin.construction_years,
                startup_revenue_frac=fin.startup_revenue_frac,
                startup_variable_cost_frac=fin.startup_variable_cost_frac,
                startup_fixed_cost_frac=fin.startup_fixed_cost_frac,
                discount_rate=fin.discount_rate, tax_rate=fin.tax_rate,
                depreciation_years=fin.depreciation_years,
                debt_frac=fin.debt_frac,
                debt_interest_rate=fin.debt_interest_rate,
                debt_term_years=fin.debt_term_years,
                working_capital=fin.working_capital_frac * cap.toc,
                land_cost=cfg.land_cost,
                salvage_value=fin.salvage_frac * cap.toc)
            price = model.minimum_selling_price()
            cash_flow = model.run(price)
            unit_cost = price
            # decompose: capital charge is the residual after O&M
            cap_comp = unit_cost - (op.total - byproduct_rev) / q
            fixed_comp = op.fixed_total / q
            var_comp = op.variable_total / q
            by_comp = byproduct_rev / q
            notes.append("MSP solved at NPV = 0 on the after-tax cash flow; the "
                         "capital component is the residual and therefore carries "
                         "tax, depreciation timing and construction financing")
        elif method == "crf":
            # The annuity form: what it costs each year to own the plant, at
            # the discount rate, over its life. Charged against TOC — the
            # overnight cost, in dollars of the dollar-year — because a CRF is
            # a pre-tax, constant-dollar device and TASC is neither.
            charge_rate = _lev.crf(fin.discount_rate, fin.plant_life_years)
            charge_name = "CRF (capital recovery factor)"
            cap_charge = charge_rate * cap.toc
            total_annual = cap_charge + op.total - byproduct_rev
            unit_cost = total_annual / q
            cap_comp = cap_charge / q
            fixed_comp = op.fixed_total / q
            var_comp = op.variable_total / q
            by_comp = byproduct_rev / q
            notes.append(
                f"levelised cost = (annualised capital + operating cost - "
                f"byproduct revenue) / production, with annualised capital = "
                f"CRF {charge_rate:.4%} x TOC {cap.toc:,.0f}. CRF = i(1+i)^n / "
                f"[(1+i)^n - 1] at i = {fin.discount_rate:.2%} over "
                f"{fin.plant_life_years} years")
            notes.append(
                "the CRF method charges the cost of capital but no tax, so it "
                "sits between 'simple' and the full cash flow. Quote it as a "
                "pre-tax, constant-dollar levelised cost")
        elif method == "fcr":
            charge_rate = _lev.fcr(fin.discount_rate, fin.plant_life_years,
                                   fin.tax_rate, fin.depreciation_years)
            charge_name = "FCR (NETL Eq. 3)"
            cap_charge = charge_rate * cap.tasc
            total_annual = cap_charge + op.total - byproduct_rev
            unit_cost = total_annual / q
            cap_comp = cap_charge / q
            fixed_comp = op.fixed_total / q
            var_comp = op.variable_total / q
            by_comp = byproduct_rev / q
            notes.append(f"capital charge = FCR {charge_rate:.4%} x TASC "
                         f"{cap.tasc:,.0f} (NETL charges the FCR against TASC, "
                         f"not TOC — a {(cap.tasc_toc_factor - 1) * 100:.0f}% difference)")
        else:  # simple
            cap_charge = cap.toc / fin.plant_life_years
            total_annual = cap_charge + op.total - byproduct_rev
            unit_cost = total_annual / q
            cap_comp = cap_charge / q
            fixed_comp = op.fixed_total / q
            var_comp = op.variable_total / q
            by_comp = byproduct_rev / q
            charge_rate = 1.0 / fin.plant_life_years
            charge_name = "straight-line, no cost of capital"
            warnings.append("the 'simple' method charges no cost of capital at "
                            "all and will understate the levelised cost by "
                            "30-50% at typical discount rates. Screening only.")

        # --- 6. allocation ---
        if self.products.method == "byproduct credit":
            alloc = self.products.allocate(
                total_cost=(unit_cost * q) + byproduct_rev, capacity_factor=cf,
                operating_hours=hours)
        else:
            annual_total = (cap_comp + fixed_comp + var_comp) * q
            alloc = self.products.allocate(total_cost=annual_total,
                                           capacity_factor=cf,
                                           operating_hours=hours)
            unit_cost = alloc.unit_cost_primary
        notes.extend(alloc.notes)

        # --- 7. sanity checks worth surfacing ---
        # ...and only if something in this study is actually escalated from
        # the correlation basis. A list of vendor quotes priced last year has
        # not been escalated 27 years, and saying so was simply wrong.
        on_basis = sum(r["cost"] for r in rows
                       if r.get("base_cost_year") == _eqdata.BASIS_YEAR)
        if on_basis and self.dollar_year - _eqdata.BASIS_YEAR > 15:
            share = on_basis / (purchased + installed_direct or 1.0)
            warnings.append(
                f"{share:.0%} of the equipment cost comes from correlations on a "
                f"{_eqdata.BASIS_YEAR} basis, escalated "
                f"{self.dollar_year - _eqdata.BASIS_YEAR} years; cost engineers "
                f"recommend a 5-year window. Treat capital as AACE Class 5.")
        if cfg.process_contingency_frac == 0 and cfg.project_contingency_frac < 0.15:
            warnings.append("contingency below the AACE 16R-90 range for a "
                            "budget-type estimate (15-30% project contingency)")
        if op.variable_total and op.variable_total / max(op.total, 1) > 0.85:
            notes.append("variable cost is over 85% of OPEX — the answer is "
                         "essentially a feedstock price forecast, so put your "
                         "effort there rather than into the capital estimate")

        result = ProjectResult(
            name=self.name, method=method, currency="USD",
            dollar_year=self.dollar_year, equipment_rows=rows,
            purchased_equipment_cost=purchased, installed_direct=installed_direct,
            bec=bec, capital=cap, opex=op, allocation=alloc,
            unit_cost=unit_cost, unit=prim.unit, product=prim.name,
            annual_production=q, capital_component=cap_comp,
            fixed_component=fixed_comp, variable_component=var_comp,
            byproduct_component=by_comp, cash_flow=cash_flow,
            charge_rate=charge_rate, charge_rate_name=charge_name,
            installation_factor=inst_factor,
            equipment_utilities=self.equipment_utility_rows(
                op.operating_hours, op.capacity_factor),
            equipment_consumables=self.equipment_consumable_rows(
                op.capacity_factor),
            utility_distribution=self.utility_distribution(
                op.operating_hours, op.capacity_factor),
            notes=notes, warnings=warnings)

        # Everything above is USD by construction. Currency is the last step.
        code = (self.currency or "USD").upper()
        # `or 1.0` would quietly turn a zero rate into "no conversion" and
        # produce a USD number wearing a foreign label. Only None defaults.
        rate = 1.0 if self.exchange_rate is None else float(self.exchange_rate)
        if code != "USD":
            if rate <= 0:
                raise ValueError(
                    f"exchange_rate must be positive to report in {code}, "
                    f"got {rate}")
            result.convert_currency(rate, code, self.exchange_rate_source)
            quote = _currency.RateQuote(code, rate, self.exchange_rate_source)
            age = quote.stale_days
            notes.append(
                f"reported in {code} at {quote.label()}; the engineering basis "
                f"is a {self.dollar_year} USD US Gulf Coast estimate and the "
                f"conversion does not account for local content, labour or duty")
            if age is not None and age > 30:
                warnings.append(
                    f"the {code} exchange rate in use is {age} days old "
                    f"({self.exchange_rate_source}) — refresh it before quoting")
        else:
            result.exchange_rate = 1.0
            result.exchange_rate_source = "USD base"
        return result

    def method_comparison(self) -> dict[str, float]:
        """
        Run all three costing methods on the same inputs.

        The spread between them is the single most informative diagnostic in a
        TEA. If ``simple`` is within 10% of ``dcf`` your discount rate is
        near zero or your capital is negligible; if ``fcr`` is far from ``dcf``,
        check whether the FCR's tax and depreciation assumptions match the cash
        flow's.
        """
        return {m: self.run(m).unit_cost for m in COSTING_METHODS}

    # ------------------------------------------------------------------
    # serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema": "teakit.project/1",
            "name": self.name, "description": self.description,
            "dollar_year": self.dollar_year, "currency": self.currency,
            "exchange_rate": self.exchange_rate,
            "exchange_rate_source": self.exchange_rate_source,
            "location": self.location, "location_factor": self.location_factor,
            "method": self.method, "allow_extrapolation": self.allow_extrapolation,
            # JSON has no integer keys; from_dict puts them back.
            "cepci_overrides": {str(k): v
                                for k, v in sorted(self.cepci_overrides.items())},
            "equipment": [e.to_dict() for e in self.equipment],
            "capital": self.capital.to_dict(),
            "opex": self.opex.to_dict(),
            "products": self.products.to_dict(),
            "finance": self.finance.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            name=d.get("name", "Untitled project"),
            description=d.get("description", ""),
            dollar_year=d.get("dollar_year", 2025),
            currency=d.get("currency", "USD"),
            exchange_rate=d.get("exchange_rate", 1.0),
            exchange_rate_source=d.get("exchange_rate_source", "USD base"),
            location=d.get("location", "USGC"),
            location_factor=d.get("location_factor"),
            method=d.get("method", "dcf"),
            allow_extrapolation=d.get("allow_extrapolation", False),
            cepci_overrides=_indices._clean_index(d.get("cepci_overrides")),
            equipment=[EquipmentItem.from_dict(e) for e in d.get("equipment", [])],
            capital=CapitalConfig.from_dict(d.get("capital", {})),
            opex=_opex.OperatingCost.from_dict(d.get("opex", {})),
            products=_products.ProductSlate.from_dict(d.get("products", {})),
            finance=FinanceConfig.from_dict(d.get("finance", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialise. The result is a complete, portable study definition.

        >>> p = Project(name="x")
        >>> Project.from_json(p.to_json()).name
        'x'
        """
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, s: str) -> "Project":
        return cls.from_dict(json.loads(s))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, encoding="utf-8") as fh:
            return cls.from_json(fh.read())


def _container_of(stream) -> str:
    return {"raw_material": "raw_materials", "utility": "utilities",
            "waste": "waste", "catalyst": "raw_materials",
            "royalty": "other_variable"}.get(stream.category, "other_variable")


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
