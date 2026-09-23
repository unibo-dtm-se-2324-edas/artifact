import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd


def _df(n=3):
    """Creates a simple DataFrame for mock return values."""
    return pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=n, freq="h"),
        "value": range(n),
    })


class TestPipelineCustomRange(unittest.TestCase):
    """
    Regression test for --mode custom --start X --end Y support.

    run_pipeline() currently has no start/end parameters, so cli.py's
    ingest_main() call with mode="custom", start=..., end=... always
    raises TypeError, which is silently swallowed by an `except TypeError:`
    fallback that retries without start/end — using _compute_range(mode)
    instead of the explicit dates the caller asked for.
    """

    # Regression: run_pipeline(mode="custom", start=..., end=...) must fetch
    # data for the explicit range, not silently fall back to
    # _compute_range("custom") — which today doesn't support "custom" at all
    # and would raise ValueError("Unknown mode: custom") if it were reached.
    @patch("edas.pipeline.upsert_energy_production")
    @patch("edas.pipeline.upsert_energy_consumption")
    @patch("edas.pipeline.fetch_production")
    @patch("edas.pipeline.fetch_consumption")
    @patch("edas.pipeline._load_countries")
    @patch("edas.pipeline.get_engine")
    def test_run_pipeline_uses_explicit_start_end_when_mode_is_custom(
        self,
        mock_get_engine,
        mock_load_countries,
        mock_fetch_consumption,
        mock_fetch_production,
        mock_upsert_cons,
        mock_upsert_prod,
    ):
        # --- Arrange ---
        class _FakeConn:
            """Fake SQLAlchemy Connection class (Test Double)."""
            def __init__(self):
                self.connection = MagicMock()
                self.connection.driver_connection = object()
            def __enter__(self): return self
            def __exit__(self, *args): return False # Simulate successful transaction

        class _FakeEngine:
            """Fake SQLAlchemy Engine class (Test Double)."""
            def begin(self): return _FakeConn()

        mock_get_engine.return_value = _FakeEngine()

        mock_load_countries.return_value = {
            "FR": {"name": "France", "zone": "10YFR-RTE------C"},
        }

        mock_fetch_consumption.return_value = _df(4)
        mock_fetch_production.return_value = _df(5)

        mock_upsert_cons.side_effect = lambda _raw, df: len(df)
        mock_upsert_prod.side_effect = lambda _raw, df: len(df)

        expected_start = "2024-06-01"
        expected_end = "2024-06-02"

        # --- Act ---
        from edas.pipeline import run_pipeline

        run_pipeline(
            mode="custom",
            start=expected_start,
            end=expected_end,
            countries=["FR"],
            include_flows=False,
        )

        # --- Assert ---
        mock_fetch_consumption.assert_called_once()
        mock_fetch_production.assert_called_once()

        expected_start_ts = pd.Timestamp(expected_start, tz="Europe/Brussels")
        expected_end_ts = pd.Timestamp(expected_end, tz="Europe/Brussels")

        # fetch_consumption(country_code, zone_key, start, end)
        cons_args = mock_fetch_consumption.call_args.args
        prod_args = mock_fetch_production.call_args.args
        self.assertEqual(cons_args[2], expected_start_ts)
        self.assertEqual(cons_args[3], expected_end_ts)
        self.assertEqual(prod_args[2], expected_start_ts)
        self.assertEqual(prod_args[3], expected_end_ts)


if __name__ == "__main__":
    unittest.main()
