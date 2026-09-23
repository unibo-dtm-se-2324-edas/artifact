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

START = "2025-01-01 00:00:00"
END = "2025-01-01 23:00:00"


def _make_fake_read_sql(db: sqlite3.Connection):
    """
    Stand-in for pd.read_sql that runs the query text against an in-memory
    SQLite database instead of PostgreSQL. Only the Postgres-specific
    constructs used by queries.py are translated:
      - = ANY(%(countries)s) -> IN (:country_0, :country_1, ...)
      - date_trunc('day', x) -> date(x)
    (Same approach as tests/test_known_bugs.py.)
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


class QueriesTestBase(unittest.TestCase):
    """Creates an empty in-memory schema and runs query functions against it."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE energy_consumption (
                country_code TEXT, time_stamp TEXT, consumption_mw REAL);
            CREATE TABLE energy_production (
                country_code TEXT, time_stamp TEXT, source_type TEXT, production_mw REAL);
            CREATE TABLE cross_border_flow (
                from_country_code TEXT, to_country_code TEXT, time_stamp TEXT, flow_mw REAL);
        """)

    def add_consumption(self, rows):
        self.db.executemany("INSERT INTO energy_consumption VALUES (?, ?, ?)", rows)

    def add_production(self, rows):
        self.db.executemany("INSERT INTO energy_production VALUES (?, ?, ?, ?)", rows)

    def add_flows(self, rows):
        self.db.executemany("INSERT INTO cross_border_flow VALUES (?, ?, ?, ?)", rows)

    def run_query(self, func, countries=("FR",)):
        engine_factory = lambda: MagicMock()
        with patch.object(queries.pd, "read_sql", _make_fake_read_sql(self.db)):
            return func(engine_factory, list(countries), START, END)


class TestQueriesCoverage(QueriesTestBase):

    def test_consumption_vs_production_merges_on_timestamp(self):
        self.add_consumption([
            ("FR", "2025-01-01 10:00:00", 100.0),
            ("FR", "2025-01-01 11:00:00", 200.0),
        ])
        self.add_production([
            ("FR", "2025-01-01 10:00:00", "Solar", 10.0),
            ("FR", "2025-01-01 10:00:00", "Wind", 20.0),
            ("FR", "2025-01-01 11:00:00", "Solar", 40.0),
        ])

        df = self.run_query(queries.consumption_vs_production)

        self.assertEqual(len(df), 2)
        self.assertIn("consumption_mw", df.columns)
        self.assertIn("production_mw", df.columns)
        rows = df.set_index("time_stamp")
        self.assertEqual(rows.loc["2025-01-01 10:00:00", "consumption_mw"], 100.0)
        self.assertEqual(rows.loc["2025-01-01 10:00:00", "production_mw"], 30.0)
        self.assertEqual(rows.loc["2025-01-01 11:00:00", "consumption_mw"], 200.0)
        self.assertEqual(rows.loc["2025-01-01 11:00:00", "production_mw"], 40.0)

    def test_kpis_totals_and_net_balance(self):
        self.add_consumption([
            ("FR", "2025-01-01 10:00:00", 100.0),
            ("FR", "2025-01-01 11:00:00", 200.0),
        ])
        self.add_production([
            ("FR", "2025-01-01 10:00:00", "Solar", 10.0),
            ("FR", "2025-01-01 10:00:00", "Wind", 20.0),
            ("FR", "2025-01-01 11:00:00", "Solar", 30.0),
        ])
        self.add_flows([
            ("FR", "DE", "2025-01-01 10:00:00", 5.0),
            ("FR", "DE", "2025-01-01 11:00:00", 7.0),
            # Flow originating outside the selected country must be excluded.
            ("DE", "FR", "2025-01-01 10:00:00", 1000.0),
        ])

        result = self.run_query(queries.kpis)

        self.assertEqual(result["total_consumption"], 300.0)
        self.assertEqual(result["total_production"], 60.0)
        self.assertEqual(result["net_balance"], 12.0)
        # Both hours fall on the same day, so the daily average is the total.
        self.assertEqual(result["avg_daily_consumption"], 300.0)
        # Energy mix: Solar 40 of 60, Wind 20 of 60.
        mix = result["energy_mix"].set_index("source_type")
        self.assertEqual(mix.loc["Solar", "production_mw"], 40.0)
        self.assertEqual(mix.loc["Wind", "production_mw"], 20.0)
        self.assertAlmostEqual(mix.loc["Solar", "percent"], 40.0 / 60.0 * 100.0)
        self.assertAlmostEqual(mix.loc["Wind", "percent"], 20.0 / 60.0 * 100.0)

    def test_production_mix_one_row_per_timestamp_and_source(self):
        self.add_production([
            ("FR", "2025-01-01 10:00:00", "Solar", 10.0),
            ("FR", "2025-01-01 10:00:00", "Wind", 20.0),
            # Same (country, time, source) is not possible in the real table,
            # so a second country is used to prove rows are summed per source.
            ("DE", "2025-01-01 10:00:00", "Solar", 5.0),
            ("FR", "2025-01-01 11:00:00", "Solar", 30.0),
        ])

        df = self.run_query(queries.production_mix, countries=("FR", "DE"))

        self.assertEqual(len(df), 3)
        got = {
            (r.time_stamp, r.source_type): r.production_mw
            for r in df.itertuples(index=False)
        }
        self.assertEqual(got, {
            ("2025-01-01 10:00:00", "Solar"): 15.0,
            ("2025-01-01 10:00:00", "Wind"): 20.0,
            ("2025-01-01 11:00:00", "Solar"): 30.0,
        })

    def test_crossborder_flows_group_and_sum_by_pair_and_timestamp(self):
        self.add_flows([
            ("FR", "DE", "2025-01-01 10:00:00", 5.0),
            ("FR", "DE", "2025-01-01 10:00:00", 3.0),
            ("FR", "BE", "2025-01-01 10:00:00", 4.0),
            ("FR", "DE", "2025-01-01 11:00:00", 2.0),
        ])

        df = self.run_query(queries.crossborder_flows)

        self.assertEqual(len(df), 3)
        got = {
            (r.from_country_code, r.to_country_code, r.time_stamp): r.flow_mw
            for r in df.itertuples(index=False)
        }
        self.assertEqual(got, {
            ("FR", "DE", "2025-01-01 10:00:00"): 8.0,
            ("FR", "BE", "2025-01-01 10:00:00"): 4.0,
            ("FR", "DE", "2025-01-01 11:00:00"): 2.0,
        })

    def test_hourly_consumption_derives_hour_and_day(self):
        # 2025-01-01 is a Wednesday, 2025-01-02 a Thursday.
        self.add_consumption([
            ("FR", "2025-01-01 10:00:00", 100.0),
            ("FR", "2025-01-01 11:00:00", 200.0),
            ("FR", "2025-01-02 09:00:00", 300.0),
        ])
        with patch.object(queries.pd, "read_sql", _make_fake_read_sql(self.db)):
            df = queries.hourly_consumption(
                lambda: MagicMock(), ["FR"], START, "2025-01-02 23:00:00"
            )

        self.assertEqual(list(df["hour"]), [10, 11, 9])
        self.assertEqual(list(df["day"]), ["Wednesday", "Wednesday", "Thursday"])
        self.assertEqual(list(df["consumption_mw"]), [100.0, 200.0, 300.0])

    def test_hourly_consumption_handles_empty_result(self):
        # No consumption rows at all: must return an empty frame that still
        # has the derived columns instead of raising.
        df = self.run_query(queries.hourly_consumption)

        self.assertTrue(df.empty)
        for col in ("time_stamp", "consumption_mw", "hour", "day"):
            self.assertIn(col, df.columns)

    def test_flow_table_returns_unaggregated_rows(self):
        self.add_flows([
            ("FR", "DE", "2025-01-01 10:00:00", 5.0),
            ("FR", "DE", "2025-01-01 10:00:00", 3.0),
            ("FR", "BE", "2025-01-01 11:00:00", 4.0),
        ])

        df = self.run_query(queries.flow_table)

        self.assertEqual(
            list(df.columns),
            ["from_country_code", "to_country_code", "time_stamp", "flow_mw"],
        )
        # Duplicated (from, to, time) rows are kept as-is, not summed.
        self.assertEqual(len(df), 3)
        self.assertEqual(sorted(df["flow_mw"]), [3.0, 4.0, 5.0])


if __name__ == "__main__":
    unittest.main()
