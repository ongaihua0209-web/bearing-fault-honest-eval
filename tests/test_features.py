"""
Tests for src/features.py, using signals whose answers are known by hand.
"""

import unittest

import numpy as np

from src import features


class TestFeatureSetF1(unittest.TestCase):

    def test_sine_wave(self):
        # A sine of amplitude 2: RMS = 2/sqrt(2), peak = 2, peak-to-peak = 4,
        # crest factor = sqrt(2), kurtosis = 1.5, skewness = 0.
        t = np.arange(12_000) / 12_000
        x = 2 * np.sin(2 * np.pi * 50 * t)          # exactly 50 whole cycles
        f = features.features_f1(x).iloc[0]
        self.assertAlmostEqual(f["rms"], 2 / np.sqrt(2), places=6)
        self.assertAlmostEqual(f["peak"], 2, places=3)
        self.assertAlmostEqual(f["peak_to_peak"], 4, places=3)
        self.assertAlmostEqual(f["crest_factor"], np.sqrt(2), places=3)
        self.assertAlmostEqual(f["kurtosis"], 1.5, places=3)
        self.assertAlmostEqual(f["skewness"], 0, places=6)
        self.assertAlmostEqual(f["std"], f["rms"], places=6)

    def test_random_noise_has_kurtosis_3(self):
        rng = np.random.default_rng(0)
        f = features.features_f1(rng.normal(size=200_000)).iloc[0]
        self.assertAlmostEqual(f["kurtosis"], 3.0, delta=0.05)
        self.assertAlmostEqual(f["skewness"], 0.0, delta=0.02)

    def test_impacts_raise_kurtosis_and_crest_factor(self):
        rng = np.random.default_rng(1)
        x = rng.normal(0, 0.1, 2048)
        smooth = features.features_f1(x).iloc[0]
        x[::200] += 3.0                              # sharp knocks
        knocks = features.features_f1(x).iloc[0]
        self.assertGreater(knocks["kurtosis"], 10 * smooth["kurtosis"] / 3)
        self.assertGreater(knocks["crest_factor"], smooth["crest_factor"])

    def test_std_ignores_a_steady_offset_but_rms_does_not(self):
        rng = np.random.default_rng(2)
        x = rng.normal(size=2048)
        a = features.features_f1(x).iloc[0]
        b = features.features_f1(x + 5).iloc[0]
        self.assertAlmostEqual(a["std"], b["std"], places=10)
        self.assertGreater(b["rms"], a["rms"])

    def test_one_row_per_window(self):
        table = features.features_f1(np.random.default_rng(3).normal(size=(10, 2048)))
        self.assertEqual(table.shape, (10, 7))
        self.assertEqual(list(table.columns), features.FEATURE_NAMES_F1)



# ---------------------------------------------------------------------------
# F2 and F3
# ---------------------------------------------------------------------------

from src import bearing_physics as bp          # noqa: E402

FS = 12_000
RPM = 1797


def impact_train(rate_hz, n=8192, resonance_hz=4_200, noise=0.3, seed=0, shaft_modulation=False):
    """A fake faulty bearing: impacts at rate_hz ringing a resonance, in noise."""
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    t_ring = np.arange(120) / FS
    ring = np.exp(-t_ring / 0.0015) * np.sin(2 * np.pi * resonance_hz * t_ring)
    for t0 in np.arange(0, n / FS - 0.01, 1 / rate_hz):
        strength = 1 + 0.5 * np.cos(2 * np.pi * RPM / 60 * t0) if shaft_modulation else 1
        i = int(round(t0 * FS))
        x[i:i + ring.size] += strength * ring
    return x + rng.normal(0, noise, n)


class TestFeatureSetF2(unittest.TestCase):

    def test_sixteen_bands_from_0_to_4800_hz(self):
        self.assertEqual(len(features.FEATURE_NAMES_F2), 16)
        self.assertEqual(features.F2_EDGES_HZ[0], 0)
        self.assertEqual(features.F2_EDGES_HZ[-1], 4800)     # project rule: 0-4.8 kHz only

    def test_a_1khz_tone_lands_in_the_900_1200_hz_band(self):
        t = np.arange(2048) / FS
        f2 = features.features_f2(np.sin(2 * np.pi * 1000 * t)).iloc[0]
        self.assertEqual(f2.idxmax(), "band_0900_1200hz")


class TestFeatureSetF3(unittest.TestCase):

    def band_with(self, hz):
        return next(i for i, (lo, hi) in enumerate(features.F3_BANDS) if lo + 200 <= hz <= hi - 200)

    def f3(self, x):
        kurtosis, f3 = features.f3_for_every_band(x[None, :], [RPM])
        return dict(zip(features.FEATURE_NAMES_F3, f3[self.band_with(4200), 0]))

    def test_outer_race_impacts_show_at_bpfo(self):
        v = self.f3(impact_train(bp.fault_frequencies_hz(RPM)["BPFO"]))
        self.assertGreater(v["bpfo_1x"], v["bpfi_1x"] + 0.5)
        self.assertGreater(v["bpfo_1x"], v["2xbsf_1x"] + 0.5)
        self.assertGreater(v["bpfo_2x"], 0.5)                  # harmonics too

    def test_inner_race_impacts_show_at_bpfi(self):
        v = self.f3(impact_train(bp.fault_frequencies_hz(RPM)["BPFI"], shaft_modulation=True))
        self.assertGreater(v["bpfi_1x"], v["bpfo_1x"] + 0.5)
        self.assertGreater(v["bpfi_1x"], v["2xbsf_1x"] + 0.5)

    def test_ball_impacts_show_at_2xbsf(self):
        v = self.f3(impact_train(bp.fault_frequencies_hz(RPM)["2xBSF"]))
        self.assertGreater(v["2xbsf_1x"], v["bpfo_1x"] + 0.5)
        self.assertGreater(v["2xbsf_1x"], v["bpfi_1x"] + 0.5)

    def test_spikiest_band_contains_the_resonance(self):
        x = impact_train(bp.fault_frequencies_hz(RPM)["BPFO"], resonance_hz=2_600)
        kurtosis, _ = features.f3_for_every_band(x[None, :], [RPM])
        low, high = features.F3_BANDS[features.choose_band(kurtosis, [0])]
        self.assertTrue(low <= 2_600 <= high)

    def test_band_is_chosen_from_training_windows_only(self):
        kurtosis = np.zeros((10, len(features.F3_BANDS)))
        kurtosis[:6, 2] = 5.0          # training windows (0-5) favour band 2
        kurtosis[6:, 7] = 50.0         # test windows (6-9) favour band 7 strongly
        self.assertEqual(features.choose_band(kurtosis, np.arange(6)), 2)

    def test_levels_are_relative_to_the_median(self):
        freqs = np.arange(0, 1000, 1.0)
        amps = np.ones_like(freqs)
        bpfo = bp.fault_frequencies_hz(RPM)["BPFO"]
        amps[np.argmin(np.abs(freqs - bpfo))] = 100.0          # 100x the median
        values = dict(zip(features.FEATURE_NAMES_F3,
                          features.envelope_line_levels(freqs, amps, RPM)))
        self.assertAlmostEqual(values["bpfo_1x"], 2.0)          # log10(100)
        self.assertAlmostEqual(values["bpfi_1x"], 0.0)


if __name__ == "__main__":
    unittest.main()
