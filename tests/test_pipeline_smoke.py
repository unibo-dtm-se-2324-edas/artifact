import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

def _df(n=3):
    """Creates a simple DataFrame for mock return values."""
    return pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=n, freq="h"),
        "value": range(n),
    })


class TestPipelineSmoke(unittest.TestCase):
    """
    A smoke test for the main 'run_pipeline' orchestrator.

    This test isolates the pipeline.py module by mocking (patching) all
    its external dependencies (adapters and repository logic).
    The goal is to test the 'happy path' execution flow, not the
    logic of the dependencies themselves.
    """

    # --- Setup Mocks (Patching) ---
    # Mocks are stacked. The bottom decorator is executed first
    # and passed as the *last* argument to the test method.
    @patch("edas.pipeline.upsert_energy_production")
    @patch("edas.pipeline.upsert_energy_consumption")
    @patch("edas.pipeline.fetch_production")
    @patch("edas.pipeline.fetch_consumption")
    @patch("edas.pipeline._load_countries")
    @patch("edas.pipeline.get_engine") # This is the first mock (executed last)
    def test_run_pipeline_minimal(
        self,
        mock_get_engine,
        mock_load_countries,
        mock_fetch_consumption,
        mock_fetch_production,
        mock_upsert_cons,
        mock_upsert_prod,
    ):
        """
        Tests the 'run_pipeline' function in a minimal configuration
        (FR only, no flows) to ensure all components are called correctly.
        """

        # --- Arrange (Define Mock Behavior) ---

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
        mock_fetch_production.return_value  = _df(5)

        mock_upsert_cons.side_effect = lambda _raw, df: len(df)
        mock_upsert_prod.side_effect = lambda _raw, df: len(df)

        # --- Act ---
        from edas.pipeline import run_pipeline

        run_pipeline(countries=["FR"], include_flows=False, mode="last_10_days")

        # --- Assert ---
        mock_fetch_consumption.assert_called_once()
        mock_fetch_production.assert_called_once()
        mock_upsert_cons.assert_called_once()
        mock_upsert_prod.assert_called_once()