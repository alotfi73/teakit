"""
The Excel export, the workbook writer under it, and the method appendix.

The point of these tests is not that a file appears. It is that the file is a
*valid* workbook — Excel refuses to open a malformed one outright, and there is
no partial credit — and that the live formulas in it reproduce the Python
engine rather than approximating it.
"""

from __future__ import annotations

import re
import xml.dom.minidom
import zipfile
from io import BytesIO

import pytest

import teakit
from teakit import excel, methods, report
from teakit.app import api
from teakit.xlsx import Workbook, cell_ref, col_letter, quote_sheet

DEMOS = ["methanol", "electrolysis", "biorefinery"]
METHODS = ["dcf", "fcr", "simple"]


# ===========================================================================
# the writer
# ===========================================================================
def test_col_letter_and_refs():
    assert col_letter(1) == "A"
    assert col_letter(26) == "Z"
    assert col_letter(27) == "AA"
    assert col_letter(702) == "ZZ"
    assert col_letter(703) == "AAA"
    assert cell_ref(3, 2) == "B3"
    assert cell_ref(3, 2, True) == "$B$3"
    with pytest.raises(ValueError):
        col_letter(0)


def test_quote_sheet_only_when_needed():
    assert quote_sheet("Equipment") == "Equipment"
    assert quote_sheet("Operating cost") == "'Operating cost'"
    assert quote_sheet("it's") == "'it''s'"


def test_sheet_names_are_made_legal_and_unique():
    wb = Workbook()
    assert wb.add_sheet("Cash flow / DCF").name == "Cash flow - DCF"
    assert wb.add_sheet("x" * 40).name == "x" * 31
    assert wb.add_sheet("Same").name == "Same"
    assert wb.add_sheet("Same").name == "Same 2"


def test_equals_prefix_is_a_formula_but_a_labelled_rung_is_not():
    """
    ``"= Total plant cost"`` is a label; ``"=SUM(A1:A9)"`` is a formula.

    Getting this wrong produces a workbook Excel refuses to open, which is
    exactly what happened while this module was being written.
    """
    sh = Workbook().add_sheet("S")
    sh.write(1, 1, "=SUM(A1:A9)")
    assert sh._cells[1][1][2] == "SUM(A1:A9)"      # formula
    sh.write(2, 1, "= Total plant cost (TPC)")
    assert sh._cells[2][1][0] == "= Total plant cost (TPC)"   # literal
    assert sh._cells[2][1][2] is None
    sh.text(3, 1, "=SUM(A1:A9)")
    assert sh._cells[3][1][0] == "=SUM(A1:A9)"     # forced literal


def test_workbook_is_a_valid_zip_of_well_formed_xml():
    wb = Workbook()
    sh = wb.add_sheet("Demo", tab_color="1F6F76")
    head = wb.style(font={"bold": True, "color": "FFFFFF"}, fill="1B6B73",
                    border="thin", align={"h": "center", "wrap": True})
    sh.write_row(1, 1, ["Item", "Cost"], style=head)
    for i, (n, v) in enumerate([("a", 1.5), ("b", 2), ("c", 3)], start=2):
        sh.write(i, 1, n)
        sh.write(i, 2, v, wb.style(fmt="#,##0.00"))
    sh.write(5, 2, "=SUM(B2:B4)")
    sh.merge(6, 1, 6, 2, "merged", head)
    sh.freeze = (1, 1)
    sh.autofilter = "A1:B4"
    sh.data_bar("B2:B4")
    sh.add_chart("column", "t", sh.ref(2, 1, 4, 1),
                 [("Cost", sh.ref(2, 2, 4, 2))], (2, 4))
    sh.add_chart("pie", "p", sh.ref(2, 1, 4, 1),
                 [("Cost", sh.ref(2, 2, 4, 2))], (20, 4))

    data = wb.to_bytes()
    assert data[:2] == b"PK"
    z = zipfile.ZipFile(BytesIO(data))
    assert z.testzip() is None
    for name in z.namelist():
        xml.dom.minidom.parseString(z.read(name))     # raises if malformed
    names = set(z.namelist())
    for required in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
                     "xl/styles.xml", "xl/worksheets/sheet1.xml",
                     "xl/charts/chart1.xml", "xl/drawings/drawing1.xml"):
        assert required in names, required


def test_every_chart_part_is_declared_in_content_types():
    """A part Excel cannot find a content type for makes the file unopenable."""
    p = teakit.demo("methanol")
    z = zipfile.ZipFile(BytesIO(excel.to_xlsx(p, p.run("dcf"))))
    declared = z.read("[Content_Types].xml").decode()
    for name in z.namelist():
        if name.startswith(("xl/charts/", "xl/drawings/")) \
                and name.endswith(".xml"):
            assert f'PartName="/{name}"' in declared, name


def test_styles_indices_referenced_by_cells_all_exist():
    p = teakit.demo("biorefinery")
    z = zipfile.ZipFile(BytesIO(excel.to_xlsx(p, p.run("fcr"))))
    styles = z.read("xl/styles.xml").decode()
    n_xf = len(re.findall(r"<xf ", styles.split("<cellXfs")[1]))
    for name in z.namelist():
        if not name.startswith("xl/worksheets/sheet"):
            continue
        for s in re.findall(r'<c [^>]*s="(\d+)"', z.read(name).decode()):
            assert int(s) < n_xf, f"{name} references style {s} of {n_xf}"


def test_nan_does_not_become_a_silently_wrong_zero():
    sh = Workbook().add_sheet("S")
    sh.write(1, 1, float("nan"))
    assert "n/a" in sh.xml()
    assert "<v>nan</v>" not in sh.xml()


# ===========================================================================
# the workbook teakit actually produces
# ===========================================================================
@pytest.mark.parametrize("kind", DEMOS)
@pytest.mark.parametrize("method", METHODS)
def test_every_demo_and_method_produces_a_valid_workbook(kind, method):
    p = teakit.demo(kind)
    res = p.run(method)
    data = excel.to_xlsx(p, res, {m: None for m in METHODS})
    z = zipfile.ZipFile(BytesIO(data))
    assert z.testzip() is None
    for name in z.namelist():
        xml.dom.minidom.parseString(z.read(name))

    sheets = [s.name for s in excel.build_workbook(p, res).sheets]
    for expected in ("Cover", "Basis", "Equipment", "Capital",
                     "Operating cost", "Products", "Results", "Method"):
        assert expected in sheets
    # A cash flow exists only where a cash flow was modelled.
    assert ("Cash flow" in sheets) == (res.cash_flow is not None)


def test_purchased_and_installed_costs_are_never_added_together():
    """
    The Equipment sheet must subtotal purchased and already-installed costs
    separately. Adding them is the error the whole application warns about, and
    it silently inflates BEC by the installation factor.
    """
    p = teakit.demo("methanol")
    res = p.run("fcr")
    installed = sum(r["cost"] for r in res.equipment_rows if r.get("installed"))
    assert installed > 0, "this demo should carry an already-installed item"

    wb = excel.build_workbook(p, res)
    eq = next(s for s in wb.sheets if s.name == "Equipment")
    labels = [c[0] for row in eq._cells.values() for c in row.values()
              if isinstance(c[0], str)]
    assert "PURCHASED EQUIPMENT COST" in labels
    assert "Already-installed direct cost" in labels
    # and the split is a live SUMIF over the Installed? column, not a constant
    formulas = [c[2] for row in eq._cells.values() for c in row.values() if c[2]]
    assert any(f.startswith('SUMIF(') and '"no"' in f for f in formulas)
    assert any(f.startswith('SUMIF(') and '"yes"' in f for f in formulas)


def test_capital_sheet_uses_the_correct_installation_multiple():
    """
    BEC = f(purchased) + already-installed, so the multiple is
    (BEC - already installed) / purchased. ``installed_direct`` on the result
    is the already-installed entries, which reads like the opposite.
    """
    for kind in DEMOS:
        p = teakit.demo(kind)
        res = p.run("fcr")
        expected = (res.bec - res.installed_direct) / res.purchased_equipment_cost
        wb = excel.build_workbook(p, res)
        cap = next(s for s in wb.sheets if s.name == "Capital")
        values = [c[0] for row in cap._cells.values() for c in row.values()
                  if isinstance(c[0], float)]
        assert any(abs(v - expected) < 1e-9 for v in values), kind


def test_the_workbook_carries_formulas_not_only_numbers():
    p = teakit.demo("methanol")
    wb = excel.build_workbook(p, p.run("dcf"))
    per_sheet = {
        s.name: sum(1 for row in s._cells.values()
                    for c in row.values() if c[2])
        for s in wb.sheets
    }
    for sheet in ("Equipment", "Capital", "Operating cost", "Results"):
        assert per_sheet[sheet] > 5, f"{sheet} has {per_sheet[sheet]} formulas"


def test_formulas_recalculate_on_open():
    """Written without cached values, so Excel must be told to evaluate them."""
    p = teakit.demo("methanol")
    z = zipfile.ZipFile(BytesIO(excel.to_xlsx(p, p.run())))
    assert 'fullCalcOnLoad="1"' in z.read("xl/workbook.xml").decode()


# ===========================================================================
# the method appendix
# ===========================================================================
@pytest.mark.parametrize("kind", DEMOS)
@pytest.mark.parametrize("method", METHODS)
def test_explain_covers_every_stage(kind, method):
    p = teakit.demo(kind)
    secs = methods.explain(p, p.run(method))
    ids = [s["id"] for s in secs]
    assert ids == ["equipment", "installation", "capital", "opex",
                   "allocation", "costing", "result"]
    for s in secs:
        assert s["title"] and s["summary"]
        for eq in s["equations"]:
            assert eq["label"] and eq["expr"]


@pytest.mark.parametrize("kind", DEMOS)
@pytest.mark.parametrize("method", METHODS)
def test_the_cost_build_up_reconciles_to_the_reported_unit_cost(kind, method):
    """
    byproduct_component is a positive magnitude that is *subtracted*. Treating
    it as another addend is an easy mistake and makes the appendix disagree
    with the headline number.
    """
    p = teakit.demo(kind)
    r = p.run(method)
    gross = (r.capital_component + r.fixed_component + r.variable_component)
    assert gross - r.byproduct_component == pytest.approx(r.unit_cost, rel=1e-9)

    steps = {s["label"]: s["detail"]
             for s in methods.explain(p, r)[-1]["steps"]}
    assert "= LEVELISED COST" in steps
    assert f"{r.unit_cost:,.4f}" in steps["= LEVELISED COST"]


def test_only_the_selected_costing_method_is_explained_in_full():
    p = teakit.demo("methanol")
    for method in METHODS:
        sec = next(s for s in methods.explain(p, p.run(method))
                   if s["id"] == "costing")
        assert method in sec["title"]
        for other in METHODS:
            if other != method:
                assert not sec["title"].startswith(f"Costing method: {other}")


def test_option_help_covers_every_choice_the_interface_offers():
    """
    A dropdown option with no explanation is exactly the complaint this help
    text exists to answer, so the coverage is asserted rather than hoped for.
    """
    from teakit.capital import LANG_FACTORS, LOH_DISTRIBUTIVE_FACTORS
    from teakit.opex import FIXED_CONVENTIONS
    from teakit.products import ALLOCATION_METHODS
    from teakit.project import COSTING_METHODS

    help_ = methods.OPTION_HELP
    for value in COSTING_METHODS:
        assert help_["method"].get(value), value
    for value in ALLOCATION_METHODS:
        assert help_["allocation"].get(value), value
    for value in FIXED_CONVENTIONS:
        assert help_["convention"].get(value), value
    for value in ("loh", "lang", "factor"):
        assert help_["installation_method"].get(value), value
    for value in LOH_DISTRIBUTIVE_FACTORS:
        assert help_["loh_service"].get(value), value
    for value in LANG_FACTORS:
        assert help_["lang_type"].get(value), value
    for value in ("catalogue", "custom", "direct"):
        assert help_["equipment_mode"].get(value), value
    # every editable field on an equipment line is explained
    for field in ("size", "base_size", "base_cost", "exponent", "base_year",
                  "size_unit", "quantity", "spare", "material", "section",
                  "direct_cost", "cost_is_installed"):
        assert help_["equipment_param"].get(field), field


def test_help_for_is_forgiving_of_unknown_keys():
    assert methods.help_for("method", "dcf")
    assert methods.help_for("method", "nope") == ""
    assert methods.help_for("nope", "nope") == ""


def test_guide_blocks_are_all_renderable_kinds():
    kinds = {"p", "ul", "eq", "table", "note"}
    for sec in methods.GUIDE:
        assert sec["id"] and sec["title"]
        for b in sec["blocks"]:
            assert b["kind"] in kinds, b["kind"]
            if b["kind"] == "table":
                assert b["headers"]
                for row in b["rows"]:
                    assert len(row) == len(b["headers"])


# ===========================================================================
# reports and the API
# ===========================================================================
def test_reports_end_with_the_method_appendix():
    p = teakit.demo("methanol")
    res = p.run()
    md = report.to_markdown(p, res)
    assert "## Method and calculations" in md
    assert md.index("## Method and calculations") > md.index("## Capital")
    assert "## Method and calculations" not in report.to_markdown(
        p, res, include_method=False)
    assert 'id="method"' in report.to_html(p, res)


def test_api_exports_the_workbook_as_base64():
    import base64
    project = api.demo({"kind": "methanol"})["project"]
    out = api.export({"project": project, "format": "xlsx"})
    assert out["ok"]
    assert out["encoding"] == "base64"
    assert out["filename"].endswith(".xlsx")
    raw = base64.b64decode(out["content"])
    assert raw[:2] == b"PK"
    assert len(raw) == out["bytes"]
    zipfile.ZipFile(BytesIO(raw)).testzip()


def test_meta_ships_the_help_and_the_guide():
    m = api.meta()
    assert m["ok"]
    assert m["option_help"]["method"]["dcf"]
    assert len(m["guide"]) >= 5
    assert m["basis_year"] and m["source"]
    # the catalogue rows carry what the parameter editor needs
    row = m["equipment"][0]
    for key in ("key", "description", "unit", "exponent", "base_size",
                "base_cost", "valid_min", "valid_max", "r_squared"):
        assert key in row, key


def test_run_returns_the_explanation_with_the_result():
    project = api.demo({"kind": "electrolysis"})["project"]
    out = api.run({"project": project, "compare_methods": True})
    assert out["ok"]
    assert [s["id"] for s in out["explanation"]][0] == "equipment"


def test_explain_endpoint():
    project = api.demo({"kind": "biorefinery"})["project"]
    out = api.dispatch("explain", {"project": project})
    assert out["ok"]
    assert len(out["sections"]) == 7
    assert out["guide"]
