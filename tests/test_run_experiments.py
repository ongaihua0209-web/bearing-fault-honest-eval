"""
Tests for src/run_experiments.py. The full experiment is not run here (it
takes a minute or two); these check the parts that keep it honest.
"""

import unittest

import numpy as np
import pandas as pd

from src import run_experiments as rx
from src import splits


def fake_data(n_per_class=40, shift=0.0, seed=0):
    """Four well-separated classes in 7 features, optionally shifted."""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for i, cls in enumerate(splits.CLASSES):
        X.append(rng.normal(loc=i * 5 + shift, scale=0.5, size=(n_per_class, 7)))
        y += [cls] * n_per_class
    return np.vstack(X), np.array(y)


class TestNoFittingOnTestData(unittest.TestCase):

    def test_scaler_learns_from_training_data_only(self):
        X_train, y_train = fake_data(shift=0.0)
        X_test, y_test = fake_data(shift=100.0, seed=1)      # very different
        for name in rx.MODEL_NAMES:
            with self.subTest(model=name):
                pipeline, _ = rx.train_and_test(name, 0, X_train, y_train, X_test, y_test)
                np.testing.assert_allclose(pipeline.named_steps["scaler"].mean_,
                                           X_train.mean(axis=0))

    def test_test_labels_are_never_needed(self):
        # Scrambling the test labels must not change the predictions.
        X_train, y_train = fake_data()
        X_test, y_test = fake_data(seed=2)
        for name in rx.MODEL_NAMES:
            with self.subTest(model=name):
                _, p1 = rx.train_and_test(name, 0, X_train, y_train, X_test, y_test)
                _, p2 = rx.train_and_test(name, 0, X_train, y_train, X_test, y_test[::-1])
                np.testing.assert_array_equal(p1, p2)


class TestModelsAndScores(unittest.TestCase):

    def test_every_model_separates_easy_classes(self):
        X_train, y_train = fake_data()
        X_test, y_test = fake_data(seed=3)
        for name in rx.MODEL_NAMES:
            with self.subTest(model=name):
                _, predicted = rx.train_and_test(name, 0, X_train, y_train, X_test, y_test)
                self.assertEqual(rx.scores(y_test, predicted)["macro_f1"], 1.0)

    def test_scores_for_a_known_case(self):
        y_true = np.array(["normal", "ball", "ball", "outer_race", "inner_race"])
        y_pred = np.array(["normal", "ball", "inner_race", "outer_race", "inner_race"])
        s = rx.scores(y_true, y_pred)
        # recalls: normal 1, inner 1, ball 0.5, outer 1 -> balanced accuracy 0.875
        self.assertAlmostEqual(s["balanced_accuracy"], 0.875)
        self.assertEqual(s["f1_ball"], 2 / 3)


class TestFeaturesForSplit(unittest.TestCase):

    def fake_table(self):
        from src import features
        n, n_bands = 10, len(features.F3_BANDS)
        kurtosis = np.zeros((n, n_bands))
        kurtosis[:6, 1] = 4.0                 # training rows prefer band 1
        kurtosis[6:, 5] = 40.0                # test rows prefer band 5
        f3_by_band = np.stack([np.full((n, 9), float(b)) for b in range(n_bands)])
        return {"F1": np.ones((n, 7)), "F2": np.ones((n, 16)),
                "f3_kurtosis": kurtosis, "f3_by_band": f3_by_band}

    def test_f3_band_comes_from_training_rows_only(self):
        X, names, band = rx.features_for_split("F3", self.fake_table(), np.arange(6))
        self.assertEqual(band, 1)
        self.assertTrue(np.all(X == 1.0))      # the band-1 slice
        self.assertEqual(len(names), 9)

    def test_combined_set_is_f1_then_f3(self):
        X, names, band = rx.features_for_split("F1+F3", self.fake_table(), np.arange(6))
        self.assertEqual(X.shape, (10, 16))
        self.assertEqual(names[:7], ["rms", "peak", "peak_to_peak", "crest_factor",
                                     "kurtosis", "skewness", "std"])

    def test_importances_sum_to_one(self):
        X_train, y_train = fake_data()
        for name in rx.MODEL_NAMES:
            with self.subTest(model=name):
                pipeline, _ = rx.train_and_test(name, 0, X_train, y_train, X_train, y_train)
                self.assertAlmostEqual(rx.importance(pipeline).sum(), 1.0)


class TestSummary(unittest.TestCase):

    def test_protocol_c_averages_folds_before_seeds(self):
        runs = pd.DataFrame([
            # seed 0: folds 0.2, 0.4, 0.6 -> 0.4 ; seed 1: 0.3, 0.5, 0.7 -> 0.5
            {"protocol": "C", "model": "m", "seed": 0, "fold": "a", "macro_f1": 0.2, "balanced_accuracy": 0.2},
            {"protocol": "C", "model": "m", "seed": 0, "fold": "b", "macro_f1": 0.4, "balanced_accuracy": 0.4},
            {"protocol": "C", "model": "m", "seed": 0, "fold": "c", "macro_f1": 0.6, "balanced_accuracy": 0.6},
            {"protocol": "C", "model": "m", "seed": 1, "fold": "a", "macro_f1": 0.3, "balanced_accuracy": 0.3},
            {"protocol": "C", "model": "m", "seed": 1, "fold": "b", "macro_f1": 0.5, "balanced_accuracy": 0.5},
            {"protocol": "C", "model": "m", "seed": 1, "fold": "c", "macro_f1": 0.7, "balanced_accuracy": 0.7},
        ])
        row = rx.summarise(runs).iloc[0]
        self.assertAlmostEqual(row["macro_f1_mean"], 0.45)
        self.assertAlmostEqual(row["macro_f1_std"], np.std([0.4, 0.5], ddof=1), places=4)
        self.assertEqual(row["n_seeds"], 2)


if __name__ == "__main__":
    unittest.main()
