import sys, os
# --- Dynamic Path Configuration ---
# Adds the 'src' directory (one level up from 'tests') to the Python path
# so the test runner can find and import the 'edas' package.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

import re
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

from edas.dashboard import queries
from edas.db.connection import get_engine
from edas.ingestion import entsoe_client


def _make_fake_read_sql(db: sqlite3.Connection):
    """
    Builds a stand-in for pd.read_sql that runs the query against an in-memory
    SQLite database instead of PostgreSQL. The SQL text under test is executed
    for real, so join fan-out is reproduced faithfully. Only the two
    Postgres-specific constructs used by queries.py are translated:
      - = ANY(%(countries)s) -> IN (:country_0, :country_1, ...)
      - date_trunc('day', x) -> date(x)
    """
    def fake_read_sql(sql, conn, params=None):
        params = dict(params or {})
        countries = params.pop("countries", [])
        placeholders = ",".join(f":country_{i}" for i in range(len(countries)))
        sql = re.sub(r"=\s*ANY\(%\(countries\)s\)", f"IN ({placeholders})", sql)
        sql = re.sub(r"date_trunc\('day',\s*([\w\.]+)\)", r"date(\1)", sql)
        sql = re.sub(r"%\((\w+)\)s", r":\1", sql)
        for i, c in enumerate(countries):
            params[f"country_{i}"] = c
        return pd.read_sql_query(sql, db, params=params)

    return fake_read_sql


class TestKnownBugs(unittest.TestCase):
    """
    Regression tests for previously fixed bugs.
    """

    # Regression: daily_summary must not fan out consumption rows when a
    # country/hour has multiple energy_production source_type rows —
    # total_consumption has to stay the raw per-hour value, not a multiple of it.
    def test_daily_summary_consumption_not_inflated_by_source_types(self):
        # --- Arrange ---
        # One hour, one country: consumption 100 MW, production from 3 sources.
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript("""
            CREATE TABLE energy_consumption (
                country_code TEXT, time_stamp TEXT, consumption_mw REAL);
            CREATE TABLE energy_production (
                country_code TEXT, time_stamp TEXT, source_type TEXT, production_mw REAL);
            INSERT INTO energy_consumption VALUES ('FR', '2025-01-01 10:00:00', 100.0);
            INSERT INTO energy_production VALUES ('FR', '2025-01-01 10:00:00', 'Solar', 10.0);
            INSERT INTO energy_production VALUES ('FR', '2025-01-01 10:00:00', 'Wind', 20.0);
            INSERT INTO energy_production VALUES ('FR', '2025-01-01 10:00:00', 'Nuclear', 30.0);
        """)

        fake_engine = MagicMock()
        engine_factory = lambda: fake_engine

        # --- Act ---
        with patch.object(queries.pd, "read_sql", _make_fake_read_sql(db)):
            df = queries.daily_summary(
                engine_factory, ["FR"], "2025-01-01 00:00:00", "2025-01-01 23:00:00"
            )

        # --- Assert ---
        # Correct values: consumption counted once (100), production summed (60).
        self.assertEqual(len(df), 1)
        self.assertEqual(df.loc[0, "total_consumption"], 100.0)
        self.assertEqual(df.loc[0, "total_production"], 60.0)
        self.assertEqual(df.loc[0, "net_balance"], -40.0)

    # Regression: fetch_consumption must return an empty DataFrame on an
    # ENTSO-E API error instead of letting the exception propagate.
    def test_fetch_consumption_returns_empty_df_on_api_error(self):
        # --- Arrange ---
        mock_client = MagicMock()
        mock_client.query_load.side_effect = Exception("API down")

        # --- Act ---
        with patch.object(entsoe_client, "client", mock_client):
            result = entsoe_client.fetch_consumption(
                "FR", "FR",
                pd.Timestamp("2025-01-01", tz="Europe/Brussels"),
                pd.Timestamp("2025-01-02", tz="Europe/Brussels"),
            )

        # --- Assert ---
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)
        self.assertEqual(
            list(result.columns), ["country_code", "time_stamp", "consumption_mw"]
        )

    # Regression: fetch_production must return an empty DataFrame on an
    # ENTSO-E API error instead of letting the exception propagate.
    def test_fetch_production_returns_empty_df_on_api_error(self):
        # --- Arrange ---
        mock_client = MagicMock()
        mock_client.query_generation.side_effect = Exception("API down")

        # --- Act ---
        with patch.object(entsoe_client, "client", mock_client):
            result = entsoe_client.fetch_production(
                "FR", "FR",
                pd.Timestamp("2025-01-01", tz="Europe/Brussels"),
                pd.Timestamp("2025-01-02", tz="Europe/Brussels"),
            )

        # --- Assert ---
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)
        self.assertEqual(
            list(result.columns),
            ["country_code", "time_stamp", "source_type", "production_mw"],
        )

    # Regression: every environment variable get_engine() requires must also
    # be documented in .env.example, so following the example file is
    # actually enough to run the project.
    def test_env_example_defines_all_vars_required_by_get_engine(self):
        # --- Arrange ---
        # Parse variable names (left side of KEY=value) from .env.example.
        env_example = os.path.join(
            os.path.dirname(__file__), "..", ".env.example"
        )
        documented = set()
        with open(env_example, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                documented.add(line.split("=", 1)[0].strip())

        # --- Act ---
        # Discover the required variables behaviourally, so the test survives
        # changes to how get_engine() stores its list: start from an empty
        # environment and supply each variable it reports as missing until it
        # succeeds.
        supplied = {}
        with patch.dict(os.environ, {}, clear=True):
            for _ in range(50):
                os.environ.update(supplied)
                try:
                    get_engine()
                    break
                except EnvironmentError as exc:
                    match = re.search(r":\s*(\w+)\s*$", str(exc))
                    self.assertIsNotNone(
                        match, f"Cannot parse missing variable from: {exc}"
                    )
                    supplied[match.group(1)] = "1"
            else:
                self.fail("get_engine() kept reporting missing variables")
        required = set(supplied)

        # --- Assert ---
        missing = required - documented
        self.assertFalse(
            missing,
            f".env.example does not define variables required by "
            f"get_engine(): {sorted(missing)}",
        )

    # Regression: the Dash dev server's debug mode must default to off and be
    # controllable via EDAS_DEBUG — Werkzeug's debug console allows arbitrary
    # code execution if the app is ever exposed beyond localhost.
    def test_debug_mode_defaults_to_false_and_is_configurable(self):
        from edas.config import debug_enabled

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(debug_enabled())

        with patch.dict(os.environ, {"EDAS_DEBUG": "true"}, clear=True):
            self.assertTrue(debug_enabled())

        with patch.dict(os.environ, {"EDAS_DEBUG": "0"}, clear=True):
            self.assertFalse(debug_enabled())

    # Regression: dashboard_main() must actually pass debug_enabled() to
    # app.run() rather than still hardcoding debug=True.
    def test_dashboard_main_passes_debug_enabled_to_app_run(self):
        from edas import cli as cli_module

        with patch("edas.dashboard.app.app") as mock_app, \
             patch.dict(os.environ, {"EDAS_DEBUG": "true"}, clear=True):
            cli_module.dashboard_main()
            mock_app.run.assert_called_once()
            _, kwargs = mock_app.run.call_args
            self.assertTrue(kwargs.get("debug"))


if __name__ == "__main__":
    unittest.main()
