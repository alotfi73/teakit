"""
Live application test — boots the real server and drives the real endpoints.

The unit tests in test_acceptance.py exercise ``teakit.app.api`` directly, which
proves the calculation layer works. It does not prove the *application* works:
that also needs the HTTP shim, the static files, and JSON that survives the
round trip. Those are exactly the layers that break silently, so they get their
own test against a real socket.

The frontend is checked structurally rather than executed — running it would
need a JavaScript engine, which teakit will not take as a test dependency. What
is checked is the contract between the two halves: every ``data-path`` the HTML
binds must resolve against a real project field, and every endpoint the
JavaScript calls must exist in the API. A rename on either side fails here.
"""

from __future__ import annotations

import io
import json
import os
import re
import threading
import urllib.error
import urllib.request
import zipfile

import pytest

from teakit import charts, defaults, equipment, excel, indices
from teakit.app import api, server
from teakit.project import Project

STATIC = server.STATIC_DIR


def _demo_project():
    """A fresh copy of the methanol demo, as JSON, for tests that mutate it."""
    return json.loads(json.dumps(api.demo({"kind": "methanol"})["project"]))


# ============================================================================
# live server
# ============================================================================
@pytest.fixture(scope="module")
def live():
    port = server._free_port("127.0.0.1", 8801)
    srv = server.make_server("127.0.0.1", port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()
    srv.server_close()


def post(base, name, payload=None):
    req = urllib.request.Request(
        f"{base}/api/{name}",
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def get(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=30) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "")


class TestServer:

    def test_serves_the_page_and_its_assets(self, live):
        for path, frag in (("/", b"<title>teakit"),
                           ("/app.css", b"--petrol"),
                           ("/app.js", b"renderChart")):
            status, body, _ = get(live, path)
            assert status == 200
            assert frag in body, path

    def test_content_types_are_correct(self, live):
        assert "text/html" in get(live, "/")[2]
        assert "text/css" in get(live, "/app.css")[2]
        assert "javascript" in get(live, "/app.js")[2]

    def test_path_traversal_is_refused(self, live):
        for bad in ("/static/../../../etc/passwd", "/static/..%2f..%2fetc%2fpasswd"):
            try:
                status, body, _ = get(live, bad)
                assert b"root:" not in body
            except urllib.error.HTTPError as e:
                assert e.code in (403, 404)

    def test_full_workflow_over_http(self, live):
        """Load a demo, run it, sweep it, export it — the way the page does."""
        meta = post(live, "meta")
        assert meta["ok"] and len(meta["equipment"]) == 42

        proj = post(live, "demo", {"kind": "methanol"})["project"]

        run = post(live, "run", {"project": proj, "compare_methods": True})
        assert run["ok"]
        assert run["result"]["unit_cost"] > 0
        assert run["charts"]["capex_waterfall"]["kind"] == "waterfall"
        assert run["assumptions"]

        params = post(live, "parameters", {"project": proj})
        assert any(p["path"] == "finance.discount_rate" for p in params["parameters"])

        tor = post(live, "sensitivity", {"project": proj, "kind": "tornado"})
        assert tor["ok"] and tor["data"]["rows"]

        swp = post(live, "sensitivity", {"project": proj, "kind": "sweep",
                                         "path": "finance.discount_rate", "n": 5})
        assert swp["ok"] and len(swp["data"]["x"]) == 5

        rep = post(live, "export", {"project": proj, "format": "html"})
        assert rep["ok"] and rep["content"].startswith("<!doctype html")

        saved = post(live, "export", {"project": proj, "format": "json"})
        reloaded = json.loads(saved["content"])
        again = post(live, "run", {"project": reloaded})
        assert again["result"]["unit_cost"] == pytest.approx(
            run["result"]["unit_cost"], rel=1e-12)

    def test_bad_input_returns_an_error_not_a_crash(self, live):
        r = post(live, "run", {"project": {"equipment": "not a list"}})
        assert r["ok"] is False and r["error"]
        r2 = post(live, "no_such_endpoint")
        assert r2["ok"] is False

    def test_malformed_json_is_rejected_cleanly(self, live):
        req = urllib.request.Request(
            f"{live}/api/run", data=b"{not json",
            headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 400


# ============================================================================
# frontend / backend contract
# ============================================================================
def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as fh:
        return fh.read()


class TestFrontendContract:

    def test_every_bound_field_resolves_to_a_real_project_field(self):
        """Each data-path in the HTML must address something that exists on a
        blank project. A typo here is a control that silently does nothing."""
        html = _read("index.html")
        paths = re.findall(r'data-path="([^"]+)"', html)
        assert len(paths) > 30, "expected the form to bind many fields"
        proj = api.dispatch("blank")["project"]
        for path in paths:
            node = proj
            for part in path.split(".")[:-1]:
                assert isinstance(node, dict) and part in node, path
                node = node[part]
            assert isinstance(node, dict), path
            assert path.split(".")[-1] in node, f"{path} is not a project field"

    def test_every_endpoint_the_page_calls_exists(self):
        js = _read("app.js")
        called = set(re.findall(r"api\(\s*'([a-z_]+)'", js))
        assert called, "expected the page to call the API"
        missing = called - set(api.ENDPOINTS)
        assert not missing, f"page calls endpoints that do not exist: {missing}"

    def test_every_panel_button_has_a_panel(self):
        html = _read("index.html")
        panels = set(re.findall(r'data-panel="([a-z]+)"', html))
        sections = set(re.findall(r'<section class="panel[^"]*" id="p-([a-z]+)"', html))
        assert panels == sections, panels ^ sections

    def test_export_buttons_match_supported_formats(self):
        html = _read("index.html")
        formats = set(re.findall(r'data-export="([a-z_]+)"', html))
        proj = api.dispatch("demo", {"kind": "methanol"})["project"]
        for f in formats:
            r = api.dispatch("export", {"project": proj, "format": f})
            assert r["ok"], f"export format {f} is offered but fails: {r.get('error')}"

    def test_page_loads_no_external_resources(self):
        """It has to work with no network. Any src or href off-origin breaks that."""
        html = _read("index.html")
        for bad in ("http://", "https://", "cdn.", "googleapis", "unpkg"):
            assert bad not in html, bad
        css = _read("app.css")
        assert "@import" not in css and "url(http" not in css

    def test_chart_kinds_the_backend_emits_are_all_renderable(self):
        """Every kind the Python charts module can produce must have a branch in
        the JavaScript renderer, or a figure silently comes out blank."""
        js = _read("app.js")
        import teakit as tea
        r = tea.demo("biorefinery").run()
        kinds = {s.kind for s in tea.default_charts(r).values()}
        kinds |= {"tornado", "line", "histogram", "heatmap", "donut"}
        for k in kinds:
            assert f"'{k}'" in js, f"the page cannot render a {k!r} chart"

    def test_javascript_is_balanced(self):
        """A crude syntax guard: unbalanced braces mean the file will not parse
        and the whole page dies silently."""
        js = _read("app.js")
        stripped = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        stripped = re.sub(r"(?<!:)//[^\n]*", "", stripped)
        for open_c, close_c in (("{", "}"), ("(", ")"), ("[", "]")):
            assert stripped.count(open_c) == stripped.count(close_c), \
                f"unbalanced {open_c}{close_c}"

    def test_packaged_assets_are_reachable_from_the_installed_package(self):
        """Data and interface files must sit inside the package tree, or an
        installed wheel has a working library and a broken application."""
        import teakit
        from teakit import datasets
        root = os.path.dirname(os.path.abspath(teakit.__file__))
        assert os.path.commonpath([root, STATIC]) == root
        assert os.path.commonpath([root, datasets.DATA_DIR]) == root
        assert set(datasets.available()) >= {
            "cepci", "equipment_scaling_factors", "rsmeans_index"}
        assert datasets.load("cepci")[0]["year"]


# ============================================================================
# the cost index, the two costs, and how output and land are entered
# ============================================================================
class TestCostIndex:
    """The dollar-year is chosen from a list that runs past the published
    series, so a study can be costed in a year nobody has an index for yet.
    Such a year has to be refused clearly and then accepted once the user
    supplies the value."""

    def test_year_list_runs_past_the_published_series(self):
        m = api.meta()
        assert max(m["cepci_years"]) == api.YEAR_MAX == 2050
        assert min(m["cepci_years"]) < 1970
        # every published value is still offered, and is still a value
        assert set(m["cepci"]) and 2025 in {int(k) for k in m["cepci"]}
        # the years past the series are offered with no value against them
        assert 2040 in m["cepci_years"] and 2040 not in m["cepci"]

    def test_a_year_with_no_index_is_refused_by_name(self):
        p = _demo_project()
        p["dollar_year"] = 2035
        r = api.run({"project": p})
        assert not r["ok"]
        assert "2035" in r["error"] and "index value" in r["error"]

    def test_a_user_index_makes_that_year_work(self):
        p = _demo_project()
        p["dollar_year"] = 2035
        p["cepci_overrides"] = {"2035": 950.0}
        r = api.run({"project": p})
        assert r["ok"]
        # and it really is the number used: double it and the capital doubles
        p["cepci_overrides"] = {"2035": 1900.0}
        r2 = api.run({"project": p})
        assert r2["ok"]
        assert r2["result"]["bec"] == pytest.approx(2 * r["result"]["bec"], rel=1e-9)

    def test_the_override_is_saved_with_the_project(self):
        p = _demo_project()
        p["cepci_overrides"] = {"2025": 820.0}
        saved = json.loads(api.export({"project": p, "format": "json"})["content"])
        assert saved["cepci_overrides"] == {"2025": 820.0}
        assert Project.from_dict(saved).cepci_overrides == {2025: 820.0}

    def test_an_override_does_not_leak_out_of_the_run(self):
        """The table is installed for the length of one run and taken down
        again, so one project cannot silently reprice the next."""
        p = _demo_project()
        p["cepci_overrides"] = {"2025": 4000.0}
        api.run({"project": p})
        assert indices.CEPCI_USER == {}
        assert indices.cepci(2025) == indices.CEPCI_ANNUAL[2025]

    def test_a_failed_run_still_puts_the_table_back(self):
        p = _demo_project()
        p["cepci_overrides"] = {"2025": 900.0}
        p["products"] = {"products": []}          # guarantees a failure
        assert not api.run({"project": p})["ok"]
        assert indices.CEPCI_USER == {}


class TestInstalledCost:
    """Purchased and installed cost are different numbers by a factor of two
    to four, and both belong on the equipment schedule."""

    def test_every_row_carries_its_installed_cost(self):
        res = api.run({"project": _demo_project()})["result"]
        assert res["installation_factor"] > 1
        for row in res["equipment_rows"]:
            assert "installed_cost" in row and "installation_factor" in row

    def test_the_installed_costs_add_up_to_bec(self):
        res = api.run({"project": _demo_project()})["result"]
        total = sum(r["installed_cost"] for r in res["equipment_rows"])
        assert total == pytest.approx(res["bec"], rel=1e-9)

    def test_an_already_installed_price_is_not_multiplied_again(self):
        res = api.run({"project": _demo_project()})["result"]
        done = [r for r in res["equipment_rows"] if r["installed"]]
        assert done, "the methanol demo carries an installed-price item"
        for r in done:
            assert r["installation_factor"] == 1.0
            assert r["installed_cost"] == pytest.approx(r["cost"])

    def test_the_factor_is_reported_for_every_installation_method(self):
        for method in ("loh", "lang", "factor"):
            p = _demo_project()
            p["capital"]["installation_method"] = method
            res = api.run({"project": p})["result"]
            assert res["installation_factor"] > 1, method
            got = res["purchased_equipment_cost"] * res["installation_factor"]
            assert got + res["installed_direct"] == pytest.approx(res["bec"])


class TestProductBasis:
    """Output is entered the way a feed is — a rate and a basis — so changing
    the operating time moves the product and the feed together."""

    def test_hourly_and_annual_entry_give_the_same_answer(self):
        annual = _demo_project()
        base = api.run({"project": annual})["result"]

        hourly = _demo_project()
        hours = hourly["opex"]["operating_hours"]
        prim = [q for q in hourly["products"]["products"]
                if q["role"] == "primary"][0]
        prim["annual_production"] /= hours
        prim["basis"] = "hour"
        got = api.run({"project": hourly})["result"]

        assert got["unit_cost"] == pytest.approx(base["unit_cost"])
        assert got["annual_production"] == pytest.approx(base["annual_production"])

    def test_an_hourly_product_follows_the_operating_hours(self):
        p = _demo_project()
        hours = p["opex"]["operating_hours"]
        prim = [q for q in p["products"]["products"] if q["role"] == "primary"][0]
        prim["annual_production"] /= hours
        prim["basis"] = "hour"
        before = api.run({"project": p})["result"]["annual_production"]
        p["opex"]["operating_hours"] = hours / 2
        after = api.run({"project": p})["result"]["annual_production"]
        assert after == pytest.approx(before / 2)

    def test_an_annual_product_does_not(self):
        p = _demo_project()
        before = api.run({"project": p})["result"]["annual_production"]
        p["opex"]["operating_hours"] = p["opex"]["operating_hours"] / 2
        after = api.run({"project": p})["result"]["annual_production"]
        assert after == pytest.approx(before)

    def test_the_basis_survives_a_save(self):
        p = _demo_project()
        p["products"]["products"][0]["basis"] = "hour"
        saved = json.loads(api.export({"project": p, "format": "json"})["content"])
        assert saved["products"]["products"][0]["basis"] == "hour"

    def test_a_project_written_before_the_basis_existed_still_loads(self):
        p = _demo_project()
        for q in p["products"]["products"]:
            q.pop("basis", None)
        r = api.run({"project": p})
        assert r["ok"]
        assert Project.from_dict(p).products.products[0].basis == "year"


class TestLandAndCategories:
    def test_land_is_an_amount_and_the_acreage_is_provenance(self):
        p = _demo_project()
        p["capital"]["land_cost"] = 450_000
        p["capital"]["land_area_acres"] = 150
        p["capital"]["land_cost_per_acre"] = 3000
        res = api.run({"project": p})["result"]
        assert res["capital"]["owners_costs"]["land"] == pytest.approx(450_000)
        saved = json.loads(api.export({"project": p, "format": "json"})["content"])
        assert saved["capital"]["land_area_acres"] == 150
        assert saved["capital"]["land_cost_per_acre"] == 3000

    def test_the_acreage_fields_are_not_offered_for_a_sweep(self):
        """They are how the amount was worked out, not an input the model
        reads; sweeping one would sweep a number nothing consumes."""
        paths = {q["path"] for q in api.parameters(
            {"project": _demo_project()})["parameters"]}
        assert "capital.land_cost" in paths
        assert "capital.land_area_acres" not in paths
        assert "capital.land_cost_per_acre" not in paths

    def test_every_variable_line_says_which_category_it_is_in(self):
        """The results panel groups the operating cost and subtotals each
        category, which needs membership, not just the category totals."""
        res = api.run({"project": _demo_project()})["result"]
        op = res["opex"]
        assert set(op["variable_categories"]) == set(op["variable_items"])
        for cat, total in op["by_category"].items():
            lines = [v for k, v in op["variable_items"].items()
                     if op["variable_categories"][k] == cat]
            if lines:
                assert sum(lines) == pytest.approx(total)


# ============================================================================
# equipment types, and the two things that hang off them
# ============================================================================
class TestEquipmentTypes:
    """A type is what lets teakit offer an exponent and an installation factor
    for an item with no catalogue entry behind it."""

    def test_the_vocabulary_reaches_the_interface(self):
        types = api.meta()["equipment_types"]
        names = {t["type"] for t in types}
        assert len(types) > 20
        for expected in ("pump", "compressor", "heat exchanger", "fired heater",
                         "crusher", "distillation column", "reactor", "tank"):
            assert expected in names, expected
        for t in types:
            assert t["exponent"] > 0
            assert t["basis"] in ("fitted", "literature", "six-tenths rule")
            assert t["source"]

    def test_a_fitted_exponent_beats_a_quoted_one(self):
        """The catalogue regressions are cost data; the literature value is a
        rule of thumb. Both are carried, and the fitted one is the default."""
        pump = equipment.type_exponent("pump")
        assert pump["basis"] == "fitted"
        assert pump["n_fitted"] == 7
        assert pump["exponent"] == pytest.approx(pump["fitted"])
        # ...and the cross-check is still there to disagree with
        assert pump["typical"] == pytest.approx(0.60)

    def test_a_type_with_no_correlations_uses_the_literature(self):
        r = equipment.type_exponent("reactor")
        assert r["basis"] == "literature"
        assert r["fitted"] is None
        assert r["exponent"] == pytest.approx(0.60)

    def test_an_unknown_type_falls_back_to_six_tenths_and_says_so(self):
        r = equipment.type_exponent("quench tower")
        assert r["basis"] == "six-tenths rule"
        assert r["exponent"] == pytest.approx(equipment.SIX_TENTHS)
        assert "fallback" in r["source"]

    def test_unreliable_correlations_are_left_out_of_the_median(self):
        """A vibratory centrifuge fitted at n = 3.16 over a 1.2x size span is
        an artefact of the regression, not a statement about centrifuges."""
        r = equipment.type_exponent("centrifuge")
        assert r["basis"] == "literature"
        assert r["exponent"] < 1.0

    def test_every_type_resolves_to_a_real_loh_class(self):
        """A typo in the type table would silently fall back to the plant
        default instead of raising, so the mapping is checked here."""
        from teakit.capital import LOH_DISTRIBUTIVE_FACTORS, LOH_SETTING_FACTORS
        for name in equipment.EQUIPMENT_TYPES:
            b = equipment.type_installation_basis(name)
            assert b["service"] in LOH_DISTRIBUTIVE_FACTORS, name
            assert b["setting"] is None or b["setting"] in LOH_SETTING_FACTORS, name


class TestInstallationByType:
    """The three plant-wide methods multiply the whole purchased total by one
    number. This one gives two machines different factors, which is the
    point of it."""

    def test_it_is_offered(self):
        assert "type" in api.meta()["installation_methods"]

    def test_two_machines_install_at_different_factors(self):
        p = _demo_project()
        p["capital"]["installation_method"] = "type"
        rows = api.run({"project": p})["result"]["equipment_rows"]
        factors = {round(r["installation_factor"], 4)
                   for r in rows if not r["installed"]}
        assert len(factors) > 1, factors

    def test_the_installed_costs_still_add_up_to_bec(self):
        p = _demo_project()
        p["capital"]["installation_method"] = "type"
        res = api.run({"project": p})["result"]
        total = sum(r["installed_cost"] for r in res["equipment_rows"])
        assert total == pytest.approx(res["bec"], rel=1e-9)

    def test_a_type_override_moves_every_item_of_that_type(self):
        p = _demo_project()
        p["capital"]["installation_method"] = "type"
        p["capital"]["type_installation_factors"] = {"pump": 4.0}
        rows = api.run({"project": p})["result"]["equipment_rows"]
        pumps = [r for r in rows if r["category"] == "pump"]
        assert pumps
        for r in pumps:
            assert r["installation_factor"] == pytest.approx(4.0)
            assert r["installed_cost"] == pytest.approx(r["cost"] * 4.0)

    def test_an_item_override_beats_its_type(self):
        p = _demo_project()
        p["capital"]["installation_method"] = "type"
        p["capital"]["type_installation_factors"] = {"pump": 4.0}
        for e in p["equipment"]:
            if e["tag"] == "P-101":
                e["installation_factor"] = 6.0
        rows = api.run({"project": p})["result"]["equipment_rows"]
        got = [r for r in rows if r["tag"] == "P-101"][0]
        assert got["installation_factor"] == pytest.approx(6.0)

    def test_an_already_installed_price_never_meets_a_factor(self):
        p = _demo_project()
        p["capital"]["installation_method"] = "type"
        rows = api.run({"project": p})["result"]["equipment_rows"]
        for r in rows:
            if r["installed"]:
                assert r["installation_factor"] == 1.0

    def test_the_factors_are_saved_with_the_study(self):
        p = _demo_project()
        p["capital"]["installation_method"] = "type"
        p["capital"]["type_installation_factors"] = {"pump": 4.0}
        saved = json.loads(api.export({"project": p, "format": "json"})["content"])
        assert saved["capital"]["type_installation_factors"] == {"pump": 4.0}
        assert saved["capital"]["installation_method"] == "type"

    def test_the_default_for_a_type_is_sourced(self):
        p = Project()
        rec = p.type_installation_factor("fired heater")
        assert rec["known"] and not rec["edited"]
        assert "DOE/NETL-2002/1169" in rec["source"]
        assert 1.5 < rec["factor"] < 4.0

    def test_an_unknown_type_borrows_the_plant_default_and_says_so(self):
        p = Project()
        rec = p.type_installation_factor("quench tower")
        assert not rec["known"]
        assert "plant-level" in rec["source"]

    def test_every_export_survives_the_new_method(self):
        """A hard-coded label lookup on installation_method used to take the
        whole report down with a bare KeyError on an unrecognised key."""
        p = _demo_project()
        p["capital"]["installation_method"] = "type"
        for fmt in ("html", "markdown", "xlsx", "equipment_csv", "opex_csv"):
            r = api.export({"project": p, "format": fmt})
            assert r["ok"], (fmt, r.get("error"))
        r = api.run({"project": p})
        assert r["ok"]
        assert any("type" in a["value"] or "equipment type" in a["value"]
                   for a in r["assumptions"] if a["label"] == "Installation method")

    def test_the_three_older_methods_are_unchanged(self):
        """Adding a fourth option must not move anyone's existing answer."""
        for method, expect in (("loh", 88_717_769), ("lang", None),
                               ("factor", None)):
            p = _demo_project()
            p["capital"]["installation_method"] = method
            res = api.run({"project": p})["result"]
            if expect:
                assert res["bec"] == pytest.approx(expect, rel=1e-6)
            # one factor for the whole list, whichever it is
            factors = {round(r["installation_factor"], 6)
                       for r in res["equipment_rows"] if not r["installed"]}
            assert len(factors) == 1, (method, factors)


class TestIndexYearsInUse:
    """Which cost indices a study actually depends on, and the warning that
    used to fire whether or not 1998 was one of them."""

    def test_every_row_says_the_year_it_was_priced_in(self):
        res = api.run({"project": _demo_project()})["result"]
        for r in res["equipment_rows"]:
            assert r["base_cost_year"] > 1900
        cat = [r for r in res["equipment_rows"] if r["mode"] == "catalogue"]
        assert cat and all(r["base_cost_year"] == 1998 for r in cat)
        direct = [r for r in res["equipment_rows"] if r["mode"] == "direct"]
        assert direct and all(r["base_cost_year"] == 2022 for r in direct)

    def test_the_long_escalation_warning_fires_on_catalogue_items(self):
        res = api.run({"project": _demo_project()})["result"]
        assert any("1998" in w and "AACE Class 5" in w
                   for w in res["warnings"]), res["warnings"]

    def test_and_not_on_a_list_of_vendor_quotes(self):
        """A study built entirely from recent quotes has not been escalated
        27 years, and saying so was simply wrong."""
        p = _demo_project()
        p["equipment"] = [e for e in p["equipment"] if e["mode"] != "catalogue"]
        # keep something to cost against
        assert p["equipment"]
        res = api.run({"project": p})["result"]
        assert not any("1998" in w for w in res["warnings"]), res["warnings"]

    def test_the_warning_says_how_much_of_the_cost_it_covers(self):
        res = api.run({"project": _demo_project()})["result"]
        w = [x for x in res["warnings"] if "1998" in x][0]
        assert "%" in w


# ============================================================================
# rate units, utility distribution, and the chart title band
# ============================================================================
class TestRateUnits:
    """A stream is priced per kWh and drawn in kW. The model keeps the first
    and the screen shows the second."""

    def test_an_hourly_rate_reads_as_a_draw(self):
        assert defaults.rate_unit("kWh", "hour") == "kW"
        assert defaults.rate_unit("MWh", "hour") == "MW"
        assert defaults.rate_unit("m3", "hour") == "m3/h"
        assert defaults.rate_unit("MMBtu", "hour") == "MMBtu/h"

    def test_an_annual_rate_keeps_the_quantity_unit(self):
        assert defaults.rate_unit("kWh", "year") == "kWh"
        assert defaults.rate_unit("tonne", "year") == "tonne"

    def test_an_unknown_unit_still_gets_a_per_hour_form(self):
        assert defaults.rate_unit("widgets", "hour") == "widgets/h"
        assert defaults.rate_unit("", "hour") == ""

    def test_the_per_hour_map_never_changes_the_number(self):
        """Every entry restates the same figure; a conversion factor in there
        would be wrong by exactly that factor. 'gpm (x60)' was."""
        for key, spec in defaults.UNIT_SETS.items():
            for unit, per_hour in spec["per_hour"].items():
                assert "x" not in per_hour.lower().replace("btu", ""), (key, unit)
                assert per_hour, (key, unit)

    def test_the_interface_offers_power_units_on_an_hourly_line(self):
        """The option *values* stay the priced unit; only the labels change,
        which is what keeps the price per kWh while the row reads kW."""
        js = _read("app.js")
        assert "function rateUnit(" in js
        assert "rateUnit(u, line.basis, line.name)" in js

    def test_every_utility_row_carries_the_unit_it_is_read_in(self):
        res = api.run({"project": _demo_project()})["result"]
        rows = res["equipment_utilities"]
        assert rows
        for r in rows:
            assert r["rate_unit"]
            if r["basis"] == "hour" and r["unit"] == "kWh":
                assert r["rate_unit"] == "kW"

    def test_the_csv_carries_both_units(self):
        from teakit import report
        p = api.demo({"kind": "methanol"})["project"]
        res = Project.from_dict(p).run()
        head = report.equipment_utility_csv(res).splitlines()[0]
        assert "rate_unit" in head and "quantity_unit" in head


class TestUtilityDistribution:
    """Every other view answers 'what does it cost'. This one answers 'which
    machines are drawing it'."""

    def test_it_is_on_the_result(self):
        res = api.run({"project": _demo_project()})["result"]
        dist = res["utility_distribution"]
        assert dist
        names = [e["utility"] for e in dist]
        assert "electricity" in names

    def test_each_entry_adds_up(self):
        res = api.run({"project": _demo_project()})["result"]
        for e in res["utility_distribution"]:
            assert e["annual_quantity"] == pytest.approx(
                sum(i["annual_quantity"] for i in e["items"]))
            assert e["annual_cost"] == pytest.approx(
                sum(i["annual_cost"] for i in e["items"]))
            for group in ("by_section", "by_type"):
                assert sum(r["annual_quantity"] for r in e[group]) == pytest.approx(
                    e["annual_quantity"])

    def test_it_reconciles_with_the_operating_cost(self):
        """Plant-level lines are contributors of their own, so the totals are
        the operating cost's totals and not a subset of them."""
        res = api.run({"project": _demo_project()})["result"]
        dist_total = sum(e["annual_cost"] for e in res["utility_distribution"])
        assert dist_total == pytest.approx(res["opex"]["variable_total"], rel=1e-9)

    def test_a_plant_level_line_is_marked_as_unattributable(self):
        res = api.run({"project": _demo_project()})["result"]
        e = [x for x in res["utility_distribution"] if x["utility"] == "electricity"][0]
        sources = {i["source"] for i in e["items"]}
        assert sources == {"equipment", "plant"}
        plant = [i for i in e["items"] if i["source"] == "plant"][0]
        assert plant["tag"] == "" and plant["section"] == "—"

    def test_the_biggest_consumer_is_identified(self):
        res = api.run({"project": _demo_project()})["result"]
        e = [x for x in res["utility_distribution"] if x["utility"] == "electricity"][0]
        assert e["items"][0]["tag"] == "K-101"
        assert e["items"][0]["quantity_share"] > 0.5
        assert e["items"][0]["rate_unit"] == "kW"

    def test_charts_split_it_three_ways(self):
        p = Project.from_dict(_demo_project())
        res = p.run()
        for group in ("item", "section", "type"):
            c = charts.utility_chart(res, "electricity", group)
            assert c.labels and c.values
            assert sum(c.values) == pytest.approx(res.utility_distribution[
                [e["utility"] for e in res.utility_distribution].index("electricity")
            ]["annual_quantity"])

    def test_quantities_are_in_the_utility_unit_and_cost_in_money(self):
        p = Project.from_dict(_demo_project())
        res = p.run()
        q = charts.utility_chart(res, "electricity", "item", "quantity")
        c = charts.utility_chart(res, "electricity", "item", "cost")
        assert q.unit == "kWh" and "kWh/yr" in q.note
        assert c.unit == res.currency and res.currency in c.note

    def test_utilities_are_not_compared_on_quantity(self):
        """kWh, m3 and MMBtu do not share an axis."""
        p = Project.from_dict(_demo_project())
        with pytest.raises(ValueError):
            charts.utility_totals_chart(p.run(), measure="quantity")

    def test_the_endpoint_serves_one_utility(self):
        d = _demo_project()
        r = api.utility_chart({"project": d, "utility": "electricity",
                               "group": "type", "kind": "bar"})
        assert r["ok"]
        assert "compressor" in r["chart"]["labels"]
        assert r["svg"].startswith("<svg")

    def test_an_unknown_utility_is_a_message_not_a_crash(self):
        r = api.utility_chart({"project": _demo_project(), "utility": "unobtainium"})
        assert not r["ok"] and "unobtainium" in r["error"]

    def test_the_run_and_the_report_both_carry_the_figures(self):
        r = api.run({"project": _demo_project()})
        assert "utility_totals" in r["utility_charts"]
        assert any(k.startswith("utility_electricity") for k in r["utility_charts"])
        html = api.export({"project": _demo_project(), "format": "html"})
        assert html["ok"] and "by equipment item" in html["content"]


class TestChartTitleBand:
    """A title drawn into the plot box collides with the plot the moment a bar
    reaches the top of its axis."""

    def _spec_kinds(self):
        p = Project.from_dict(_demo_project())
        res = p.run()
        return charts.default_charts(res)

    def test_every_plotted_kind_gets_a_band(self):
        for name, spec in self._spec_kinds().items():
            svg = spec.svg(760, 400)
            if spec.kind == "donut":
                continue
            assert f'<g transform="translate(0,{charts.TITLE_BAND})">' in svg, name

    def test_a_donut_keeps_its_corner_title(self):
        specs = self._spec_kinds()
        donuts = [s for s in specs.values() if s.kind == "donut"]
        assert donuts
        for spec in donuts:
            assert "translate(0," not in spec.svg(760, 400)

    def test_the_plot_never_reaches_the_title(self):
        """The topmost thing the plot draws, in absolute coordinates, has to
        clear the title's baseline."""
        for name, spec in self._spec_kinds().items():
            if spec.kind == "donut":
                continue
            svg = spec.svg(760, 400)
            body = svg.split(f'translate(0,{charts.TITLE_BAND})">', 1)[1]
            ys = [float(m) for m in re.findall(r'\sy="(-?\d+(?:\.\d+)?)"', body)]
            ys += [float(m) for m in re.findall(r'y1="(-?\d+(?:\.\d+)?)"', body)]
            assert ys, name
            assert min(ys) + charts.TITLE_BAND > 26, (name, min(ys))

    def test_a_chart_with_no_title_wastes_no_space(self):
        c = charts.bar("", {"a": 1, "b": 2})
        assert "translate(0," not in c.svg(400, 200)


# ============================================================================
# the chart set, the utility sheet, and the tornado's ranges
# ============================================================================
class TestChartSet:
    def _specs(self):
        p = Project.from_dict(_demo_project())
        res = p.run()
        specs = charts.default_charts(res)
        specs.update(charts.utility_distribution_charts(res))
        return specs

    def test_the_three_equipment_views_are_all_there(self):
        titles = {s.title for s in self._specs().values()}
        assert "Equipment cost by item" in titles
        assert "Equipment cost by plant section" in titles
        assert "Equipment cost by type" in titles

    def test_a_utility_is_split_by_item_and_by_type(self):
        titles = {s.title for s in self._specs().values()}
        assert "electricity by equipment item" in titles
        assert "electricity by equipment type" in titles

    def test_the_by_type_split_is_skipped_when_it_says_nothing(self):
        """One type is one bar, and a chart of one bar is a table."""
        p = Project.from_dict(_demo_project())
        # Every drawing item is a compressor and nothing is entered at plant
        # level, so there is only one type for the split to find.
        for e in p.equipment:
            e.category = "compressor"
        p.opex.utilities = []
        p.opex.waste = []
        p.opex.other_variable = []
        specs = charts.utility_distribution_charts(p.run())
        assert not any(k.endswith("_by_type") for k in specs), list(specs)

    def test_the_run_hands_them_to_the_interface(self):
        r = api.run({"project": _demo_project()})
        assert any(k.endswith("_by_type") for k in r["utility_charts"])
        assert "equipment_share" in r["charts"]


class TestUtilitySheet:
    def _sheets(self):
        p = Project.from_dict(_demo_project())
        raw = excel.to_xlsx(p, p.run())
        z = zipfile.ZipFile(io.BytesIO(raw))
        return re.findall(r'name="([^"]+)"', z.read("xl/workbook.xml").decode()), raw

    def test_the_workbook_has_a_utilities_tab(self):
        names, _ = self._sheets()
        assert "Utilities" in names
        # between the operating cost it belongs to and the products it feeds
        assert names.index("Operating cost") < names.index("Utilities")
        assert names.index("Utilities") < names.index("Products")

    def test_it_carries_the_consumption_and_who_draws_it(self):
        _, raw = self._sheets()
        z = zipfile.ZipFile(io.BytesIO(raw))
        blob = " ".join(z.read(n).decode("utf-8", "replace")
                        for n in z.namelist() if n.endswith(".xml"))
        assert "UTILITY CONSUMPTION" in blob
        assert "ELECTRICITY — WHO DRAWS IT" in blob
        assert "Rate unit" in blob and "kW" in blob

    def test_a_project_with_no_utilities_simply_has_no_sheet(self):
        p = Project.from_dict(_demo_project())
        p.opex.utilities = []
        p.opex.waste = []
        p.opex.raw_materials = []
        p.opex.other_variable = []
        for e in p.equipment:
            e.utilities = []
        raw = excel.to_xlsx(p, p.run())
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = re.findall(r'name="([^"]+)"', z.read("xl/workbook.xml").decode())
        assert "Utilities" not in names


class TestReportUtilitySection:
    def test_the_html_report_has_a_utilities_section(self):
        j = api.export({"project": _demo_project(), "format": "html"})
        assert j["ok"]
        html = j["content"]
        assert "<h2>Utilities</h2>" in html
        assert "% of variable cost" in html
        # the contributors of whichever utility has the most machines behind
        # it, which is the one worth spelling out
        assert "who draws it" in html
        assert "electricity" in html.split("who draws it", 1)[0][-200:]

    def test_it_carries_the_utility_figures(self):
        j = api.export({"project": _demo_project(), "format": "html"})
        assert "by equipment item" in j["content"]
        assert "by equipment type" in j["content"]

    def test_markdown_gets_the_table_too(self):
        j = api.export({"project": _demo_project(), "format": "markdown"})
        assert "## Utilities" in j["content"]


class TestTornadoRanges:
    """'Low 0.7' with nothing saying whether that is seven tenths of the
    discount rate or a rate of 70% is not a reviewable input."""

    def test_every_parameter_reports_its_current_value_and_auto_range(self):
        j = api.parameters({"project": _demo_project()})
        disc = [p for p in j["parameters"]
                if p["path"] == "finance.discount_rate"][0]
        assert disc["value"] > 0
        assert disc["low_mult"] == pytest.approx(0.70)
        assert disc["high_mult"] == pytest.approx(1.40)
        assert disc["auto_low"] == pytest.approx(disc["value"] * 0.70)
        assert disc["auto_high"] == pytest.approx(disc["value"] * 1.40)

    def test_the_suggested_set_carries_them_as_well(self):
        j = api.parameters({"project": _demo_project()})
        assert j["suggested"]
        for s in j["suggested"]:
            assert s["low_mult"] and s["high_mult"]

    def test_a_multiplier_and_the_value_it_stands_for_agree(self):
        """The interface sends a percentage row as a multiplier and an
        absolute row as a value. Both have to reach the same tornado."""
        d = _demo_project()
        base = [p for p in api.parameters({"project": d})["parameters"]
                if p["path"] == "finance.discount_rate"][0]["value"]
        as_value = api.sensitivity({
            "project": d, "kind": "tornado",
            "params": [{"path": "finance.discount_rate", "label": "discount rate",
                        "low": base * 0.75, "high": base * 1.5}]})
        as_mult = api.sensitivity({
            "project": d, "kind": "tornado",
            "params": [{"path": "finance.discount_rate", "label": "discount rate",
                        "low_mult": 0.75, "high_mult": 1.5}]})
        assert as_value["ok"] and as_mult["ok"]
        a, b = as_value["data"]["rows"][0], as_mult["data"]["rows"][0]
        # the parameter values the two ends were evaluated at...
        assert a["low_param"] == pytest.approx(b["low_param"])
        assert a["high_param"] == pytest.approx(b["high_param"])
        # ...and therefore the answer
        assert a["swing"] == pytest.approx(b["swing"])


class TestFigureTools:
    """The SVG button handed a blob to an <a download>, which does nothing at
    all in the desktop window — the same interface runs in an embedded
    WebView2/WebKit view, where that anchor is inert."""

    def test_the_button_goes_through_the_workspace(self):
        js = _read("app.js")
        assert "async function saveChartSvg(" in js
        assert "workspace_save" in js.split("function saveChartSvg", 1)[1][:1200]

    def test_and_still_falls_back_to_the_browser(self):
        js = _read("app.js").split("function saveChartSvg", 1)[1][:1600]
        assert "download(filename, content, 'image/svg+xml')" in js

    def test_every_figure_gets_both_tools(self):
        js = _read("app.js")
        block = js.split("function figure(spec, w, h)", 1)[1][:1600]
        assert "'Width'" in block and "'SVG'" in block

    def test_the_rail_can_be_collapsed(self):
        assert 'id="btn-rail"' in _read("index.html")
        css = _read("app.css")
        assert "body.rail-min .step .t" in css
        assert "body.rail-min .sheet" in css
