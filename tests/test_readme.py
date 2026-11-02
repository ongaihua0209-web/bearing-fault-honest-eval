"""
Tests that README.md quotes the results correctly.

The README is the public face of the project, so its numbers must match
results/results_all.csv. If the experiment is re-run and the numbers
change, these tests fail until the README is updated.
"""

import re
import unittest

import pandas as pd

from src import config

README = config.REPO_ROOT / "README.md"
RESULTS = config.RESULTS_DIR / "results_all.csv"
MODELS = ("logistic_regression", "random_forest", "gradient_boosting")   # README column order

# README protocol-C table row label -> (feature set, window length)
ROWS = {"F1: 7 generic statistics": ("F1", 2048),
        "F2: 16 spectral band energies": ("F2", 2048),
        "F3: physics-informed envelope features": ("F3", 8192),
        "**F1 + F3**": ("F1+F3", 8192)}


def readme_row_numbers(text, row_start):
    """The numbers in the README table row that starts with row_start."""
    line = next(l for l in text.splitlines() if l.startswith("| " + row_start))
    return [float(x) for x in re.findall(r"\d\.\d\d", line)]


class TestReadmeMatchesResults(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not RESULTS.exists():
            raise unittest.SkipTest("run python -m src.run_experiments first")
        cls.text = README.read_text()
        cls.results = pd.read_csv(RESULTS).set_index(
            ["feature_set", "window_length", "protocol", "model"])["macro_f1_mean"]

    def value(self, feature_set, length, protocol, model):
        return round(self.results.loc[(feature_set, length, protocol, model)], 2)

    def test_protocol_c_table(self):
        for row_start, (feature_set, length) in ROWS.items():
            with self.subTest(row=row_start):
                expected = [self.value(feature_set, length, "C", m) for m in MODELS]
                self.assertEqual(readme_row_numbers(self.text, row_start), expected)

    def test_protocol_table_best_f1_scores(self):
        for protocol, row_start in (("A", "**A**"), ("B", "**B**"), ("C", "**C**")):
            with self.subTest(protocol=protocol):
                best = max(self.value("F1", 2048, protocol, m) for m in MODELS)
                self.assertEqual(readme_row_numbers(self.text, row_start)[-1], best)


if __name__ == "__main__":
    unittest.main()
