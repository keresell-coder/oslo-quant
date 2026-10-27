import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from oslo_quant.financial_contracts import filing_coverage
from oslo_quant.pipeline import _convert_prices, _resolve_currency
from oslo_quant import healthcheck, report
from tests.test_healthcheck import _write_results
from oslo_quant.config import COMPANIES, ALL_FRAMEWORKS


def test_known_release_beats_fresh_download(tmp_path):
    _write_results(tmp_path, ["fresh"] * len(COMPANIES))
    for fw in ALL_FRAMEWORKS:
        path = tmp_path / "NOD.OL" / (fw + ".json")
        row = json.loads(path.read_text())
        row["source_metadata"]["groups"]["quarterly"]["statement_period_ends"] = {"income_stmt": ["2026-06-30"], "balance_sheet": ["2026-06-30"]}
        path.write_text(json.dumps(row))
    health = healthcheck.build_health(results_dir=tmp_path)
    nod = next(r for r in health["companies"] if r["ticker"] == "NOD.OL")
    assert nod["status"] == "blocked"
    assert nod["filing_coverage"]["issuer_release"]["published_on"] == "2026-10-22"
    assert "filing coverage: behind-known-release" in nod["withheld_reasons"]
    data = {"publication_health": nod, "dupont": {"periods": {"2025": {"roe_3factor": 987654}}}}
    assert "987654" not in report._summary_row("NOD.OL", data)
    assert "987654" not in report._detail_card("NOD.OL", data)


@pytest.mark.parametrize("detected,status", [(None, "gated-unverified-currency"), ("EUR", "gated-unverified-currency"), ("USD", "screening-currency-consistent")])
def test_currency_is_not_verified_by_config_fallback(detected, status):
    fetcher = SimpleNamespace(fetch_currency_info=lambda *a, **k: {"financial_currency": detected, "price_currency": "NOK"})
    result = _resolve_currency(fetcher, "TEST", SimpleNamespace(reporting_currency="USD", full_name="Test", price_currency="NOK", exchange="Euronext Oslo"), True)
    assert result["status"] == status


@pytest.mark.parametrize("rate", [None, 0, -1, float("nan")])
def test_missing_fx_never_leaves_nok_prices_labelled_usd(rate):
    frame = pd.DataFrame({"Close": [100]})
    result = _convert_prices({"prices": frame}, "NOK", "USD", SimpleNamespace(fetch_fx_rate=lambda *a: rate), {})
    assert result["prices"].empty
    assert frame.iloc[0, 0] == 100


def test_valid_conversion_and_same_currency():
    frame = pd.DataFrame({"Close": [100]})
    fetcher = SimpleNamespace(fetch_fx_rate=lambda *a: .1)
    assert _convert_prices({"prices": frame}, "NOK", "USD", fetcher, {})["prices"].iloc[0, 0] == 10
    assert _convert_prices({"prices": frame}, "NOK", "NOK", fetcher, {})["prices"].iloc[0, 0] == 100


def test_currency_agreement_does_not_claim_primary_verification():
    table = report._currency_table({"MOWI.OL": {"currency": {
        "verification_status": "verified", "financial_currency": "EUR"}}})
    assert "Provider/config agree" in table
    assert "✓ Verified" not in table
    assert "do not verify primary statements" in table
