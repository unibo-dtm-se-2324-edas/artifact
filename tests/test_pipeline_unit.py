import sys, os
# --- Dynamic Path Configuration ---
# This adds the 'src' directory (one level up from 'tests') to the Python path.
# This is necessary so the test runner can find and import the 'edas' package.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
import pandas as pd

from edas.pipeline import _compute_range

class TestComputeRange(unittest.TestCase):
    """
    Test case for the _compute_range helper function in pipeline.py.
    These are unit tests, focusing on a single, isolated piece of logic.
    """

    def test_last_10_days_dynamic_now(self):
        """
        Tests the 'last_10_days' mode.
        This test is dynamic; it calculates the expected start/end based on the
        current time, just as the main function does, to ensure they match.
        """
        # --- Arrange ---
        # Re-calculate the expected timestamps based on the current execution time.
        now_bxl = pd.Timestamp.utcnow().tz_convert("Europe/Brussels")
        expected_end = now_bxl.floor("h") - pd.Timedelta(hours=1)
        expected_start = expected_end - pd.Timedelta(days=10)

        # --- Act ---
        start, end = _compute_range("last_10_days")

        # --- Assert ---
        self.assertEqual(start, expected_start)
        self.assertEqual(end, expected_end)

    def test_full_2025_range(self):
        """
        Tests the 'full_2025' mode.
        This test is static and deterministic, checking against hardcoded values.
        """
        # --- Arrange ---
        # Define the expected (hardcoded) start and end timestamps for this mode
        expected_start_str = "2025-01-01 00:00:00+01:00"
        expected_end_str = "2025-12-31 23:00:00+01:00"

        # --- Act ---
        start, end = _compute_range("full_2025")

        # --- Assert ---
        self.assertEqual(str(start), expected_start_str)
        self.assertEqual(str(end),   expected_end_str)

    def test_invalid_mode_raises(self):
        """
        Tests that the function correctly raises a ValueError
        when an unsupported mode is provided.
        """
        # --- Act & Assert ---
        with self.assertRaises(ValueError):
            _compute_range("unsupported_mode")


if __name__ == "__main__":
    unittest.main()