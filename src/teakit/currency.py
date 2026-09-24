"""
teakit.currency — exchange rates for reporting a USD estimate in another currency
================================================================================

teakit's cost engine works in **one** currency: US dollars. Every correlation in
:mod:`teakit.equipment` is regressed from DOE/NETL-2002/1169, every index in
:mod:`teakit.indices` is a US series, and every default price in
:mod:`teakit.defaults` is a US tariff. That is the engineering basis and this
module does not touch it.

What this module does is convert the *finished* result for reporting. A rate is
a presentation choice applied at the very end, never an input to the estimate::

    result = project.run()                       # always USD internally
    result.convert_currency(0.92, "EUR")         # reported in EUR

Three ways to get a rate, in the order you should prefer them:

1. **Your own.** A project rate agreed with whoever is funding the study. Set it
   on the project and it is stored in the project file, so the number is
   reproducible years later. This is the only defensible choice for a real
   estimate.
2. **Live.** :func:`fetch_rates` pulls the ECB reference rates published through
   the Frankfurter service. Requires a network; fails closed, never raises.
3. **The offline table.** :data:`DEFAULT_RATES`, below. Indicative only — see
   the warning on that table.

.. warning::
   A currency conversion does **not** make a US-basis estimate into a local
   estimate. Local content, labour rates, freight, duty and code requirements
   move independently of the exchange rate and usually dominate it. Set the
   location factor in :data:`teakit.defaults.LOCATIONS` for that, and treat the
   converted figure as "the US estimate, expressed in EUR" — not "what this
   plant costs in Europe".

Sources
-------
Frankfurter (https://frankfurter.app) republishes the European Central Bank
euro foreign-exchange reference rates, which are published each working day at
about 16:00 CET. They are reference rates, not dealable rates: a real
transaction carries a spread.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

__all__ = [
    "CURRENCIES", "DEFAULT_RATES", "RATES_AS_OF", "RateQuote", "RateTable",
    "symbol", "format_money", "is_supported",
    "fetch_rates", "cached_rates", "save_rates", "load_rates", "cache_path",
]

#: ISO 4217 codes and the symbol used in report headers.
#:
#: CNY and JPY share the glyph ¥; the ISO code is what disambiguates them, which
#: is why every report prints the code alongside the symbol.
CURRENCIES: dict[str, str] = {
    "USD": "$", "CAD": "C$", "EUR": "€", "GBP": "£", "AUD": "A$",
    "MXN": "MX$", "CNY": "¥", "INR": "₹", "BRL": "R$", "JPY": "¥",
}

#: The date :data:`DEFAULT_RATES` was last refreshed from the live feed.
RATES_AS_OF = "2026-08-24"

#: Offline fallback rates, as **units of the target currency per 1 USD**.
#:
#: .. warning::
#:    These are a last resort so the application starts on an air-gapped
#:    machine. They were last checked on :data:`RATES_AS_OF` and float
#:    continuously — by the time you read this they are wrong, and for a
#:    volatile pair such as MXN, BRL or INR they may be wrong by tens of
#:    percent. Refresh with :func:`fetch_rates` or set the rate by hand before
#:    quoting anything. The application shows the age of the rate in use and
#:    warns when it falls back to this table.
DEFAULT_RATES: dict[str, float] = {
    "USD": 1.0,
    "CAD": 1.3849,
    "EUR": 0.85734,
    "GBP": 0.73345,
    "AUD": 1.3963,
    "MXN": 16.9282,
    "CNY": 6.7227,
    "INR": 95.76,
    "BRL": 5.1499,
    "JPY": 159.12,
}

#: Endpoint used by :func:`fetch_rates`. ECB reference rates, no API key.
FEED_URL = "https://api.frankfurter.app/latest"

_CACHE_NAME = "exchange_rates.json"


def is_supported(code: str) -> bool:
    """Is ``code`` a currency teakit knows how to label?

    >>> is_supported("eur"), is_supported("XYZ")
    (True, False)
    """
    return str(code).upper() in CURRENCIES


def symbol(code: str) -> str:
    """Symbol for ``code``, falling back to the code itself.

    >>> symbol("USD"), symbol("EUR"), symbol("XYZ")
    ('$', '€', 'XYZ')
    """
    code = str(code).upper()
    return CURRENCIES.get(code, code)


def format_money(value: float, code: str = "USD", dp: int = 0) -> str:
    """Format ``value`` with the symbol for ``code``.

    >>> format_money(1234567.0, "USD")
    '$1,234,567'
    >>> format_money(1234.5, "EUR", dp=2)
    '€1,234.50'
    """
    return f"{symbol(code)}{value:,.{dp}f}"


# ============================================================================
# Quote
# ============================================================================
@dataclass
class RateQuote:
    """One USD-based rate, with enough provenance to defend it in a report.

    ``rate`` is units of :attr:`currency` per 1 USD, so a USD figure is
    multiplied by it.
    """

    currency: str
    rate: float
    source: str = "offline table"
    as_of: str = RATES_AS_OF
    live: bool = False

    def __post_init__(self) -> None:
        self.currency = str(self.currency).upper()
        self.rate = float(self.rate)
        if self.rate <= 0:
            raise ValueError(f"exchange rate must be positive, got {self.rate}")

    @property
    def stale_days(self) -> int | None:
        """Days since :attr:`as_of`, or ``None`` if it does not parse."""
        try:
            then = datetime.strptime(self.as_of, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        return (date.today() - then).days

    def label(self) -> str:
        """One-line provenance string for a report header.

        >>> RateQuote("EUR", 0.93, "ECB", "2024-06-28").label()
        '1 USD = 0.93 EUR (ECB, 2024-06-28)'
        """
        return (f"1 USD = {self.rate:g} {self.currency} "
                f"({self.source}, {self.as_of})")

    def to_dict(self) -> dict:
        return dict(currency=self.currency, rate=self.rate, source=self.source,
                    as_of=self.as_of, live=self.live)

    @classmethod
    def from_dict(cls, d: dict) -> "RateQuote":
        return cls(currency=d["currency"], rate=d["rate"],
                   source=d.get("source", "unknown"),
                   as_of=d.get("as_of", RATES_AS_OF),
                   live=bool(d.get("live", False)))


@dataclass
class RateTable:
    """A full set of USD-based rates with a single provenance."""

    rates: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RATES))
    source: str = "offline table"
    as_of: str = RATES_AS_OF
    live: bool = False

    def quote(self, code: str) -> RateQuote:
        code = str(code).upper()
        return RateQuote(currency=code, rate=self.rates.get(code, 1.0),
                         source=self.source, as_of=self.as_of, live=self.live)

    def to_dict(self) -> dict:
        return dict(rates=dict(self.rates), source=self.source,
                    as_of=self.as_of, live=self.live)

    @classmethod
    def from_dict(cls, d: dict) -> "RateTable":
        rates = dict(DEFAULT_RATES)
        rates.update({str(k).upper(): float(v)
                      for k, v in (d.get("rates") or {}).items()})
        return cls(rates=rates, source=d.get("source", "unknown"),
                   as_of=d.get("as_of", RATES_AS_OF),
                   live=bool(d.get("live", False)))


# ============================================================================
# Live feed
# ============================================================================
def fetch_rates(codes: list[str] | None = None,
                timeout: float = 6.0) -> RateTable | None:
    """
    Fetch USD-based rates from the ECB feed.

    Returns ``None`` on any failure — no network, DNS blocked, proxy refusing,
    feed down, malformed payload. It never raises, because a cost-estimating
    tool must keep working on a disconnected machine. The caller decides what to
    do with ``None``; the application falls back to the cache, then to
    :data:`DEFAULT_RATES`, and says which it used.

    ``codes`` defaults to every currency in :data:`CURRENCIES`.
    """
    wanted = [c.upper() for c in (codes or CURRENCIES)]
    wanted = [c for c in wanted if c != "USD" and c in CURRENCIES]
    if not wanted:
        return RateTable(rates={"USD": 1.0}, source="USD base",
                         as_of=date.today().isoformat(), live=False)
    try:
        url = f"{FEED_URL}?{urlencode({'base': 'USD', 'symbols': ','.join(wanted)})}"
        req = Request(url, headers={"User-Agent": "teakit/2.0 (+exchange rates)"})
        with urlopen(req, timeout=timeout) as response:   # noqa: S310 — fixed https host
            payload = json.loads(response.read().decode("utf-8"))
        feed = payload.get("rates") or {}
        rates = {"USD": 1.0}
        for code in wanted:
            if code in feed:
                rates[code] = float(feed[code])
        if len(rates) < 2:
            return None
        return RateTable(rates=rates, source="ECB via frankfurter.app",
                         as_of=str(payload.get("date") or date.today().isoformat()),
                         live=True)
    except Exception:                                     # noqa: BLE001
        # Deliberately broad: URLError, HTTPError, socket.timeout, JSONDecodeError,
        # KeyError, ValueError and anything a proxy invents all mean the same
        # thing here — no live rate, carry on offline.
        return None


# ============================================================================
# Cache
# ============================================================================
def cache_path() -> str:
    """
    Where a fetched rate table is cached, per user.

    Windows uses ``%LOCALAPPDATA%\\teakit``, macOS
    ``~/Library/Application Support/teakit``, everything else
    ``$XDG_CACHE_HOME/teakit`` or ``~/.cache/teakit``.
    """
    override = os.environ.get("TEAKIT_CACHE_DIR")
    if override:
        base = override
    elif os.name == "nt":
        base = os.path.join(os.environ.get("LOCALAPPDATA")
                            or os.path.expanduser("~\\AppData\\Local"), "teakit")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/teakit")
    else:
        base = os.path.join(os.environ.get("XDG_CACHE_HOME")
                            or os.path.expanduser("~/.cache"), "teakit")
    return os.path.join(base, _CACHE_NAME)


def save_rates(table: RateTable) -> bool:
    """Write ``table`` to the user cache. Returns whether it was written."""
    path = cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = table.to_dict()
        payload["cached_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def load_rates() -> RateTable | None:
    """Read the cached table, or ``None`` if there is not a usable one."""
    try:
        with open(cache_path(), encoding="utf-8") as fh:
            return RateTable.from_dict(json.load(fh))
    except (OSError, ValueError, KeyError):
        return None


def cached_rates(max_age_days: int = 7, allow_network: bool = True) -> RateTable:
    """
    The best rate table available, cheapest source first.

    Cache if it is younger than ``max_age_days``, otherwise the live feed (when
    ``allow_network``), otherwise the stale cache, otherwise
    :data:`DEFAULT_RATES`. Always returns a usable table.
    """
    cached = load_rates()
    if cached is not None:
        quote = RateQuote("USD", 1.0, cached.source, cached.as_of)
        age = quote.stale_days
        if age is not None and age <= max_age_days:
            return cached
    if allow_network:
        live = fetch_rates()
        if live is not None:
            save_rates(live)
            return live
    if cached is not None:
        return cached
    return RateTable()
