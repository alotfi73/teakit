"""
Acceptance tests — pinned to published government reference values.

The point of this file is not coverage. It is that a change to teakit which
breaks agreement with NETL-PUB-22580, DOE/NETL-2002/1169 or NREL/TP-5100-47764
fails loudly. A self-referential unit test that asserts today's output equals
today's output would catch none of that.

Run: pytest -q
"""

from __future__ import annotations

import json
import math

import pytest

import teakit as tea
from teakit import opex, products
from teakit.project import EquipmentItem, Project


# ============================================================================
# 1. Published reference values
# ============================================================================
class TestPublishedReferences:
    """Numbers that appear in the source documents, reproduced exactly."""

    def test_loh_appendix_a_installed_cost(self):
        """DOE/NETL-2002/1169 Appendix A worked example: $62,000 of bare
        exchanger becomes $150,245 installed."""
        r = tea.installed_cost_loh(62_000, "gas_gt400F_lt150psig", "heat exchanger")
        assert round(r["installed_cost"]) == 150_245

    def test_netl_tasc_over_toc_real(self):
        """NETL-PUB-22580: 3-year build, real basis, TASC/TOC = 1.093."""
        f = tea.tasc_over_toc(0.0514, 0.0, [0.10, 0.60, 0.30])["tasc_over_toc"]
        assert round(f, 3) == 1.093

    def test_netl_tasc_over_toc_five_year_real(self):
        """5-year build, real basis, TASC/TOC = 1.154."""
        f = tea.tasc_over_toc(0.0514, 0.0,
                              [0.10, 0.30, 0.25, 0.20, 0.15])["tasc_over_toc"]
        assert round(f, 3) == 1.154

    def test_netl_fixed_charge_rate(self):
        """NETL-PUB-22580 Exhibit 3-6: real FCR 0.0707 at a 4.73% real ATWACC,
        30-year book life, 20-year MACRS, 25.74% tax."""
        assert round(tea.fcr(0.0473, 30, 0.2574, 20), 4) == 0.0707

    def test_netl_nominal_fixed_charge_rate(self):
        """Nominal FCR 0.0886 at the 6.54% nominal ATWACC. Tolerance is 2e-4
        because NETL publishes the ATWACC itself rounded to three figures, so
        the last digit of the FCR cannot be reproduced exactly from it."""
        assert tea.fcr(tea.NETL_FINANCE_IOU["nominal"]["atwacc"], 30, 0.2574, 20) \
            == pytest.approx(0.0886, abs=2e-4)

    def test_capital_ratio_bec_to_tpc(self):
        """BEC 500 -> EPCC 587.5 at a 17.5% fee -> TPC 705.0 at 20% project
        contingency. NETL-PUB-22580 §2.1-2.4 arithmetic."""
        r = tea.NETLCapitalCost(bec=500e6, construction_years=3,
                                basis="real").evaluate()
        assert round(r.epcc / 1e6, 1) == 587.5
        assert round(r.tpc / 1e6, 1) == 705.0

    def test_crf_textbook(self):
        """Capital recovery factor, 10% over 20 years = 0.117460."""
        assert round(tea.crf(0.10, 20), 6) == 0.117460

    def test_cepci_1998_basis(self):
        """The correlations' basis year. CEPCI 1998 annual = 389.5."""
        assert tea.cepci(1998) == pytest.approx(389.5, abs=0.1)

    def test_macrs_schedules_sum_to_one(self):
        for years in (3, 5, 7, 10, 15, 20):
            assert sum(tea.macrs_schedule(years)) == pytest.approx(1.0, abs=1e-6)

    def test_turton_com_formula(self):
        """COM_d = 0.180 FCI + 2.73 C_OL + 1.23 (C_UT + C_WT + C_RM)."""
        r = opex.turton_com(100e6, 2.5e6, 4e6, 1e6, 40e6)
        assert r["COM_d"] == pytest.approx(
            0.180 * 100e6 + 2.73 * 2.5e6 + 1.23 * 45e6)

    def test_dcf_irr_equals_discount_rate_at_msp(self):
        """The defining property of a minimum selling price: priced at MSP, the
        project returns exactly the discount rate."""
        m = tea.CashFlowModel(total_capital=400e6, annual_production=30e6,
                              annual_fixed_opex=18e6, annual_variable_opex=65e6,
                              discount_rate=0.10, plant_life_years=30)
        msp = m.minimum_selling_price()
        res = m.run(msp)
        assert res.irr == pytest.approx(0.10, abs=1e-4)
        assert res.npv == pytest.approx(0.0, abs=1.0)


# ============================================================================
# 2. Invariants that must hold for any input
# ============================================================================
class TestInvariants:

    def test_capital_ladder_is_monotone(self):
        r = tea.NETLCapitalCost(bec=100e6, process_contingency_frac=0.10).evaluate()
        assert r.bec < r.epcc < r.tpc < r.toc < r.tasc

    def test_reliable_exponents_are_physically_plausible(self):
        """A fitted exponent outside 0.2-1.3 means the regression is wrong, not
        that the equipment is unusual. Three correlations in the source data do
        fall outside it — a vibrating centrifuge fitted over a 1.2x size span, a
        gyratory crusher, and a small steam turbine. The requirement is not that
        they are absent, but that every one of them is flagged unreliable with a
        reason, so a user cannot reach a bad number without being told."""
        for key, rec in tea.EQUIPMENT.items():
            if 0.2 <= rec["exponent"] <= 1.3:
                continue
            assert rec.get("reliable") is False, f"{key} is out of bounds but not flagged"
            assert rec.get("caution"), f"{key} is flagged but carries no reason"

    def test_unreliable_correlations_warn_the_caller(self):
        """Costing an unreliable correlation must put the caution in the notes."""
        bad = [k for k, v in tea.EQUIPMENT.items() if v.get("reliable") is False]
        assert bad, "expected the catalogue to flag some weak fits"
        for key in bad:
            rec = tea.EQUIPMENT[key]
            r = tea.purchased_cost(key, (rec["valid_min"] + rec["valid_max"]) / 2,
                                   quiet=True)
            assert any("UNRELIABLE" in n for n in r.notes), key

    def test_cost_rises_with_size(self):
        for key in list(tea.EQUIPMENT)[:12]:
            rec = tea.EQUIPMENT[key]
            lo, hi = rec["valid_min"], rec["valid_max"]
            a = tea.purchased_cost(key, lo * 1.01, quiet=True).cost
            b = tea.purchased_cost(key, hi * 0.99, quiet=True).cost
            assert b > a, key

    def test_economy_of_scale_holds(self):
        """Doubling size must less than double cost, for every exponent < 1."""
        for key, rec in tea.EQUIPMENT.items():
            if rec["exponent"] >= 1.0:
                continue
            lo, hi = rec["valid_min"], rec["valid_max"]
            s = lo * 1.05
            if s * 2 > hi:
                continue
            c1 = tea.purchased_cost(key, s, quiet=True).cost
            c2 = tea.purchased_cost(key, s * 2, quiet=True).cost
            assert c2 < 2 * c1, key

    def test_oversize_duty_splits_into_parallel_trains(self):
        """Past the largest shop-fabricable unit, cost becomes linear. Silently
        extrapolating the power law here is a classic way to underestimate."""
        key = "hx_shell_tube"
        rec = tea.EQUIPMENT[key]
        r = tea.purchased_cost(key, rec["valid_max"] * 3.2, quiet=True)
        assert r.n_units >= 4

    def test_extrapolation_refused_by_default(self):
        rec = tea.EQUIPMENT["pump_centrifugal"]
        with pytest.raises(ValueError):
            tea.purchased_cost("pump_centrifugal", rec["valid_min"] * 0.01,
                               use_multiple_units=False, quiet=True)

    def test_escalation_is_reversible(self):
        c = 1_000_000.0
        assert tea.escalate(tea.escalate(c, 2000, 2024), 2024, 2000) == \
            pytest.approx(c, rel=1e-9)

    def test_material_factor_ordering(self):
        """Rotating machinery takes a smaller alloy penalty than static
        equipment: less of its cost is wetted metal."""
        assert tea.material_factor("pump", "ss316") < \
            tea.material_factor("separator", "ss316")

    def test_higher_discount_rate_raises_levelised_cost(self):
        p = _small_project()
        lo = p.copy(); lo["finance.discount_rate"] = 0.05
        hi = p.copy(); hi["finance.discount_rate"] = 0.15
        assert hi.run().unit_cost > lo.run().unit_cost

    def test_simple_method_understates(self):
        """The 'simple' method charges no cost of capital, so it must come out
        below the DCF at any positive discount rate."""
        comp = _small_project().method_comparison()
        assert comp["simple"] < comp["dcf"]


# ============================================================================
# 3. Operating cost
# ============================================================================
class TestOperatingCost:

    def test_capacity_factor_scales_variable_not_fixed(self):
        base = dict(fci=100e6, installed_equipment_cost=60e6,
                    raw_materials=[opex.Stream("feed", 10, "t", 500)],
                    labor=opex.LaborModel(operators_per_shift=4))
        full = opex.OperatingCost(**base, capacity_factor=1.0).evaluate()
        half = opex.OperatingCost(**base, capacity_factor=0.5).evaluate()
        assert half.variable_total == pytest.approx(full.variable_total * 0.5)
        assert half.fixed_total == pytest.approx(full.fixed_total)

    def test_pinned_line_ignores_capacity_factor(self):
        s = opex.Stream("take-or-pay gas", 1e6, "yr", 1.0, basis="year",
                        scales_with_rate=False)
        assert s.annual_cost(8000, 0.5) == pytest.approx(1e6)

    def test_opex_excludes_depreciation(self):
        """A structural guarantee: there is nowhere in the OPEX model to put
        depreciation, so it cannot be double-counted against the capital charge."""
        r = opex.OperatingCost(fci=100e6,
                               labor=opex.LaborModel(operators_per_shift=2)).evaluate()
        joined = " ".join(r.items).lower()
        assert "deprec" not in joined
        assert "interest" not in joined

    def test_conventions_differ_but_agree_in_order(self):
        kw = dict(fci=200e6, installed_equipment_cost=120e6,
                  labor=opex.LaborModel(operators_per_shift=5))
        totals = {c: opex.OperatingCost(**kw, convention=c).evaluate().fixed_total
                  for c in ("NREL", "Peters & Timmerhaus", "NETL")}
        assert max(totals.values()) < 4 * min(totals.values())

    def test_turton_operator_correlation(self):
        """Solids handling dominates the operator count — that is the whole
        point of the correlation."""
        assert opex.operators_turton(20, 0) < opex.operators_turton(20, 1)


# ============================================================================
# 4. Products and allocation
# ============================================================================
class TestAllocation:

    def _slate(self):
        return products.ProductSlate([
            products.Product("main", 1000, "t", role="primary"),
            products.Product("side", 500, "t", price=200, role="byproduct"),
        ])

    def test_byproduct_credit_subtracts_revenue(self):
        r = self._slate().allocate(1_000_000)
        assert r.cost_to_primary == pytest.approx(1_000_000 - 500 * 200)

    def test_allocation_shares_sum_to_one(self):
        s = products.ProductSlate([
            products.Product("a", 1000, "t", price=900, role="primary"),
            products.Product("b", 500, "t", price=1100, role="coproduct"),
        ], method="market value")
        r = s.allocate(1e6)
        assert sum(r.shares.values()) == pytest.approx(1.0)

    def test_dominant_credit_is_flagged(self):
        s = products.ProductSlate([
            products.Product("main", 100, "t", role="primary"),
            products.Product("side", 1000, "t", price=800, role="byproduct"),
        ])
        r = s.allocate(1_000_000)
        assert any("leveraged" in n or "negative" in n for n in r.notes)

    def test_exactly_one_primary_required(self):
        s = products.ProductSlate([
            products.Product("a", 1, "t", role="primary"),
            products.Product("b", 1, "t", role="primary"),
        ])
        with pytest.raises(ValueError):
            s.primary()

    def test_mass_allocation_ignores_price(self):
        s = products.ProductSlate([
            products.Product("a", 1000, "t", price=10, role="primary"),
            products.Product("b", 1000, "t", price=10_000, role="coproduct"),
        ], method="mass")
        assert s.allocate(1e6).shares["a"] == pytest.approx(0.5)


# ============================================================================
# 5. Project pipeline
# ============================================================================
class TestProject:

    def test_json_round_trip_is_lossless(self):
        p = tea.demo("methanol")
        q = Project.from_json(p.to_json())
        assert q.to_dict() == p.to_dict()
        assert q.run().unit_cost == pytest.approx(p.run().unit_cost, rel=1e-12)

    def test_dotted_paths_read_and_write(self):
        p = _small_project()
        p["finance.discount_rate"] = 0.13
        assert p["finance.discount_rate"] == 0.13
        p["opex.raw_materials.feed.price"] = 555.0
        assert p.opex.raw_materials[0].price == 555.0
        p["equipment.E-101.size"] = 7000
        assert p.equipment[0].size == 7000

    def test_copy_is_isolated(self):
        p = _small_project()
        q = p.copy()
        q["finance.discount_rate"] = 0.99
        assert p.finance.discount_rate != 0.99

    def test_parameters_are_generated_not_hardcoded(self):
        paths = {q["path"] for q in _small_project().parameters()}
        assert "finance.discount_rate" in paths
        assert "capital.project_contingency_frac" in paths
        assert any(q.startswith("equipment.") for q in paths)

    def test_installed_cost_bypasses_installation_factors(self):
        """A vendor's installed price must not be multiplied by an installation
        factor again."""
        base = _small_project()
        base.equipment.append(EquipmentItem(
            "Q-1", mode="direct", direct_cost=10e6, cost_is_installed=True))
        with_installed = base.run().bec

        base2 = _small_project()
        base2.equipment.append(EquipmentItem(
            "Q-1", mode="direct", direct_cost=10e6, cost_is_installed=False))
        with_purchased = base2.run().bec
        assert with_purchased > with_installed + 5e6

    def test_custom_correlation_matches_hand_calculation(self):
        e = EquipmentItem("X-1", mode="custom", size=2000, base_cost=100_000,
                          base_size=1000, exponent=0.6, base_year=2025)
        assert e.evaluate(2025)["cost"] == pytest.approx(100_000 * 2 ** 0.6)

    def test_all_three_demos_run(self):
        for kind in ("methanol", "electrolysis", "biorefinery"):
            r = tea.demo(kind).run()
            assert r.unit_cost > 0
            assert math.isfinite(r.unit_cost)

    def test_biorefinery_demo_near_nrel_published_mesp(self):
        """NREL's cellulosic ethanol design cases land around $2.15-2.50/gal in
        recent dollars. A demo built on the same conventions should sit in that
        neighbourhood; a large drift means something upstream changed."""
        r = tea.demo("biorefinery").run()
        assert 1.4 < r.unit_cost < 4.0, r.unit_cost

    def test_missing_product_is_a_clear_error(self):
        p = Project(dollar_year=2025)
        p.equipment = [EquipmentItem("E-101", kind="hx_shell_tube", size=5000)]
        with pytest.raises(ValueError, match="no products"):
            p.run()

    def test_unreliable_correlation_reaches_the_project_warnings(self):
        """teakit.project always costs with quiet=True. The caution must still
        surface — otherwise a weak fit reaches a report unflagged."""
        p = Project(dollar_year=2025, method="fcr")
        p.equipment = [EquipmentItem("C-1", kind="centrifuge_vibratory", size=52)]
        p.products.products = [products.Product("w", 1000, "t")]
        assert any("UNRELIABLE" in w for w in p.run().warnings)

    def test_long_escalation_raises_a_warning(self):
        r = _small_project().run()
        assert any("escalated" in w.lower() for w in r.warnings)


# ============================================================================
# 6. Sensitivity
# ============================================================================
class TestSensitivity:

    def test_tornado_is_sorted_by_swing(self):
        t = tea.tornado(_small_project(),
                        ["finance.discount_rate", "opex.raw_materials.feed.price"])
        swings = [r["swing"] for r in t.rows]
        assert swings == sorted(swings, reverse=True)

    def test_sweep_is_monotone_in_discount_rate(self):
        s = tea.sweep(_small_project(), "finance.discount_rate", n=5)
        assert s.y == sorted(s.y)

    def test_monte_carlo_is_reproducible(self):
        p = _small_project()
        d = {"finance.discount_rate": {"low": 0.06, "high": 0.15}}
        a = tea.monte_carlo(p, d, n=30, seed=7)
        b = tea.monte_carlo(p, d, n=30, seed=7)
        assert a.samples == b.samples

    def test_percentiles_are_ordered(self):
        r = tea.monte_carlo(_small_project(),
                            {"finance.discount_rate": {"low": 0.06, "high": 0.15}},
                            n=60, seed=3)
        p = r.percentiles
        assert p["P10"] <= p["P50"] <= p["P90"]

    def test_breakeven_inverts_the_model(self):
        p = _small_project()
        base = p.run().unit_cost
        target = base * 0.92
        x = tea.breakeven(p, "opex.raw_materials.feed.price", target)
        assert x is not None
        p["opex.raw_materials.feed.price"] = x
        assert p.run().unit_cost == pytest.approx(target, rel=1e-4)

    def test_integer_parameters_stay_integers(self):
        """Plant life is a count, not a quantity. A continuous sweep that hands
        the model 27.3 years used to fail every trial silently — the parameter
        simply vanished from the tornado."""
        s = tea.sweep(_small_project(), "finance.plant_life_years", n=6)
        assert s.x, "integer parameter produced no points at all"
        assert all(float(v).is_integer() for v in s.x), s.x
        assert len(s.y) == len(s.x)

    def test_plant_life_appears_in_an_automatic_tornado(self):
        p = tea.demo("electrolysis")
        labels = [r["label"] for r in tea.tornado(p).rows]
        assert any("plant life" in l for l in labels), labels

    def test_monte_carlo_over_the_suggested_set_succeeds(self):
        """suggest_params must only offer parameters that can actually be
        sampled — one unresolvable path used to abort the whole run."""
        p = tea.demo("electrolysis")
        d = {s.path: {} for s in tea.suggest_params(p, 6)}
        r = tea.monte_carlo(p, d, n=25, seed=1)
        assert r.n_failed == 0, r.notes
        assert len(r.samples) == 25

    def test_unsampleable_paths_are_skipped_not_fatal(self):
        p = _small_project()
        r = tea.monte_carlo(p, {"finance.discount_rate": {},
                                "opex.maintenance_frac_capital": {}},
                            n=10, seed=1)
        assert len(r.samples) == 10
        assert any("skipped" in n for n in r.notes)

    def test_sensitivity_does_not_mutate_the_project(self):
        p = _small_project()
        before = p.to_json()
        tea.tornado(p, ["finance.discount_rate"])
        assert p.to_json() == before


# ============================================================================
# 7. Charts and reports
# ============================================================================
class TestOutput:

    def test_every_default_chart_renders_valid_svg(self):
        r = tea.demo("methanol").run()
        for name, spec in tea.default_charts(r).items():
            svg = spec.svg()
            assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>"), name

    def test_equipment_chart_does_not_hide_a_mixed_cost_basis(self):
        """The methanol demo mixes purchased and already-installed items. A
        chart that shows both without saying so repeats the exact error the
        capital cascade refuses to make."""
        r = tea.demo("methanol").run()
        spec = tea.charts.equipment_share_chart(r)
        installed = [row["tag"] for row in r.equipment_rows if row["installed"]]
        assert installed, "the demo should contain an installed-basis item"
        assert "mixed basis" in spec.note
        assert any(tag in lbl and "installed" in lbl
                   for tag in installed for lbl in spec.labels)

    def test_purchased_only_chart_excludes_installed_items(self):
        r = tea.demo("methanol").run()
        spec = tea.charts.equipment_share_chart(r, purchased_only=True)
        assert not any("installed" in lbl for lbl in spec.labels)
        assert sum(spec.values) == pytest.approx(r.purchased_equipment_cost, rel=1e-9)

    def test_chart_specs_are_json_serialisable(self):
        """The app hands these to JavaScript; anything unserialisable breaks it."""
        r = tea.demo("electrolysis").run()
        for spec in tea.default_charts(r).values():
            json.loads(json.dumps(spec.to_dict()))

    def test_html_report_is_self_contained(self):
        p = tea.demo("methanol")
        html = tea.report.to_html(p, p.run())
        assert "<svg" in html
        # The only permitted http reference is the SVG XML namespace, which is
        # an identifier and is never fetched.
        stripped = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
        for external in ("http://", "https://", "<script", "<link", "@import"):
            assert external not in stripped, external

    def test_csv_exports_have_headers(self):
        r = tea.demo("biorefinery").run()
        assert tea.report.equipment_csv(r).splitlines()[0].startswith("tag,")
        assert tea.report.cash_flow_csv(r).splitlines()[0].startswith("year,")

    def test_assumptions_table_names_the_method(self):
        p = tea.demo("methanol")
        table = dict(tea.report.assumptions_table(p, p.run()))
        assert "Costing method" in table
        assert "Estimate class" in table


# ============================================================================
# 8. Application layer
# ============================================================================
class TestAppApi:

    def test_meta_has_everything_the_ui_needs(self):
        from teakit.app import api
        m = api.dispatch("meta")
        assert m["ok"]
        for key in ("equipment", "locations", "utilities", "finance_presets",
                    "materials", "metrics", "loh_services"):
            assert m[key], key

    def test_run_returns_result_and_charts(self):
        from teakit.app import api
        proj = api.dispatch("demo", {"kind": "methanol"})["project"]
        r = api.dispatch("run", {"project": proj, "compare_methods": True})
        assert r["ok"] and r["result"]["unit_cost"] > 0
        assert r["charts"] and r["comparison"]["dcf"]

    def test_errors_come_back_as_data_not_exceptions(self):
        from teakit.app import api
        bad = api.dispatch("run", {"project": {"equipment": [], "products": {}}})
        assert bad["ok"] is False and bad["error"]

    def test_unknown_endpoint_is_handled(self):
        from teakit.app import api
        assert api.dispatch("does_not_exist")["ok"] is False

    def test_api_responses_are_json_serialisable(self):
        from teakit.app import api
        proj = api.dispatch("demo", {"kind": "electrolysis"})["project"]
        for name, payload in (("meta", {}), ("run", {"project": proj}),
                              ("parameters", {"project": proj}),
                              ("sensitivity", {"project": proj, "kind": "tornado"})):
            json.dumps(api.dispatch(name, payload), default=str)

    def test_static_assets_are_packaged(self):
        """Artwork included: teakit.ico is also the .exe icon, and a missing
        one only shows up in a built application."""
        import os
        from teakit.app import server
        for f in ("index.html", "app.css", "app.js",
                  "teakit-icon.svg", "favicon.ico", "teakit.ico"):
            assert os.path.isfile(os.path.join(server.STATIC_DIR, f)), f


# ============================================================================
# helpers
# ============================================================================
def _small_project() -> Project:
    p = Project(name="test", dollar_year=2025, method="dcf")
    p.equipment = [
        EquipmentItem("E-101", kind="hx_shell_tube", size=5000),
        EquipmentItem("P-101", kind="pump", size=900, quantity=2, spare=1),
    ]
    p.opex.raw_materials = [opex.Stream("feed", 5.0, "tonne", 300.0)]
    p.opex.utilities = [opex.Stream("electricity", 2000, "kWh", 0.081,
                                    category="utility")]
    p.opex.labor = opex.LaborModel(operators_per_shift=3)
    p.products.products = [products.Product("widget", 35_000, "tonne")]
    return p
