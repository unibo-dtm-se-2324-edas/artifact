import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

from edas.ingestion import upsert


class TestUpsertColumnOrder(unittest.TestCase):
    # BUG 5 (upsert.py): upsert_energy_consumption trusts DataFrame column
    # order instead of explicitly selecting columns to match the INSERT
    # list, so a differently-ordered DataFrame silently corrupts data.
    def test_upsert_energy_consumption_ignores_dataframe_column_order(self):
        # Columns deliberately NOT in (country_code, time_stamp,
        # consumption_mw) order.
        df = pd.DataFrame([
            {"consumption_mw": 42.0, "country_code": "FR", "time_stamp": "2025-01-01 10:00:00"},
        ])

        captured = {}

        def fake_execute_values(cur, sql, records, page_size=None):
            captured["records"] = records

        mock_conn = MagicMock()
        with patch.object(upsert.pg_extras, "execute_values", side_effect=fake_execute_values):
            upsert.upsert_energy_consumption(mock_conn, df)

        # Regardless of the DataFrame's column order, the row sent to the
        # DB must be (country_code, time_stamp, consumption_mw) to match
        # the INSERT statement's column list.
        self.assertEqual(
            captured["records"],
            [("FR", "2025-01-01 10:00:00", 42.0)],
        )

    # BUG 5b (upsert.py): same column-order bug in upsert_energy_production.
    def test_upsert_energy_production_ignores_dataframe_column_order(self):
        df = pd.DataFrame([
            {"production_mw": 7.5, "source_type": "Wind", "country_code": "FR", "time_stamp": "2025-01-01 10:00:00"},
        ])
        captured = {}
        def fake_execute_values(cur, sql, records, page_size=None):
            captured["records"] = records
        mock_conn = MagicMock()
        with patch.object(upsert.pg_extras, "execute_values", side_effect=fake_execute_values):
            upsert.upsert_energy_production(mock_conn, df)
        self.assertEqual(
            captured["records"],
            [("FR", "2025-01-01 10:00:00", "Wind", 7.5)],
        )

    # BUG 5c (upsert.py): same column-order bug in upsert_cross_border_flow.
    def test_upsert_cross_border_flow_ignores_dataframe_column_order(self):
        df = pd.DataFrame([
            {"flow_mw": 12.0, "to_country_code": "DE", "from_country_code": "FR", "time_stamp": "2025-01-01 10:00:00"},
        ])
        captured = {}
        def fake_execute_values(cur, sql, records, page_size=None):
            captured["records"] = records
        mock_conn = MagicMock()
        with patch.object(upsert.pg_extras, "execute_values", side_effect=fake_execute_values):
            upsert.upsert_cross_border_flow(mock_conn, df)
        self.assertEqual(
            captured["records"],
            [("FR", "DE", "2025-01-01 10:00:00", 12.0)],
        )


if __name__ == "__main__":
    unittest.main()
