"""
teakit.xlsx — A small, dependency-free writer for real .xlsx workbooks.
=======================================================================

teakit ships with no runtime dependencies, and an Excel export is not a good
enough reason to break that: a plant office on a locked-down machine has to be
able to ``pip install teakit`` and get every feature. An .xlsx file is a ZIP of
XML parts, all of which the standard library can produce, so this module
produces them directly.

What it supports, which is what a costing workbook actually needs:

* several worksheets, each with a coloured tab
* cell styling — fonts, fills, borders, alignment, number formats
* column widths, row heights, merged cells, frozen panes, autofilter
* **live formulas**, so the reader can change an input and watch the estimate
  move, rather than reading a picture of a number
* native Excel charts (column, bar, pie, line) that stay linked to their cells
* data-bar conditional formatting, for in-cell magnitude at a glance

What it deliberately does not support: reading, images, pivot tables, themes,
rich text within a cell. This is a writer for reports, not a spreadsheet engine.

    >>> wb = Workbook()
    >>> sh = wb.add_sheet("Demo", tab_color="1F6F76")
    >>> head = wb.style(font={"bold": True}, fill="E8EFE8")
    >>> sh.write(1, 1, "Item", style=head)
    >>> sh.write(2, 1, "pump"); sh.write(2, 2, 1234.5)
    >>> sh.write(3, 2, "=B2*2")
    >>> wb.to_bytes()[:2] == b"PK"
    True
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO

__all__ = ["Workbook", "Sheet", "col_letter", "cell_ref", "quote_sheet",
           "CHART_PALETTE"]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def esc(value) -> str:
    """XML-escape a value, dropping the control characters XML cannot carry.

    >>> esc('a < b & "c"')
    'a &lt; b &amp; &quot;c&quot;'
    """
    return "".join(_ESCAPES.get(c, c) for c in _CTRL.sub("", str(value)))


def col_letter(idx: int) -> str:
    """1-based column index to its spreadsheet letter.

    >>> col_letter(1), col_letter(27), col_letter(52)
    ('A', 'AA', 'AZ')
    """
    if idx < 1:
        raise ValueError("column index is 1-based")
    out = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def cell_ref(row: int, col: int, absolute: bool = False) -> str:
    """``(2, 3)`` -> ``C2``, or ``$C$2`` when *absolute*.

    >>> cell_ref(2, 3), cell_ref(2, 3, True)
    ('C2', '$C$2')
    """
    d = "$" if absolute else ""
    return f"{d}{col_letter(col)}{d}{row}"


def quote_sheet(name: str) -> str:
    """Sheet name as it must appear inside a formula reference.

    >>> quote_sheet("Cost basis"), quote_sheet("Equipment")
    ("'Cost basis'", 'Equipment')
    """
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


def _argb(color) -> str | None:
    """``"1F6F76"`` / ``"#1F6F76"`` / ``"FF1F6F76"`` -> ``"FF1F6F76"``."""
    if not color:
        return None
    c = str(color).lstrip("#").upper()
    if len(c) == 6:
        c = "FF" + c
    if len(c) != 8:
        raise ValueError(f"colour must be RGB or ARGB hex, got {color!r}")
    return c


def _span(ref: str | None) -> int:
    """How many points a range reference covers — for per-slice pie colouring."""
    if not ref or ":" not in ref:
        return 1
    rows = re.findall(r"\$?([A-Z]{1,3})\$?(\d+)", ref.split("!")[-1])
    if len(rows) != 2:
        return 1
    (c1, r1), (c2, r2) = rows
    return max(abs(int(r2) - int(r1)) + 1, 1)


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
_C_NS = ('xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
         'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
         'relationships"')

#: A muted engineering palette, matching the application's on-screen charts.
CHART_PALETTE = ["1B6B73", "D98324", "4A7C59", "8C4A5F", "3D5A80", "A68A3F",
                 "6B4E71", "2A9D8F", "BC6C25", "577590", "9C6644", "43658B"]


class _Chart:
    """One chart anchored on a sheet. Built through :meth:`Sheet.add_chart`."""

    def __init__(self, kind, title, cat_ref, series, anchor, size, y_title=""):
        self.kind = kind              # column | bar | pie | line
        self.title = title
        self.cat_ref = cat_ref        # "'Sheet'!$A$2:$A$9", or None
        self.series = series          # [(name_or_ref, values_ref), ...]
        self.anchor = anchor          # (row, col), 1-based, top-left corner
        self.size = size              # (width_px, height_px)
        self.y_title = y_title

    def _txt(self, s: str, size: int = 1100, bold: bool = False) -> str:
        b = 1 if bold else 0
        return (f'<c:rich><a:bodyPr/><a:lstStyle/><a:p><a:pPr>'
                f'<a:defRPr sz="{size}" b="{b}"/></a:pPr>'
                f'<a:r><a:rPr lang="en-US" sz="{size}" b="{b}"/>'
                f'<a:t>{esc(s)}</a:t></a:r></a:p></c:rich>')

    def _ser(self, i: int, name, values_ref: str) -> str:
        colour = CHART_PALETTE[i % len(CHART_PALETTE)]
        o = [f'<c:ser><c:idx val="{i}"/><c:order val="{i}"/>']
        if name:
            if isinstance(name, str) and name.startswith("="):
                o.append(f'<c:tx><c:strRef><c:f>{esc(name[1:])}</c:f>'
                         f'</c:strRef></c:tx>')
            else:
                o.append(f'<c:tx><c:v>{esc(name)}</c:v></c:tx>')
        if self.kind == "pie":
            # One coloured point per slice — otherwise every wedge is teal.
            n = _span(values_ref)
            o.append("".join(
                f'<c:dPt><c:idx val="{j}"/><c:bubble3D val="0"/><c:spPr>'
                f'<a:solidFill><a:srgbClr '
                f'val="{CHART_PALETTE[j % len(CHART_PALETTE)]}"/></a:solidFill>'
                f'<a:ln w="12700"><a:solidFill><a:srgbClr val="FFFFFF"/>'
                f'</a:solidFill></a:ln></c:spPr></c:dPt>' for j in range(n)))
        elif self.kind == "line":
            o.append(f'<c:spPr><a:ln w="22225"><a:solidFill>'
                     f'<a:srgbClr val="{colour}"/></a:solidFill></a:ln></c:spPr>'
                     f'<c:marker><c:symbol val="none"/></c:marker>')
        else:
            o.append(f'<c:spPr><a:solidFill><a:srgbClr val="{colour}"/>'
                     f'</a:solidFill></c:spPr>')
        if self.cat_ref:
            o.append(f'<c:cat><c:strRef><c:f>{esc(self.cat_ref)}</c:f>'
                     f'</c:strRef></c:cat>')
        o.append(f'<c:val><c:numRef><c:f>{esc(values_ref)}</c:f></c:numRef></c:val>')
        if self.kind == "line":
            o.append('<c:smooth val="0"/>')
        o.append('</c:ser>')
        return "".join(o)

    def xml(self) -> str:
        ax1, ax2 = 111111111, 222222222
        sers = "".join(self._ser(i, n, v) for i, (n, v) in enumerate(self.series))
        o = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             f'<c:chartSpace {_C_NS}><c:chart>']
        if self.title:
            o.append(f'<c:title><c:tx>{self._txt(self.title, 1200, True)}</c:tx>'
                     f'<c:overlay val="0"/></c:title>'
                     f'<c:autoTitleDeleted val="0"/>')
        else:
            o.append('<c:autoTitleDeleted val="1"/>')
        o.append('<c:plotArea><c:layout/>')

        if self.kind == "pie":
            o.append('<c:pieChart><c:varyColors val="1"/>' + sers +
                     '<c:dLbls><c:showLegendKey val="0"/><c:showVal val="0"/>'
                     '<c:showCatName val="0"/><c:showSerName val="0"/>'
                     '<c:showPercent val="1"/><c:showBubbleSize val="0"/>'
                     '</c:dLbls><c:firstSliceAng val="0"/></c:pieChart>')
        elif self.kind == "line":
            o.append('<c:lineChart><c:grouping val="standard"/>'
                     '<c:varyColors val="0"/>' + sers + '<c:marker val="1"/>'
                     f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/></c:lineChart>')
        else:
            direction = "bar" if self.kind == "bar" else "col"
            o.append(f'<c:barChart><c:barDir val="{direction}"/>'
                     f'<c:grouping val="clustered"/><c:varyColors val="0"/>'
                     + sers + '<c:gapWidth val="60"/>'
                     f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/></c:barChart>')

        if self.kind != "pie":
            cat_pos = "l" if self.kind == "bar" else "b"
            val_pos = "b" if self.kind == "bar" else "l"
            title = (f'<c:title><c:tx>{self._txt(self.y_title, 900)}</c:tx>'
                     f'<c:overlay val="0"/></c:title>') if self.y_title else ""
            o.append(
                f'<c:catAx><c:axId val="{ax1}"/><c:scaling>'
                f'<c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
                f'<c:axPos val="{cat_pos}"/><c:txPr><a:bodyPr/><a:lstStyle/>'
                f'<a:p><a:pPr><a:defRPr sz="900"/></a:pPr>'
                f'<a:endParaRPr lang="en-US"/></a:p></c:txPr>'
                f'<c:crossAx val="{ax2}"/></c:catAx>'
                f'<c:valAx><c:axId val="{ax2}"/><c:scaling>'
                f'<c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
                f'<c:axPos val="{val_pos}"/><c:majorGridlines><c:spPr>'
                f'<a:ln w="9525"><a:solidFill><a:srgbClr val="E4E9E4"/>'
                f'</a:solidFill></a:ln></c:spPr></c:majorGridlines>{title}'
                f'<c:numFmt formatCode="#,##0" sourceLinked="0"/>'
                f'<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr>'
                f'<a:defRPr sz="900"/></a:pPr><a:endParaRPr lang="en-US"/></a:p>'
                f'</c:txPr><c:crossAx val="{ax1}"/></c:valAx>')
        o.append('</c:plotArea>')
        if self.kind == "pie" or len(self.series) > 1:
            o.append('<c:legend><c:legendPos val="b"/><c:overlay val="0"/>'
                     '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr>'
                     '<a:defRPr sz="900"/></a:pPr><a:endParaRPr lang="en-US"/>'
                     '</a:p></c:txPr></c:legend>')
        o.append('<c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart>'
                 '<c:spPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
                 '<a:ln><a:solidFill><a:srgbClr val="D5DCD5"/></a:solidFill>'
                 '</a:ln></c:spPr></c:chartSpace>')
        return "".join(o)


# ---------------------------------------------------------------------------
# worksheet
# ---------------------------------------------------------------------------
class Sheet:
    """One worksheet. Rows and columns are 1-based throughout, as in Excel."""

    def __init__(self, book: Workbook, name: str, tab_color=None):
        self.book = book
        self.name = name
        self.tab_color = _argb(tab_color)
        self._cells: dict[int, dict[int, tuple]] = {}
        self._widths: dict[int, float] = {}
        self._heights: dict[int, float] = {}
        self._merges: list[str] = []
        self._charts: list[_Chart] = []
        self._databars: list[tuple[str, str]] = []
        self.freeze: tuple[int, int] | None = None      # (rows, cols) frozen
        self.autofilter: str | None = None
        self.show_gridlines = True
        self.max_row = 0
        self.max_col = 0

    # -- writing --------------------------------------------------------
    def write(self, row: int, col: int, value=None, style: int | None = None,
              formula: str | None = None) -> None:
        """
        Put *value* in a cell. A string starting with ``=`` is written as a
        formula, which is the point of the Excel export: the reader edits an
        input and the workbook recomputes rather than going stale.

        The ``=`` must be followed immediately by the expression. ``"= Total
        plant cost"`` is a *label*, not a formula — report builders are full of
        rungs named ``"= TPC"``, and writing those as formulas produces a file
        Excel refuses to open. Use :meth:`text` when you want a literal string
        whatever it starts with.

        >>> sh = Workbook().add_sheet("S")
        >>> sh.write(1, 1, "=SUM(B1:B9)"); sh._cells[1][1][2]
        'SUM(B1:B9)'
        >>> sh.write(2, 1, "= Total plant cost"); sh._cells[2][1][0]
        '= Total plant cost'
        """
        if (formula is None and isinstance(value, str)
                and value.startswith("=") and not value[1:2].isspace()
                and len(value) > 1):
            formula, value = value[1:], None
        self._cells.setdefault(row, {})[col] = (value, style, formula)
        self.max_row = max(self.max_row, row)
        self.max_col = max(self.max_col, col)

    def text(self, row: int, col: int, value, style: int | None = None) -> None:
        """
        Write a literal string, never a formula, whatever it starts with.

        >>> sh = Workbook().add_sheet("S")
        >>> sh.text(1, 1, "=SUM(A1)"); sh._cells[1][1][0]
        '=SUM(A1)'
        """
        self._cells.setdefault(row, {})[col] = (
            "" if value is None else str(value), style, None)
        self.max_row = max(self.max_row, row)
        self.max_col = max(self.max_col, col)

    def write_row(self, row: int, col: int, values, style: int | None = None,
                  styles: list | None = None) -> int:
        """Write a sequence left to right; returns the next free column."""
        for i, v in enumerate(values):
            st = style
            if styles and i < len(styles) and styles[i] is not None:
                st = styles[i]
            self.write(row, col + i, v, st)
        return col + len(values)

    def merge(self, row1: int, col1: int, row2: int, col2: int,
              value=None, style: int | None = None) -> None:
        """Merge a rectangle; *value* goes in its top-left cell."""
        if value is not None or style is not None:
            self.write(row1, col1, value, style)
        if style is not None:
            # Excel takes the merged block's borders and fill from every
            # constituent cell, not only the anchor.
            for r in range(row1, row2 + 1):
                for c in range(col1, col2 + 1):
                    if (r, c) != (row1, col1):
                        self.write(r, c, None, style)
        self._merges.append(f"{cell_ref(row1, col1)}:{cell_ref(row2, col2)}")

    def set_width(self, col: int, width: float, last: int | None = None) -> None:
        for c in range(col, (last or col) + 1):
            self._widths[c] = width

    def set_height(self, row: int, height: float) -> None:
        self._heights[row] = height

    def data_bar(self, ref: str, color: str = "1B6B73") -> None:
        """In-cell magnitude bars over a range such as ``"E5:E28"``."""
        self._databars.append((ref, _argb(color)[2:]))

    def add_chart(self, kind: str, title: str, cat_ref: str | None, series,
                  anchor: tuple[int, int], size: tuple[int, int] = (620, 340),
                  y_title: str = "") -> None:
        """
        Anchor a native Excel chart on this sheet.

        ``kind``     ``column`` | ``bar`` | ``pie`` | ``line``
        ``cat_ref``  full reference for the category labels — build it with
                     :meth:`ref`
        ``series``   ``[(name, values_ref), ...]``; a *name* beginning with
                     ``=`` is read as a cell reference for the series title
        ``anchor``   ``(row, col)`` of the chart's top-left corner
        """
        if kind not in ("column", "bar", "pie", "line"):
            raise ValueError(f"unknown chart kind {kind!r}")
        self._charts.append(_Chart(kind, title, cat_ref, list(series), anchor,
                                   size, y_title))

    def ref(self, row1: int, col1: int, row2: int | None = None,
            col2: int | None = None) -> str:
        """An absolute, sheet-qualified reference, ready for a chart or formula.

        >>> Workbook().add_sheet("Cost basis").ref(2, 1, 9, 1)
        "'Cost basis'!$A$2:$A$9"
        """
        a = cell_ref(row1, col1, True)
        if row2 is None:
            return f"{quote_sheet(self.name)}!{a}"
        return f"{quote_sheet(self.name)}!{a}:{cell_ref(row2, col2 or col1, True)}"

    # -- xml ------------------------------------------------------------
    def _cell_xml(self, row: int, col: int, cell: tuple) -> str:
        value, style, formula = cell
        r = cell_ref(row, col)
        s = f' s="{style}"' if style else ""
        if formula is not None:
            return f'<c r="{r}"{s}><f>{esc(formula)}</f></c>'
        if value is None or value == "":
            return f'<c r="{r}"{s}/>' if style else ""
        if isinstance(value, bool):
            return f'<c r="{r}"{s} t="b"><v>{1 if value else 0}</v></c>'
        if isinstance(value, (int, float)):
            if value != value or value in (float("inf"), float("-inf")):
                # NaN and infinity have no numeric spelling in the format; a
                # silent 0 would be a wrong number in a cost estimate.
                return f'<c r="{r}"{s} t="inlineStr"><is><t>n/a</t></is></c>'
            return f'<c r="{r}"{s}><v>{value!r}</v></c>'
        return (f'<c r="{r}"{s} t="inlineStr"><is>'
                f'<t xml:space="preserve">{esc(value)}</t></is></c>')

    def xml(self) -> str:
        o = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
             'officeDocument/2006/relationships">']
        if self.tab_color:
            o.append(f'<sheetPr><tabColor rgb="{self.tab_color}"/></sheetPr>')
        o.append(f'<dimension ref="A1:'
                 f'{cell_ref(max(self.max_row, 1), max(self.max_col, 1))}"/>')

        grid = "" if self.show_gridlines else ' showGridLines="0"'
        o.append(f'<sheetViews><sheetView{grid} workbookViewId="0">')
        if self.freeze:
            fr, fc = self.freeze
            top = cell_ref(fr + 1, fc + 1)
            pane = "bottomRight" if (fr and fc) else ("bottomLeft" if fr
                                                      else "topRight")
            o.append(f'<pane xSplit="{fc}" ySplit="{fr}" topLeftCell="{top}" '
                     f'activePane="{pane}" state="frozen"/>'
                     f'<selection pane="{pane}" activeCell="{top}" sqref="{top}"/>')
        o.append('</sheetView></sheetViews>')
        o.append('<sheetFormatPr defaultRowHeight="15"/>')

        if self._widths:
            o.append('<cols>')
            for c in sorted(self._widths):
                o.append(f'<col min="{c}" max="{c}" '
                         f'width="{self._widths[c]:g}" customWidth="1"/>')
            o.append('</cols>')

        o.append('<sheetData>')
        for row in sorted(self._cells):
            cells = self._cells[row]
            h = self._heights.get(row)
            attr = f' ht="{h:g}" customHeight="1"' if h else ""
            body = "".join(self._cell_xml(row, c, cells[c]) for c in sorted(cells))
            o.append(f'<row r="{row}"{attr}>{body}</row>')
        o.append('</sheetData>')

        if self.autofilter:
            o.append(f'<autoFilter ref="{self.autofilter}"/>')
        if self._merges:
            o.append(f'<mergeCells count="{len(self._merges)}">')
            o += [f'<mergeCell ref="{m}"/>' for m in self._merges]
            o.append('</mergeCells>')
        for i, (ref, colour) in enumerate(self._databars, start=1):
            o.append(f'<conditionalFormatting sqref="{ref}">'
                     f'<cfRule type="dataBar" priority="{i}"><dataBar>'
                     f'<cfvo type="min"/><cfvo type="max"/>'
                     f'<color rgb="FF{colour}"/></dataBar></cfRule>'
                     f'</conditionalFormatting>')
        o.append('<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" '
                 'header="0.3" footer="0.3"/>'
                 '<pageSetup orientation="landscape" fitToWidth="1" '
                 'fitToHeight="0"/>')
        if self._charts:
            o.append('<drawing r:id="rId1"/>')
        o.append('</worksheet>')
        return "".join(o)

    def drawing_xml(self) -> str:
        ns = ('xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/'
              'spreadsheetDrawing" '
              'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"')
        o = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             f'<xdr:wsDr {ns}>']
        for i, ch in enumerate(self._charts, start=1):
            r0, c0 = ch.anchor
            # A default column is about 64 px wide and a default row 20 px tall.
            c1 = c0 + max(1, round(ch.size[0] / 64))
            r1 = r0 + max(1, round(ch.size[1] / 20))
            o.append(
                f'<xdr:twoCellAnchor editAs="oneCell">'
                f'<xdr:from><xdr:col>{c0 - 1}</xdr:col><xdr:colOff>0</xdr:colOff>'
                f'<xdr:row>{r0 - 1}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
                f'<xdr:to><xdr:col>{c1 - 1}</xdr:col><xdr:colOff>0</xdr:colOff>'
                f'<xdr:row>{r1 - 1}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
                f'<xdr:graphicFrame macro="">'
                f'<xdr:nvGraphicFramePr><xdr:cNvPr id="{i + 1}" '
                f'name="Chart {i}"/><xdr:cNvGraphicFramePr/>'
                f'</xdr:nvGraphicFramePr>'
                f'<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
                f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/'
                f'drawingml/2006/chart"><c:chart '
                f'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
                f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                f'relationships" r:id="rId{i}"/></a:graphicData></a:graphic>'
                f'</xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>')
        o.append('</xdr:wsDr>')
        return "".join(o)


# ---------------------------------------------------------------------------
# workbook
# ---------------------------------------------------------------------------
class Workbook:
    """
    A workbook under construction. Build sheets, then :meth:`to_bytes` or
    :meth:`save`.

    Styles are interned: calling :meth:`style` with the same specification
    twice returns the same id, so a sheet with ten thousand styled cells still
    carries a handful of style records.
    """

    def __init__(self, title: str = "teakit report", creator: str = "teakit"):
        self.title = title
        self.creator = creator
        self.sheets: list[Sheet] = []
        self._numfmts: dict[str, int] = {}
        self._fonts: dict[tuple, int] = {}
        self._fills: dict[tuple, int] = {}
        self._borders: dict[tuple, int] = {}
        self._xfs: dict[tuple, int] = {}
        self._seed()

    # -- sheets ---------------------------------------------------------
    def add_sheet(self, name: str, tab_color=None) -> Sheet:
        """
        Add a worksheet.

        Excel forbids ``[]:*?/\\`` in a sheet name, caps it at 31 characters
        and requires it to be unique. All three are enforced here rather than
        producing a file Excel refuses to open.

        >>> wb = Workbook()
        >>> wb.add_sheet("Cash flow / DCF").name
        'Cash flow - DCF'
        >>> wb.add_sheet("Same").name, wb.add_sheet("Same").name
        ('Same', 'Same 2')
        """
        clean = re.sub(r"[\[\]:*?/\\]", "-", str(name)).strip("'")[:31] or "Sheet"
        existing = {s.name.lower() for s in self.sheets}
        if clean.lower() in existing:
            stem = clean[:28].rstrip()
            for i in range(2, 100):
                cand = f"{stem} {i}"
                if cand.lower() not in existing:
                    clean = cand
                    break
        sh = Sheet(self, clean, tab_color)
        self.sheets.append(sh)
        return sh

    # -- styles ---------------------------------------------------------
    def _seed(self) -> None:
        """The records Excel requires to exist at fixed indices in styles.xml."""
        self._fonts[("Calibri", 11.0, False, False, False, "FF1C2B2D")] = 0
        self._fills[("none", None)] = 0
        self._fills[("gray125", None)] = 1
        self._borders[(None, None, None, None, None)] = 0
        self._xfs[(0, 0, 0, 0, None)] = 0

    def _font(self, spec: dict) -> int:
        key = (str(spec.get("name", "Calibri")), float(spec.get("size", 11)),
               bool(spec.get("bold")), bool(spec.get("italic")),
               bool(spec.get("underline")),
               _argb(spec.get("color")) or "FF1C2B2D")
        return self._fonts.setdefault(key, len(self._fonts))

    def _fill(self, spec) -> int:
        if not spec:
            return 0
        colour = _argb(spec if isinstance(spec, str) else spec.get("color"))
        if not colour:
            return 0
        return self._fills.setdefault(("solid", colour), len(self._fills))

    def _border(self, spec) -> int:
        if not spec:
            return 0
        if isinstance(spec, str):                    # "thin" — all four sides
            spec = {"all": spec}
        colour = _argb(spec.get("color") or "FFC6D0C6")
        every = spec.get("all")
        sides = []
        for side in ("left", "right", "top", "bottom"):
            style = spec.get(side, every) or every
            sides.append((style, colour) if style else None)
        key = tuple(sides) + (colour,)
        return self._borders.setdefault(key, len(self._borders))

    def _numfmt(self, code) -> int:
        if not code:
            return 0
        builtin = {"General": 0, "0": 1, "0.00": 2, "#,##0": 3, "#,##0.00": 4,
                   "0%": 9, "0.00%": 10}
        if code in builtin:
            return builtin[code]
        if code not in self._numfmts:
            self._numfmts[code] = 164 + len(self._numfmts)
        return self._numfmts[code]

    def style(self, font: dict | None = None, fill=None, border=None,
              fmt: str | None = None, align: dict | None = None) -> int:
        """
        Intern a cell style and return its id.

        ``font``   ``{"bold": True, "size": 12, "color": "FFFFFF"}``
        ``fill``   a hex colour, applied as a solid fill
        ``border`` ``"thin"`` for all four sides, or per-side
                   ``{"bottom": "medium", "color": "1B6B73"}``
        ``fmt``    an Excel number-format code, e.g. ``'#,##0'``, ``'0.0%'``
        ``align``  ``{"h": "center", "v": "center", "wrap": True, "indent": 1}``
        """
        fid = self._font(font) if font else 0
        lid = self._fill(fill)
        bid = self._border(border)
        nid = self._numfmt(fmt)
        akey = None
        if align:
            akey = (align.get("h"), align.get("v"), bool(align.get("wrap")),
                    int(align.get("indent", 0)), int(align.get("rotate", 0)))
        return self._xfs.setdefault((nid, fid, lid, bid, akey), len(self._xfs))

    def _styles_xml(self) -> str:
        o = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<styleSheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main">']
        if self._numfmts:
            o.append(f'<numFmts count="{len(self._numfmts)}">')
            for code, i in sorted(self._numfmts.items(), key=lambda kv: kv[1]):
                o.append(f'<numFmt numFmtId="{i}" formatCode="{esc(code)}"/>')
            o.append('</numFmts>')

        o.append(f'<fonts count="{len(self._fonts)}">')
        for name, size, bold, italic, under, colour in sorted(
                self._fonts, key=self._fonts.get):
            bits = ("<b/>" if bold else "") + ("<i/>" if italic else "") \
                + ("<u/>" if under else "")
            o.append(f'<font>{bits}<sz val="{size:g}"/><color rgb="{colour}"/>'
                     f'<name val="{esc(name)}"/><family val="2"/></font>')
        o.append('</fonts>')

        o.append(f'<fills count="{len(self._fills)}">')
        for pattern, colour in sorted(self._fills, key=self._fills.get):
            if pattern == "solid":
                o.append(f'<fill><patternFill patternType="solid">'
                         f'<fgColor rgb="{colour}"/><bgColor indexed="64"/>'
                         f'</patternFill></fill>')
            else:
                o.append(f'<fill><patternFill patternType="{pattern}"/></fill>')
        o.append('</fills>')

        o.append(f'<borders count="{len(self._borders)}">')
        for key in sorted(self._borders, key=self._borders.get):
            parts = []
            for side, spec in zip(("left", "right", "top", "bottom"),
                                  key[:4], strict=True):
                if spec:
                    parts.append(f'<{side} style="{spec[0]}">'
                                 f'<color rgb="{spec[1]}"/></{side}>')
                else:
                    parts.append(f'<{side}/>')
            o.append('<border>' + "".join(parts) + '<diagonal/></border>')
        o.append('</borders>')

        o.append('<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" '
                 'fillId="0" borderId="0"/></cellStyleXfs>')
        o.append(f'<cellXfs count="{len(self._xfs)}">')
        for nid, fid, lid, bid, akey in sorted(self._xfs, key=self._xfs.get):
            applied = ""
            if nid:
                applied += ' applyNumberFormat="1"'
            if fid:
                applied += ' applyFont="1"'
            if lid:
                applied += ' applyFill="1"'
            if bid:
                applied += ' applyBorder="1"'
            attrs = (f'numFmtId="{nid}" fontId="{fid}" fillId="{lid}" '
                     f'borderId="{bid}" xfId="0"' + applied)
            if akey:
                h, v, wrap, indent, rotate = akey
                a = "".join([f' horizontal="{h}"' if h else "",
                             f' vertical="{v}"' if v else "",
                             ' wrapText="1"' if wrap else "",
                             f' indent="{indent}"' if indent else "",
                             f' textRotation="{rotate}"' if rotate else ""])
                o.append(f'<xf {attrs} applyAlignment="1">'
                         f'<alignment{a}/></xf>')
            else:
                o.append(f'<xf {attrs}/>')
        o.append('</cellXfs>')
        o.append('<cellStyles count="1"><cellStyle name="Normal" xfId="0" '
                 'builtinId="0"/></cellStyles></styleSheet>')
        return "".join(o)

    # -- package --------------------------------------------------------
    def to_bytes(self) -> bytes:
        """The finished .xlsx, as bytes."""
        if not self.sheets:
            self.add_sheet("Sheet1")
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for path, data in self._parts():
                z.writestr(path, data)
        return buf.getvalue()

    def save(self, path: str) -> str:
        """Write the workbook to *path*; returns the path."""
        with open(path, "wb") as fh:
            fh.write(self.to_bytes())
        return path

    def _parts(self):
        R = "http://schemas.openxmlformats.org/package/2006/relationships"
        OD = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        SS = "application/vnd.openxmlformats-officedocument.spreadsheetml"
        DR = "application/vnd.openxmlformats-officedocument.drawing+xml"
        CH = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"

        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
              'content-types">',
              '<Default Extension="rels" ContentType="application/vnd.'
              'openxmlformats-package.relationships+xml"/>',
              '<Default Extension="xml" ContentType="application/xml"/>',
              f'<Override PartName="/xl/workbook.xml" '
              f'ContentType="{SS}.sheet.main+xml"/>',
              f'<Override PartName="/xl/styles.xml" '
              f'ContentType="{SS}.styles+xml"/>',
              '<Override PartName="/docProps/core.xml" ContentType="application/'
              'vnd.openxmlformats-package.core-properties+xml"/>',
              '<Override PartName="/docProps/app.xml" ContentType="application/'
              'vnd.openxmlformats-officedocument.extended-properties+xml"/>']
        chart_no = 0
        for i, sh in enumerate(self.sheets, start=1):
            ct.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                      f'ContentType="{SS}.worksheet+xml"/>')
            if sh._charts:
                ct.append(f'<Override PartName="/xl/drawings/drawing{i}.xml" '
                          f'ContentType="{DR}"/>')
                for _ in sh._charts:
                    chart_no += 1
                    ct.append(f'<Override PartName="/xl/charts/'
                              f'chart{chart_no}.xml" ContentType="{CH}"/>')
        ct.append('</Types>')
        yield "[Content_Types].xml", "".join(ct)

        yield "_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{R}">'
            f'<Relationship Id="rId1" Type="{OD}/officeDocument" '
            f'Target="xl/workbook.xml"/>'
            f'<Relationship Id="rId2" Type="{OD}/extended-properties" '
            f'Target="docProps/app.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/'
            'package/2006/relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/></Relationships>')

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        yield "docProps/core.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/'
            'package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{esc(self.title)}</dc:title>'
            f'<dc:creator>{esc(self.creator)}</dc:creator>'
            f'<cp:lastModifiedBy>{esc(self.creator)}</cp:lastModifiedBy>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            '</cp:coreProperties>')
        yield "docProps/app.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/'
            'officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
            f'docPropsVTypes"><Application>{esc(self.creator)}</Application>'
            '<Company/></Properties>')

        wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<workbook xmlns="http://schemas.openxmlformats.org/'
              f'spreadsheetml/2006/main" xmlns:r="{OD}"><sheets>']
        for i, sh in enumerate(self.sheets, start=1):
            wb.append(f'<sheet name="{esc(sh.name)}" sheetId="{i}" '
                      f'r:id="rId{i}"/>')
        # fullCalcOnLoad: formulas are written without cached results, so Excel
        # must evaluate them on open or every formula cell would read as zero.
        wb.append('</sheets><calcPr calcId="0" fullCalcOnLoad="1"/></workbook>')
        yield "xl/workbook.xml", "".join(wb)

        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                f'<Relationships xmlns="{R}">']
        for i in range(1, len(self.sheets) + 1):
            rels.append(f'<Relationship Id="rId{i}" Type="{OD}/worksheet" '
                        f'Target="worksheets/sheet{i}.xml"/>')
        rels.append(f'<Relationship Id="rId{len(self.sheets) + 1}" '
                    f'Type="{OD}/styles" Target="styles.xml"/></Relationships>')
        yield "xl/_rels/workbook.xml.rels", "".join(rels)
        yield "xl/styles.xml", self._styles_xml()

        chart_no = 0
        for i, sh in enumerate(self.sheets, start=1):
            yield f"xl/worksheets/sheet{i}.xml", sh.xml()
            if not sh._charts:
                continue
            yield (f"xl/worksheets/_rels/sheet{i}.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<Relationships xmlns="{R}"><Relationship Id="rId1" '
                   f'Type="{OD}/drawing" Target="../drawings/drawing{i}.xml"/>'
                   f'</Relationships>')
            yield f"xl/drawings/drawing{i}.xml", sh.drawing_xml()
            dr = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                  f'<Relationships xmlns="{R}">']
            for j, ch in enumerate(sh._charts, start=1):
                chart_no += 1
                dr.append(f'<Relationship Id="rId{j}" Type="{OD}/chart" '
                          f'Target="../charts/chart{chart_no}.xml"/>')
                yield f"xl/charts/chart{chart_no}.xml", ch.xml()
            dr.append('</Relationships>')
            yield f"xl/drawings/_rels/drawing{i}.xml.rels", "".join(dr)


if __name__ == "__main__":  # pragma: no cover
    import doctest
    print(doctest.testmod())
