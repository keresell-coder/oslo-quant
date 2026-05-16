"""CLI smoke tests (no network calls)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from oslo_quant.cli import main


def _mock_pipeline_run(**kwargs):
    return {
        "TEL.OL": {
            "dupont": {"ticker": "TEL.OL", "framework": "dupont", "periods": {"2023": {}}},
        }
    }


def test_cli_help(capsys):
    try:
        main(["--help"])
    except SystemExit as e:
        assert e.code == 0
    captured = capsys.readouterr()
    assert "oslo-quant" in captured.out


def test_cli_runs_without_network():
    with patch("oslo_quant.pipeline.run", side_effect=_mock_pipeline_run):
        rc = main(["--tickers", "TEL.OL", "--frameworks", "dupont", "--output", "none"])
    assert rc == 0


def test_cli_summary_output(capsys):
    with patch("oslo_quant.pipeline.run", side_effect=_mock_pipeline_run):
        rc = main(["--tickers", "TEL.OL", "--frameworks", "dupont"])
    captured = capsys.readouterr()
    assert "TEL.OL" in captured.out
