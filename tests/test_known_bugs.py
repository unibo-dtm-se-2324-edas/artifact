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
    Regression tests that reproduce known, not-yet-fixed bugs.
    These are EXPECTED TO FAIL against the current production code.
    """

    # BUG 1 (queries.py, daily_summary): the query JOINs energy_consumption to
    # raw energy_production rows. energy_production has one row per
    # (country_code, time_stamp, source_type), so each consumption row is
    # duplicated once per source_type at that hour, inflating total_consumption.
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

    # BUG 2 (entsoe_client.py, fetch_consumption): unlike fetch_flow, there is
    # no try/except around the ENTSO-E API call, so an API error propagates to
    # the caller instead of yielding an empty DataFrame.
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

    # BUG 2b (entsoe_client.py, fetch_production): same missing try/except as
    # fetch_consumption around client.query_generation.
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


if __name__ == "__main__":
    unittest.main()
