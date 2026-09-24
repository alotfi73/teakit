"""
teakit.products — The product slate, and how to split cost between products.
============================================================================

A plant with one product has one levelised cost and no argument. A plant with
two has an allocation problem, and the choice of allocation method can move the
headline number by a factor of two without changing a single physical quantity.
This module makes that choice explicit and forces you to name it.

THE FOUR METHODS
----------------
**byproduct credit** (a.k.a. displacement, or system expansion in LCA)
    Sell the secondary products at their market price, subtract the revenue from
    total cost, and divide what is left by the primary product. This is what
    NREL's minimum-selling-price calculations do, and it is the default here.
    It is the right method when the secondary output is genuinely incidental and
    has a liquid market price. It becomes unstable when byproduct revenue
    approaches total cost — the primary cost then becomes a small difference of
    large numbers, and a 10% error in the byproduct price can swing the answer
    30%. :meth:`ProductSlate.credit_sensitivity` reports that leverage.

**market value allocation**
    Split cost in proportion to each product's revenue. Cannot produce a
    negative cost, and is the usual choice when two products are genuinely
    co-equal. Requires a price for the primary product, which is circular if the
    primary price is what you are solving for — so teakit uses an assumed
    reference price for the split and reports it.

**mass allocation**
    Split by tonnes out. Simple, defensible for commodity streams of similar
    value, indefensible when a tonne of one product is worth fifty times a tonne
    of another.

**energy allocation**
    Split by energy content. The convention in fuels work, and required by
    several renewable-fuel regulatory frameworks.

If you report a levelised cost without naming the allocation method, the number
is not reproducible.

SOURCES
-------
Humbird, D. et al. (2011), NREL/TP-5100-47764 — byproduct credit convention for
    minimum ethanol selling price.
NETL-PUB-22580 §4 — byproduct credit treatment in the COE equation.
ISO 14040/14044 — the allocation hierarchy that the four methods above follow.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

__all__ = ["Product", "ProductSlate", "AllocationResult", "ALLOCATION_METHODS"]

ALLOCATION_METHODS = ("byproduct credit", "market value", "mass", "energy")


@dataclass
class Product:
    """
    One saleable output.

    Parameters
    ----------
    name : str
        Label used everywhere downstream.
    annual_production : float
        Output at full rate, in ``unit``: per operating year when
        ``basis="year"`` (the default), per operating hour when
        ``basis="hour"``. The field keeps its name because it is what every
        saved project, dotted path and sweep already calls it.
    basis : {"year", "hour"}
        Whether the figure above is annual or hourly, exactly as on a
        :class:`teakit.opex.Stream`. An hourly figure is multiplied by the
        plant's operating hours, so changing the operating time moves the
        output and the feed together instead of leaving one of them behind.
    unit : str
        kg, tonne, gal, MWh, Nm3 — whatever the price is quoted in. This unit
        propagates into the levelised cost, so ``$/tonne`` versus ``$/kg`` is
        decided here.
    price : float or None
        Market price per unit. ``None`` on the primary product means "solve for
        it" — that is exactly what a minimum selling price is.
    role : {"primary", "coproduct", "byproduct"}
        Exactly one product must be ``"primary"``. A ``"byproduct"`` is credited
        at its price; a ``"coproduct"`` participates in allocation.
    energy_content : float
        Lower heating value per unit, for energy allocation. Optional.
    mass_per_unit : float
        Mass in tonnes per unit, for mass allocation. Defaults to 1.0, which is
        correct when ``unit`` is already tonnes.
    scales_with_rate : bool
        Whether output follows the capacity factor. Almost always True.

    Examples
    --------
    >>> p = Product("ethanol", 61e6, "gal", role="primary")
    >>> p.price is None
    True
    >>> g = Product("electricity", 120_000, "MWh", price=45.0, role="byproduct")
    >>> g.annual_revenue()
    5400000.0

    The same plant entered on an hourly basis, at 8,000 h/yr and a 90%
    capacity factor:

    >>> h = Product("methanol", 100.0, "tonne", basis="hour", role="primary")
    >>> h.quantity(0.90, 8000)
    720000.0
    """
    name: str
    annual_production: float
    unit: str = "tonne"
    price: float | None = None
    role: str = "primary"
    energy_content: float = 0.0
    mass_per_unit: float = 1.0
    scales_with_rate: bool = True
    basis: str = "year"
    note: str = ""

    def __post_init__(self):
        if self.role not in ("primary", "coproduct", "byproduct"):
            raise ValueError("role must be 'primary', 'coproduct' or 'byproduct'")
        if self.basis not in ("hour", "year"):
            raise ValueError("basis must be 'hour' or 'year'")

    def quantity(self, capacity_factor: float = 1.0,
                 operating_hours: float = 0.0) -> float:
        """
        Output for the year, in ``unit``.

        ``operating_hours`` is only read on an hourly basis, which is why it
        may be omitted everywhere a slate is annual -- the overwhelmingly
        common case, and every project written before the basis existed.
        """
        q = (self.annual_production * operating_hours if self.basis == "hour"
             else self.annual_production)
        return q * (capacity_factor if self.scales_with_rate else 1.0)

    def annual_revenue(self, capacity_factor: float = 1.0,
                       operating_hours: float = 0.0) -> float:
        """Revenue at the stated price; zero if the price is unset."""
        return (self.quantity(capacity_factor, operating_hours)
                * (self.price or 0.0))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Product":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AllocationResult:
    """Output of :meth:`ProductSlate.allocate`."""
    method: str
    primary: str
    primary_unit: str
    primary_quantity: float
    cost_to_primary: float
    unit_cost_primary: float
    shares: dict[str, float]
    credits: dict[str, float]
    total_cost: float
    notes: list[str] = field(default_factory=list)

    def report(self, currency: str = "$", width: int = 40) -> str:
        w = width
        out = [f"COST ALLOCATION — {self.method}", "=" * (w + 18),
               f"{'total annual cost to allocate':<{w}}{self.total_cost:>18,.0f}"]
        if self.credits:
            for k, v in self.credits.items():
                out.append(f"{'  credit: ' + k:<{w}}{-v:>18,.0f}")
        if self.shares:
            out.append("")
            for k, v in self.shares.items():
                out.append(f"{'  share ' + k:<{w}}{v:>17.1%}")
        out += ["-" * (w + 18),
                f"{'cost borne by ' + self.primary:<{w}}{self.cost_to_primary:>18,.0f}",
                f"{'quantity':<{w}}{self.primary_quantity:>18,.0f} {self.primary_unit}",
                f"{'UNIT COST':<{w}}{self.unit_cost_primary:>18,.4f} "
                f"{currency}/{self.primary_unit}"]
        for n in self.notes:
            out.append(f"  ! {n}")
        return "\n".join(out)


@dataclass
class ProductSlate:
    """
    The full set of outputs, plus the allocation rule.

    Examples
    --------
    A biorefinery selling ethanol with an electricity byproduct:

    >>> slate = ProductSlate([
    ...     Product("ethanol", 61e6, "gal", role="primary"),
    ...     Product("electricity", 120_000, "MWh", price=45.0, role="byproduct"),
    ... ])
    >>> r = slate.allocate(total_cost=140e6)
    >>> round(r.unit_cost_primary, 3)
    2.207
    >>> r.method
    'byproduct credit'

    Mass allocation between two co-products instead:

    >>> slate2 = ProductSlate([
    ...     Product("ethylene", 500_000, "tonne", price=900, role="primary"),
    ...     Product("propylene", 250_000, "tonne", price=1100, role="coproduct"),
    ... ], method="mass")
    >>> r2 = slate2.allocate(total_cost=600e6)
    >>> round(r2.shares["ethylene"], 4)
    0.6667
    """
    products: list[Product] = field(default_factory=list)
    method: str = "byproduct credit"
    #: Reference price for the primary product, used only by market-value
    #: allocation, which would otherwise be circular. If the primary product
    #: carries a price, that price is used instead.
    primary_reference_price: float | None = None

    # ------------------------------------------------------------------
    def primary(self) -> Product:
        """The primary product. Raises if there is not exactly one."""
        prim = [p for p in self.products if p.role == "primary"]
        if len(prim) != 1:
            raise ValueError(f"exactly one product must have role='primary', "
                             f"found {len(prim)}")
        return prim[0]

    def secondaries(self) -> list[Product]:
        return [p for p in self.products if p.role != "primary"]

    def byproduct_revenue(self, capacity_factor: float = 1.0,
                          operating_hours: float = 0.0) -> float:
        """Total revenue from every non-primary product.

        >>> ProductSlate([Product("a", 1, "t", role="primary"),
        ...               Product("b", 100, "t", price=50, role="byproduct")]
        ...             ).byproduct_revenue()
        5000.0
        """
        return sum(p.annual_revenue(capacity_factor, operating_hours)
                   for p in self.secondaries())

    def total_revenue(self, primary_price: float | None = None,
                      capacity_factor: float = 1.0,
                      operating_hours: float = 0.0) -> float:
        """Revenue from everything, with the primary priced at ``primary_price``."""
        prim = self.primary()
        pp = primary_price if primary_price is not None else (prim.price or 0.0)
        return (prim.quantity(capacity_factor, operating_hours) * pp
                + self.byproduct_revenue(capacity_factor, operating_hours))

    # ------------------------------------------------------------------
    def allocate(self, total_cost: float, capacity_factor: float = 1.0,
                 method: str | None = None,
                 operating_hours: float = 0.0) -> AllocationResult:
        """
        Apportion ``total_cost`` and return the unit cost of the primary product.

        ``total_cost`` is the annualised total: capital charge plus operating
        cost, or the cost side of a DCF. It must be on the same basis as the
        production quantities. ``operating_hours`` is read only by products
        entered on an hourly basis.
        """
        method = method or self.method
        if method not in ALLOCATION_METHODS:
            raise ValueError(f"method must be one of {ALLOCATION_METHODS}")
        prim = self.primary()
        q = prim.quantity(capacity_factor, operating_hours)
        if q <= 0:
            raise ValueError("primary product has zero production")
        notes: list[str] = []
        credits: dict[str, float] = {}
        shares: dict[str, float] = {}

        if method == "byproduct credit":
            for p in self.secondaries():
                rev = p.annual_revenue(capacity_factor, operating_hours)
                if rev:
                    credits[p.name] = rev
                elif p.price is None:
                    notes.append(f"{p.name} has no price and contributes no credit")
            credit_total = sum(credits.values())
            cost = total_cost - credit_total
            if credit_total > 0.5 * total_cost:
                notes.append(
                    f"byproduct credits are {credit_total / total_cost:.0%} of total "
                    f"cost — the primary cost is now a small difference of large "
                    f"numbers and is highly leveraged on the byproduct price. "
                    f"Consider co-product allocation instead.")
            if cost < 0:
                notes.append("byproduct credits exceed total cost: the primary "
                             "product has a negative cost, which is arithmetically "
                             "correct and economically meaningless. Reallocate.")
        else:
            weights: dict[str, float] = {}
            if method == "mass":
                for p in self.products:
                    weights[p.name] = (p.quantity(capacity_factor, operating_hours)
                                       * p.mass_per_unit)
                notes.append("mass allocation ignores value; defensible only for "
                             "streams of comparable worth per tonne")
            elif method == "energy":
                for p in self.products:
                    weights[p.name] = (p.quantity(capacity_factor, operating_hours)
                                       * p.energy_content)
                if not sum(weights.values()):
                    raise ValueError("energy allocation needs energy_content on "
                                     "at least one product")
                notes.append("energy allocation on lower heating value")
            else:  # market value
                pp = (prim.price if prim.price is not None
                      else self.primary_reference_price)
                if pp is None:
                    raise ValueError(
                        "market-value allocation needs a price for the primary "
                        "product: set Product.price or "
                        "ProductSlate.primary_reference_price")
                for p in self.products:
                    price = pp if p.role == "primary" else (p.price or 0.0)
                    weights[p.name] = (p.quantity(capacity_factor, operating_hours)
                                       * price)
                notes.append(f"market-value allocation used a reference price of "
                             f"{pp:,.4g} {'' if prim.price is not None else '(assumed) '}"
                             f"for {prim.name}; the allocated cost moves with it")
            tot_w = sum(weights.values())
            if tot_w <= 0:
                raise ValueError("allocation weights sum to zero")
            shares = {k: v / tot_w for k, v in weights.items()}
            cost = total_cost * shares[prim.name]

        return AllocationResult(
            method=method, primary=prim.name, primary_unit=prim.unit,
            primary_quantity=q, cost_to_primary=cost, unit_cost_primary=cost / q,
            shares=shares, credits=credits, total_cost=total_cost, notes=notes)

    # ------------------------------------------------------------------
    def credit_sensitivity(self, total_cost: float, delta: float = 0.10,
                           capacity_factor: float = 1.0,
                           operating_hours: float = 0.0) -> dict[str, float]:
        """
        How much a ``delta`` change in every byproduct price moves the primary
        unit cost, under the byproduct-credit method. Reported as an elasticity.

        A magnitude above ~1.5 means the headline number is really a byproduct
        price forecast wearing a process-economics hat.

        >>> s = ProductSlate([Product("main", 1000, "t", role="primary"),
        ...                   Product("side", 500, "t", price=200, role="byproduct")])
        >>> round(s.credit_sensitivity(1e6)["elasticity"], 3)
        -0.111
        """
        base = self.allocate(total_cost, capacity_factor, "byproduct credit",
                             operating_hours)
        credit = sum(base.credits.values())
        bumped = total_cost - credit * (1 + delta)
        q = base.primary_quantity
        new_unit = bumped / q
        if base.unit_cost_primary == 0:
            return {"elasticity": float("inf"), "base": 0.0, "bumped": new_unit}
        elas = ((new_unit - base.unit_cost_primary) / base.unit_cost_primary) / delta
        return {"elasticity": elas,
                "base": base.unit_cost_primary,
                "bumped": new_unit,
                "credit_share_of_cost": credit / total_cost if total_cost else 0.0}

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"products": [p.to_dict() for p in self.products],
                "method": self.method,
                "primary_reference_price": self.primary_reference_price}

    @classmethod
    def from_dict(cls, d: dict) -> "ProductSlate":
        return cls(products=[Product.from_dict(p) for p in d.get("products", [])],
                   method=d.get("method", "byproduct credit"),
                   primary_reference_price=d.get("primary_reference_price"))


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
