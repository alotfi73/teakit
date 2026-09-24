"""
teakit.datasets — The bundled reference data, as files and as rows.
===================================================================

The Python modules hold the data as literals so that importing teakit costs no
file I/O and so the values are visible in the source. The same data also ships
as CSV, because a cost engineer checking your work wants a spreadsheet, not a
dataclass.

    >>> from teakit import datasets
    >>> sorted(datasets.available())            # doctest: +ELLIPSIS
    ['cepci', 'column_correlations', ...]
    >>> rows = datasets.load("cepci")
    >>> rows[0]["year"]
    '1964'
    >>> datasets.path("cepci").endswith("cepci.csv")
    True

FILES
-----
``equipment_scaling_factors``  the 42 fitted single-parameter correlations, with
    R^2, relative RMSE, point count, validity range and a reliability flag.
``column_correlations``        6 two-parameter column correlations.
``packing_costs``              tower packing, $/ft^3 on a 1998 Q1 basis.
``cepci``                      CEPCI annual, quarterly and monthly, 1964-2025,
    with a status column marking provisional values.
``rsmeans_index``              RSMeans Historical Cost Index, quarterly, as an
    independent cross-check on CEPCI escalation.
``netl_plant_section_exponents``  273 account-level scaling exponents for PC,
    IGCC and NGCC plant sections, December 2018 basis.

PROVENANCE
----------
All equipment cost data derives from Loh, Lyons & White (2002),
*Process Equipment Cost Estimation, Final Report*, DOE/NETL-2002/1169,
Appendix B — a U.S. government work in the public domain.
The plant-section exponents derive from NETL's *QGESS: Capital Cost Scaling
Methodology*, Rev. 4/4a.
CEPCI values are compiled from *Chemical Engineering* magazine; the index itself
is proprietary to Access Intelligence and the values are reproduced here as
factual data for escalation, as they are in every published cost study.
"""

from __future__ import annotations

import csv
import os

__all__ = ["available", "path", "load", "load_raw", "DATA_DIR"]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def available() -> list[str]:
    """Names of the bundled datasets, without the ``.csv`` extension."""
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(f[:-4] for f in os.listdir(DATA_DIR) if f.endswith(".csv"))


def path(name: str) -> str:
    """Absolute path to a bundled CSV. Raises :class:`FileNotFoundError`."""
    p = os.path.join(DATA_DIR, f"{name}.csv")
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"No dataset {name!r}. Available: {', '.join(available())}")
    return p


def load(name: str) -> list[dict]:
    """Read a bundled CSV into a list of dicts. Values stay as strings —
    teakit does no type inference on your behalf."""
    with open(path(name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_raw(name: str) -> str:
    """The raw file text, for when you want to hand it to pandas or a
    spreadsheet."""
    with open(path(name), encoding="utf-8") as fh:
        return fh.read()


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
