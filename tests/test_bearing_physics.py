"""
Tests for src/bearing_physics.py.

The main check: our formulas, fed with the bearing geometry, must reproduce
CWRU's published fault-frequency multipliers. If they do, we know both the
formulas and the geometry numbers are right.

Run all tests from the repository folder with:
    python -m unittest discover -s tests -v
"""

import unittest

from src import bearing_physics as bp
from src import config

PUBLISHED = config.CWRU_PUBLISHED_MULTIPLIERS

# CWRU publishes 4 decimal places, so a correct calculation can differ by up
# to 0.00005 from their rounded figure. 0.0001 allows for that and no more.
ROUNDING_TOLERANCE = 1e-4


class TestAgainstCWRUPublishedMultipliers(unittest.TestCase):

    def test_bpfi(self):
        self.assertAlmostEqual(bp.bpfi_multiplier(), PUBLISHED["BPFI"],
                               delta=ROUNDING_TOLERANCE)

    def test_bpfo(self):
        self.assertAlmostEqual(bp.bpfo_multiplier(), PUBLISHED["BPFO"],
                               delta=ROUNDING_TOLERANCE)

    def test_ftf(self):
        self.assertAlmostEqual(bp.ftf_multiplier(), PUBLISHED["FTF"],
                               delta=ROUNDING_TOLERANCE)

    def test_standard_bsf_is_about_2_357(self):
        self.assertAlmostEqual(bp.bsf_multiplier(), 2.357, delta=1e-3)

    def test_cwru_rolling_element_value_is_twice_bsf(self):
        """CWRU's 4.7135 is 2 x BSF, not BSF itself."""
        self.assertAlmostEqual(2 * bp.bsf_multiplier(),
                               PUBLISHED["rolling_element"],
                               delta=ROUNDING_TOLERANCE)

    def test_cwru_rolling_element_value_is_not_bsf(self):
        """Guard against someone 'fixing' BSF to match 4.7135."""
        self.assertGreater(abs(bp.bsf_multiplier() - PUBLISHED["rolling_element"]), 2)


class TestPhysicalRelationships(unittest.TestCase):
    """Facts that follow from the formulas, independent of CWRU's numbers."""

    def test_bpfo_plus_bpfi_equals_number_of_balls(self):
        # (n/2)(1 - r) + (n/2)(1 + r) = n
        self.assertAlmostEqual(bp.bpfo_multiplier() + bp.bpfi_multiplier(),
                               config.N_BALLS, places=10)

    def test_bpfo_is_number_of_balls_times_cage_speed(self):
        self.assertAlmostEqual(bp.bpfo_multiplier(),
                               config.N_BALLS * bp.ftf_multiplier(), places=10)

    def test_inner_race_frequency_is_higher_than_outer(self):
        self.assertGreater(bp.bpfi_multiplier(), bp.bpfo_multiplier())

    def test_zero_size_balls_give_simple_limits(self):
        # With infinitely small balls the cage turns at half shaft speed.
        self.assertAlmostEqual(bp.ftf_multiplier(ball_d=1e-12), 0.5, places=9)


class TestHandCalculationAt1797Rpm(unittest.TestCase):
    """The same numbers as the hand calculation in docs/VALIDATION.md."""

    def setUp(self):
        self.f = bp.fault_frequencies_hz(1797)

    def test_shaft_frequency(self):
        self.assertAlmostEqual(self.f["shaft_1x"], 29.95, places=10)

    def test_values_in_hz(self):
        expected = {"FTF": 11.929, "BPFO": 107.364, "BPFI": 162.186,
                    "BSF": 70.585, "2xBSF": 141.169}
        for name, hz in expected.items():
            with self.subTest(name=name):
                self.assertAlmostEqual(self.f[name], hz, delta=0.001)


if __name__ == "__main__":
    unittest.main()
