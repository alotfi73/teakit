"""
Currency conversion — the reporting layer on top of the USD engine.

The property that matters is that conversion is *uniform*: every monetary field
scales by exactly the rate, and nothing dimensionless moves at all. A partial
conversion is the dangerous failure, because the report still looks plausible.

Nothing here touches the network. The live feed is exercised only through a
stubbed transport, so the suite runs on a disconnected machine.
"""

from __future__ import annotations

import json
import math

import pytest

from teakit import currency
from teakit.app import api
from teakit.project import Project


# ============================================================================
# The rate table
# ============================================================================
def test_every_labelled_currency_has_a_fallback_rate():
    """A currency the interface offers must be convertible offline."""
    missing = set(currency.CURRENCIES) - set(currency.DEFAULT_RATES)
    assert not missing, f"no offline rate for {missing}"


def test_usd_is_the_identity():
    assert currency.DEFAULT_RATES["USD"] == 1.0


def test_rates_are_positive_and_finite():
    for code, rate in currency.DEFAULT_RATES.items():
        assert rate > 0 and math.isfinite(rate), f"{code} = {rate}"


def test_quote_rejects_a_nonsense_rate():
    with pytest.raises(ValueError):
        currency.RateQuote("EUR", 0.0)
    with pytest.raises(ValueError):
        currency.RateQuote("EUR", -1.0)


def test_quote_reports_its_own_age():
    q = currency.RateQuote("EUR", 0.9, "test", "2020-01-01")
    assert q.stale_days > 1000
    assert currency.RateQuote("EUR", 0.9, "test", "not-a-date").stale_days is None


def test_symbol_falls_back_to_the_code():
    assert currency.symbol("USD") == "$"
    assert currency.symbol("ZZZ") == "ZZZ"


def test_table_round_trips_through_json():
    t = currency.RateTable(rates={"USD": 1.0, "EUR": 0.9},
                           source="test", as_of="2026-01-01", live=True)
    back = currency.RateTable.from_dict(json.loads(json.dumps(t.to_dict())))
    assert back.rates["EUR"] == 0.9
    assert back.source == "test" and back.live is True


# ============================================================================
# The live feed, without a network
# ============================================================================
def test_fetch_returns_none_when_the_feed_is_unreachable(monkeypatch):
    """No network must degrade, never raise — a cost tool has to run offline."""
    def boom(*a, **k):
        raise OSError("no route to host")
    monkeypatch.setattr(currency, "urlopen", boom)
    assert currency.fetch_rates(["EUR"]) is None


def test_fetch_survives_a_malformed_payload(monkeypatch):
    class FakeResponse:
        def read(self):
            return b'{"unexpected": true}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(currency, "urlopen", lambda *a, **k: FakeResponse())
    assert currency.fetch_rates(["EUR"]) is None


def test_fetch_parses_a_good_payload(monkeypatch):
    class FakeResponse:
        def read(self):
            return json.dumps({"base": "USD", "date": "2026-01-02",
                               "rates": {"EUR": 0.9, "GBP": 0.8}}).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(currency, "urlopen", lambda *a, **k: FakeResponse())
    table = currency.fetch_rates(["EUR", "GBP"])
    assert table is not None
    assert table.live is True
    assert table.as_of == "2026-01-02"
    assert table.rates["EUR"] == 0.9
    assert table.rates["USD"] == 1.0


def test_cache_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAKIT_CACHE_DIR", str(tmp_path))
    table = currency.RateTable(rates={"USD": 1.0, "EUR": 0.77},
                               source="test", as_of="2026-01-01")
    assert currency.save_rates(table) is True
    assert currency.load_rates().rates["EUR"] == 0.77


def test_cached_rates_never_fails_without_a_network(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAKIT_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(currency, "fetch_rates", lambda *a, **k: None)
    table = currency.cached_rates()
    assert table.rates["USD"] == 1.0
    assert set(currency.CURRENCIES) <= set(table.rates)


# ============================================================================
# Conversion of a result
# ============================================================================
def _demo_project() -> Project:
    import teakit
    return teakit.demo("methanol")


RATE = 0.75


def test_conversion_scales_every_monetary_field_by_exactly_the_rate():
    p = _demo_project()
    usd = p.run()
    p.currency, p.exchange_rate = "GBP", RATE
    conv = p.run()

    pairs = [
        (usd.purchased_equipment_cost, conv.purchased_equipment_cost),
        (usd.bec, conv.bec),
        (usd.installed_direct, conv.installed_direct),
        (usd.capital.bec, conv.capital.bec),
        (usd.capital.epc_fee, conv.capital.epc_fee),
        (usd.capital.epcc, conv.capital.epcc),
        (usd.capital.tpc, conv.capital.tpc),
        (usd.capital.toc, conv.capital.toc),
        (usd.capital.tasc, conv.capital.tasc),
        (usd.capital.total_owners_cost, conv.capital.total_owners_cost),
        (usd.opex.total, conv.opex.total),
        (usd.opex.fixed_total, conv.opex.fixed_total),
        (usd.opex.variable_total, conv.opex.variable_total),
        (usd.allocation.total_cost, conv.allocation.total_cost),
        (usd.allocation.cost_to_primary, conv.allocation.cost_to_primary),
        (usd.allocation.unit_cost_primary, conv.allocation.unit_cost_primary),
        (usd.unit_cost, conv.unit_cost),
        (usd.capital_component, conv.capital_component),
        (usd.fixed_component, conv.fixed_component),
        (usd.variable_component, conv.variable_component),
    ]
    for before, after in pairs:
        assert after == pytest.approx(before * RATE, rel=1e-12)


def test_conversion_reaches_the_equipment_rows():
    """The reported bug: switching currency left equipment costs in USD."""
    p = _demo_project()
    usd = p.run()
    p.currency, p.exchange_rate = "GBP", RATE
    conv = p.run()
    assert conv.equipment_rows, "demo should have equipment"
    for before, after in zip(usd.equipment_rows, conv.equipment_rows,
                            strict=True):
        assert after["cost"] == pytest.approx(before["cost"] * RATE, rel=1e-12)
        assert after["unit_cost"] == pytest.approx(before["unit_cost"] * RATE,
                                                   rel=1e-12)


def test_conversion_reaches_every_opex_line_and_the_cash_flow():
    p = _demo_project()
    usd = p.run()
    p.currency, p.exchange_rate = "GBP", RATE
    conv = p.run()
    for k, v in usd.opex.variable_items.items():
        assert conv.opex.variable_items[k] == pytest.approx(v * RATE, rel=1e-12)
    for k, v in usd.opex.fixed_items.items():
        assert conv.opex.fixed_items[k] == pytest.approx(v * RATE, rel=1e-12)
    for k, v in usd.capital.owners_costs.items():
        assert conv.capital.owners_costs[k] == pytest.approx(v * RATE, rel=1e-12)
    assert usd.cash_flow is not None
    assert conv.cash_flow.npv == pytest.approx(usd.cash_flow.npv * RATE, rel=1e-12)
    for before, after in zip(usd.cash_flow.net_cash_flow,
                             conv.cash_flow.net_cash_flow, strict=True):
        assert after == pytest.approx(before * RATE, rel=1e-12)


def test_dimensionless_quantities_do_not_move():
    """Ratios, physical output and rates are currency-independent."""
    p = _demo_project()
    usd = p.run()
    p.currency, p.exchange_rate = "GBP", RATE
    conv = p.run()
    assert conv.capital.tasc_toc_factor == usd.capital.tasc_toc_factor
    assert conv.opex.capacity_factor == usd.opex.capacity_factor
    assert conv.opex.operating_hours == usd.opex.operating_hours
    assert conv.annual_production == usd.annual_production
    assert conv.cash_flow.irr == usd.cash_flow.irr
    assert conv.cash_flow.discount_rate == usd.cash_flow.discount_rate
    assert conv.cash_flow.years == usd.cash_flow.years
    assert conv.charge_rate == usd.charge_rate
    if usd.opex.labor:
        assert conv.opex.labor.headcount == usd.opex.labor.headcount


def test_running_twice_does_not_compound_the_rate():
    """run() must convert exactly once, however many times it is called."""
    p = _demo_project()
    p.currency, p.exchange_rate = "GBP", RATE
    first, second = p.run(), p.run()
    assert first.capital.toc == pytest.approx(second.capital.toc, rel=1e-12)


def test_a_bad_rate_is_refused():
    p = _demo_project()
    p.currency, p.exchange_rate = "GBP", 0.0
    with pytest.raises(ValueError):
        p.run()


def test_usd_projects_are_untouched():
    p = _demo_project()
    p.currency, p.exchange_rate = "USD", 1.0
    r = p.run()
    assert r.currency == "USD" and r.exchange_rate == 1.0


def test_the_rate_survives_a_project_round_trip():
    p = _demo_project()
    p.currency = "EUR"
    p.exchange_rate = 0.877
    p.exchange_rate_source = "ECB, test"
    back = Project.from_json(p.to_json())
    assert back.exchange_rate == 0.877
    assert back.exchange_rate_source == "ECB, test"
    assert back.run().unit_cost == pytest.approx(p.run().unit_cost, rel=1e-12)


def test_a_stale_rate_raises_a_warning():
    p = _demo_project()
    p.currency, p.exchange_rate = "EUR", 0.9
    p.exchange_rate_source = "offline table"
    r = p.run()
    # The bundled table is dated; either it is fresh (no warning) or it is old
    # and the user must be told. Both are correct — silence about an old rate
    # is not.
    quote = currency.RateQuote("EUR", 0.9, "offline table")
    if quote.stale_days and quote.stale_days > 30:
        assert any("exchange rate" in w for w in r.warnings)


def test_the_rate_appears_in_the_reported_basis():
    from teakit import report
    p = _demo_project()
    p.currency, p.exchange_rate = "EUR", 0.877
    p.exchange_rate_source = "ECB, test"
    rows = dict(report.assumptions_table(p, p.run()))
    assert "Exchange rate" in rows
    assert "0.877" in rows["Exchange rate"]


# ============================================================================
# The endpoint the interface calls
# ============================================================================
def test_endpoint_offline_mode_needs_no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("live=False must not touch the network")
    monkeypatch.setattr(currency, "urlopen", boom)
    r = api.dispatch("exchange_rates", {"live": False})
    assert r["ok"] is True
    assert r["rates"]["USD"] == 1.0
    assert set(currency.CURRENCIES) <= set(r["rates"])


def test_endpoint_degrades_when_the_feed_is_down(monkeypatch, tmp_path):
    monkeypatch.setenv("TEAKIT_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(currency, "fetch_rates", lambda *a, **k: None)
    r = api.dispatch("exchange_rates", {"live": True})
    assert r["ok"] is True, "a dead feed must not break the interface"
    assert r["note"], "the user has to be told the rates are not live"
    assert r["rates"]["EUR"] > 0


def test_endpoint_rejects_an_unknown_currency():
    r = api.dispatch("exchange_rates", {"currency": "XYZ", "live": False})
    assert r["ok"] is False


def test_endpoint_returns_a_single_quote_when_asked():
    r = api.dispatch("exchange_rates", {"currency": "eur", "live": False})
    assert r["ok"] is True
    assert r["currency"] == "EUR"
    assert r["rate"] == currency.DEFAULT_RATES["EUR"]


def test_meta_ships_rates_so_the_interface_starts_offline():
    m = api.meta()
    assert m["exchange_rates"]["USD"] == 1.0
    assert m["exchange_rates_as_of"]
    assert set(m["currencies"]) == set(m["exchange_rates"])


def test_run_endpoint_converts_and_reports_the_rate():
    project = api.demo({"kind": "methanol"})["project"]
    usd = api.run({"project": project})["result"]
    project = dict(project, currency="GBP", exchange_rate=RATE,
                   exchange_rate_source="test")
    gbp = api.run({"project": project})["result"]
    assert gbp["currency"] == "GBP"
    assert gbp["exchange_rate"] == RATE
    assert gbp["capital"]["toc"] == pytest.approx(usd["capital"]["toc"] * RATE,
                                                   rel=1e-12)
    assert gbp["equipment_rows"][0]["cost"] == pytest.approx(
        usd["equipment_rows"][0]["cost"] * RATE, rel=1e-12)
