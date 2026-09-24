"""
tea.indices — Cost indices and escalation between dollar-years.
==============================================================

Everything in a TEA has a *dollar year*. Equipment correlations, vendor quotes
and published baselines are all anchored to a particular point in time, and the
first thing you must do before adding two numbers together is bring them to a
common basis.

The workhorse relation is::

    C_new = C_old * (Index_new / Index_old)

SOURCES
-------
Chemical Engineering Plant Cost Index (CEPCI), 1957-59 = 100.
    Published by Chemical Engineering magazine (Access Intelligence LLC).
    Composite of four sub-indices (Equipment, Construction Labor, Buildings,
    Engineering & Supervision) built from ~41 US BLS Producer Price Indices.
    https://www.chemengonline.com/pci-home/

    Annual values 2001-2023 and monthly Jan-Jun 2024 as republished at
    https://toweringskills.com/financial-analysis/cost-indices/
    Sub-index values and the 2016-2023 annual series are confirmed directly
    from the CE "Economic Indicators" page, September 2024 issue:
    https://www.chemengonline.com/wp-content/uploads/2024/08/19_CHE_0924_EconInd_p45.pdf

    !! IMPORTANT !! Effective September 2024, Access Intelligence stopped
    publishing the CEPCI in the free print/online magazine. It is now only
    available behind a paid subscription (~US$699/yr) at
    https://www.chemengonline.com/pci. Values in this module for 2024 and
    later are therefore marked PROVISIONAL — see CEPCI_PROVISIONAL below and
    replace them with subscription values if you have access.

Historical CEPCI 1957-59 through 2001 as tabulated in:
    Loh, H.P., Lyons, J., White, C.W. III, "Process Equipment Cost Estimation,
    Final Report", DOE/NETL-2002/1169, January 2002, Table 11.
    https://www.osti.gov/servlets/purl/797810

Free alternatives (recommended when CEPCI is unavailable):
    US BLS Producer Price Indices, https://www.bls.gov/data/
    FRED, https://fred.stlouisfed.org/  (e.g. series WPU1076 for pumps/compressors)
    US BEA Chained Price Index for Private Nonresidential Structures.
"""

from __future__ import annotations

from contextlib import contextmanager

# ----------------------------------------------------------------------------
# CEPCI annual averages (1957-59 = 100)
# ----------------------------------------------------------------------------
# The annual value is the arithmetic mean of that year's twelve monthly values.
CEPCI_ANNUAL: dict[int, float] = {
    # --- Loh et al. (DOE/NETL-2002/1169) Table 11 -----------------------------
    1964: 103.0, 1965: 104.0, 1970: 126.0, 1975: 182.0, 1980: 261.0,
    1985: 325.0, 1990: 357.6, 1995: 381.1, 1996: 381.8, 1997: 386.5,
    1998: 389.5, 1999: 390.6, 2000: 394.1,
    # --- Chemical Engineering, as republished by Towering Skills -------------
    2001: 394.3, 2002: 395.6, 2003: 402.0, 2004: 444.2, 2005: 468.2,
    2006: 499.6, 2007: 525.4, 2008: 575.4, 2009: 521.9, 2010: 550.8,
    2011: 585.7, 2012: 584.6, 2013: 567.3, 2014: 576.1, 2015: 556.8,
    2016: 541.7, 2017: 567.5, 2018: 603.1, 2019: 607.5, 2020: 596.2,
    2021: 708.8, 2022: 816.0, 2023: 797.9,
    # --- PROVISIONAL, see note below ----------------------------------------
    2024: 797.5,
    2025: 810.3,
}

#: Years whose values are estimated rather than taken from a published table.
CEPCI_PROVISIONAL: dict[int, str] = {
    2024: (
        "ESTIMATE. Monthly values Jan-Jun 2024 are published "
        "(795.4, 800.0, 800.7, 799.5, 800.2, 798.8; mean 799.1) and Chemical "
        "Engineering reported the index 'hovering around 800' all year with "
        "declines in Jul/Aug/Sep and Nov/Dec. 797.5 is a reasonable central "
        "estimate; the true annual average is very likely 795-800."
    ),
    2025: (
        "ESTIMATE. Chemical Engineering reported (April 2026) that the 2025 "
        "annual average was 1.6% above 2024. 810.3 = 797.5 x 1.016. Carries "
        "the uncertainty of the 2024 estimate. Replace with the published "
        "value if you have a CE subscription."
    ),
}

# ----------------------------------------------------------------------------
# User-supplied index values
# ----------------------------------------------------------------------------
#: CEPCI values supplied by the user, ``{year: value}``, consulted before
#: :data:`CEPCI_ANNUAL`.
#:
#: Two things need this. The shipped table stops at 2025, so a study costed in
#: 2030 dollars has no index to escalate to and must be given one. And the
#: 2024/2025 values here are estimates (see :data:`CEPCI_PROVISIONAL`), so
#: anyone with a Chemical Engineering subscription should be able to replace
#: them with the published figures without editing the library.
#:
#: A user value replaces the whole year -- quarters and months included --
#: because supplying one is a deliberate statement about that year and a
#: silently-preferred monthly value would contradict it.
#:
#: The table is empty unless something installs one, so nothing about the
#: library's behaviour changes until a project asks for it. A project installs
#: its own for the duration of a run; see :func:`user_cepci`.
CEPCI_USER: dict[int, float] = {}


def _clean_index(values: dict | None) -> dict[int, float]:
    """
    ``{year: value}`` with the keys as ints and anything unusable dropped.

    JSON has no integer keys, so a project round-tripped through a file comes
    back with ``"2030"`` rather than ``2030``. Blanks are dropped rather than
    stored as zero: "I have not filled this in yet" and "the index is zero"
    must not become the same state.
    """
    out: dict[int, float] = {}
    for k, v in (values or {}).items():
        if v is None or v == "":
            continue
        try:
            year, val = int(k), float(v)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out[year] = val
    return out


def set_user_cepci(values: dict | None) -> dict[int, float]:
    """Replace :data:`CEPCI_USER`. Returns the table it replaced.

    >>> prev = set_user_cepci({"2030": 900.0})
    >>> cepci(2030)
    900.0
    >>> _ = set_user_cepci(prev)
    """
    global CEPCI_USER
    prev = CEPCI_USER
    CEPCI_USER = _clean_index(values)
    return prev


@contextmanager
def user_cepci(values: dict | None):
    """
    Install user index values for the duration of a block, then put back
    whatever was there before.

    Escalation happens in half a dozen places -- equipment correlations,
    vendor quotes, utility prices -- and threading an index table through all
    of them would mean changing every signature between here and the caller.
    A scoped override keeps :func:`cepci` as the single place the value is
    looked up, and the ``finally`` makes a failed run leave nothing behind.

    >>> with user_cepci({2030: 900.0}):
    ...     round(escalate(100.0, 2025, 2030), 2)
    111.07
    >>> 2030 in CEPCI_USER
    False
    """
    prev = set_user_cepci(values)
    try:
        yield CEPCI_USER
    finally:
        set_user_cepci(prev)


def available_years() -> list[int]:
    """Every year an index value can be had for, shipped or user-supplied."""
    return sorted(set(CEPCI_ANNUAL) | set(CEPCI_USER))


def has_cepci(year: int) -> bool:
    """Whether :func:`cepci` will answer for `year` rather than raise."""
    return int(year) in CEPCI_ANNUAL or int(year) in CEPCI_USER


# ----------------------------------------------------------------------------
# CEPCI monthly values, where published free-of-charge
# ----------------------------------------------------------------------------
CEPCI_MONTHLY: dict[tuple[int, int], float] = {
    (2024, 1): 795.4, (2024, 2): 800.0, (2024, 3): 800.7,
    (2024, 4): 799.5, (2024, 5): 800.2, (2024, 6): 798.8,
}

# ----------------------------------------------------------------------------
# CEPCI sub-indices — useful when the cost you are escalating is dominated by
# one category (e.g. a compressor package, or a labour-heavy install).
# Values from CE "Economic Indicators", September 2024 issue.
# ----------------------------------------------------------------------------
CEPCI_SUBINDEX_2024_06: dict[str, float] = {
    "CE Index (composite)":        798.8,
    "Equipment":                  1004.0,
    "Heat exchangers & tanks":     798.7,
    "Process machinery":          1029.6,
    "Pipe, valves & fittings":    1355.5,
    "Process instruments":         582.5,
    "Pumps & compressors":        1543.1,
    "Electrical equipment":        832.3,
    "Structural supports & misc.":1112.9,
    "Construction labor":          375.7,
    "Buildings":                   801.0,
    "Engineering & supervision":   315.2,
}

# ----------------------------------------------------------------------------
# Other North American indices, for cross-checking CEPCI
# ----------------------------------------------------------------------------
#: RSMeans Historical Cost Index (Jan 1993 = 100), quarterly.
#: Source: https://toweringskills.com/financial-analysis/cost-indices/
RSMEANS_QUARTERLY: dict[tuple[int, int], float] = {
    (2020, 1): 239.1, (2020, 2): 235.6, (2020, 3): 234.6, (2020, 4): 235.5,
    (2021, 1): 238.3, (2021, 2): 241.7, (2021, 3): 257.5, (2021, 4): 266.6,
    (2022, 1): 276.9, (2022, 2): 289.4, (2022, 3): 297.1, (2022, 4): 298.8,
    (2023, 1): 299.4, (2023, 2): 294.8, (2023, 3): 293.7, (2023, 4): 295.4,
    (2024, 1): 295.6, (2024, 2): 295.5, (2024, 3): 294.8, (2024, 4): 296.3,
    (2025, 1): 293.9, (2025, 2): 295.8, (2025, 3): 300.7, (2025, 4): 304.2,
    (2026, 1): 303.4, (2026, 2): 309.6,
}


# ============================================================================
# Look-ups
# ============================================================================
def cepci(year: int, quarter: int | None = None, month: int | None = None) -> float:
    """
    Return the CEPCI for a year, or for a quarter/month within that year.

    Parameters
    ----------
    year : int
    quarter : int, optional
        1-4. Returns the mean of that quarter's monthly values if all three
        are available, otherwise falls back to the annual average.
    month : int, optional
        1-12. Takes precedence over ``quarter``.

    Notes
    -----
    Monthly CEPCI values are only free-of-charge through June 2024. For any
    later period this function returns the annual average and the caller
    should treat the result as an approximation.

    A value in :data:`CEPCI_USER` wins over everything, at every resolution:
    supplying one is a statement about that whole year.

    Examples
    --------
    >>> round(cepci(2022), 1)
    816.0
    >>> round(cepci(2024, quarter=1), 2)
    798.7
    """
    if year in CEPCI_USER:
        return CEPCI_USER[year]

    if month is not None:
        key = (year, month)
        if key in CEPCI_MONTHLY:
            return CEPCI_MONTHLY[key]
        if year in CEPCI_ANNUAL:
            return CEPCI_ANNUAL[year]
        raise KeyError(f"No CEPCI available for {year}-{month:02d}")

    if quarter is not None:
        if quarter not in (1, 2, 3, 4):
            raise ValueError("quarter must be 1, 2, 3 or 4")
        months = [(quarter - 1) * 3 + k for k in (1, 2, 3)]
        vals = [CEPCI_MONTHLY[(year, m)] for m in months if (year, m) in CEPCI_MONTHLY]
        if len(vals) == 3:
            return sum(vals) / 3.0
        if year in CEPCI_ANNUAL:
            return CEPCI_ANNUAL[year]
        raise KeyError(f"No CEPCI available for {year} Q{quarter}")

    if year in CEPCI_ANNUAL:
        return CEPCI_ANNUAL[year]
    raise KeyError(
        f"No CEPCI for {year}. The published series runs "
        f"{min(CEPCI_ANNUAL)}-{max(CEPCI_ANNUAL)}; to cost in {year} dollars, "
        f"supply an index value for {year} (Project.cepci_overrides, or the "
        f"cost-index table on the Project panel)."
    )


def is_provisional(year: int) -> str | None:
    """Return the provenance warning for `year`, or None if the value is published.

    A user-supplied value is never provisional: the user is the authority on a
    number they typed.
    """
    if year in CEPCI_USER:
        return None
    return CEPCI_PROVISIONAL.get(year)


# ============================================================================
# Escalation
# ============================================================================
def escalate(cost: float,
             from_year: int,
             to_year: int,
             from_quarter: int | None = None,
             to_quarter: int | None = None,
             index: dict | None = None) -> float:
    """
    Escalate a cost between dollar-years using CEPCI (or a supplied index).

    C_to = C_from * (I_to / I_from)

    Parameters
    ----------
    cost : float
        Cost in `from_year` dollars.
    from_year, to_year : int
    from_quarter, to_quarter : int, optional
        Use quarterly resolution where available.
    index : dict, optional
        Substitute {year: value} mapping (e.g. an RSMeans or BLS PPI series).
        If given, quarters are ignored.

    Returns
    -------
    float
        Cost in `to_year` dollars.

    Caution
    -------
    Cost engineers generally advise against escalating more than ~5 years with
    a single index, and treat >10 years as order-of-magnitude only, because the
    index composition, construction practice and productivity all drift
    (Loh et al. 2002, "Cost Indexes" section). Escalating a 1998 correlation to
    today spans 25+ years — expect the index correction alone to carry
    tens of percent of error, on top of the correlation's own +50%/-30%.

    Examples
    --------
    >>> round(escalate(1_000_000, 2018, 2022))
    1353009
    """
    if index is not None:
        return cost * (index[to_year] / index[from_year])
    i_from = cepci(from_year, quarter=from_quarter)
    i_to = cepci(to_year, quarter=to_quarter)
    return cost * (i_to / i_from)


def escalate_by_index(cost: float, index_from: float, index_to: float) -> float:
    """Escalate using raw index values rather than years. C_to = C * I_to / I_from."""
    return cost * (index_to / index_from)


def index_ratio(from_year: int, to_year: int,
                from_quarter: int | None = None,
                to_quarter: int | None = None) -> float:
    """Return the bare CEPCI ratio I_to / I_from."""
    return cepci(to_year, quarter=to_quarter) / cepci(from_year, quarter=from_quarter)


def inflate(cost: float, rate: float, years: float) -> float:
    """
    Escalate at a constant compound rate — used when no index exists for the
    forward-looking period (e.g. projecting 2026 dollars to a 2030 online year).

    C = C0 * (1 + rate) ** years
    """
    return cost * (1.0 + rate) ** years


def real_to_nominal(rate_real: float, inflation: float) -> float:
    """
    Fisher relation: (1 + r_nom) = (1 + r_real)(1 + i).

    >>> round(real_to_nominal(0.0514, 0.0201), 4)
    0.0725
    """
    return (1.0 + rate_real) * (1.0 + inflation) - 1.0


def nominal_to_real(rate_nominal: float, inflation: float) -> float:
    """
    Inverse Fisher relation: (1 + r_real) = (1 + r_nom) / (1 + i).

    >>> round(nominal_to_real(0.0725, 0.0201), 4)
    0.0514
    """
    return (1.0 + rate_nominal) / (1.0 + inflation) - 1.0
