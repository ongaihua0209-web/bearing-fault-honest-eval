"""
Tests for src/check_fault_signatures.py.

Synthetic tests: we build fake faulty-bearing signals where we KNOW the
answer. Each is a train of impacts, repeating at one fault frequency, that
makes a resonance ring, buried in random noise. The method must find the
right fault type, and only that one.

Real-data tests are POSITIVE CONTROLS only: files whose fault signatures
are textbook-clear (inner race 0.007 in, outer race 0.007 in) must match,
and healthy files must show nothing. These were written before the script
was first run on real data. We deliberately do NOT write tests that expect
the ball files to fail: that is a finding to report, not a requirement.
"""

import unittest

import numpy as np

from src import bearing_physics as bp
from src import check_fault_signatures as sig
from src import config, load_data

FS = 12_000
RPM = 1797
SHAFT_HZ = RPM / 60


def impact_train(rate_hz, resonance_hz=3_000, seconds=10, noise=0.3,
                 shaft_modulation=False, seed=0):
    """
    A fake faulty bearing: an impact every 1/rate_hz seconds, each one making
    a resonance ring and die away within about 2 ms, plus random noise.

    The noise level (0.3, against impacts of size 1) is deliberately
    realistic. In an almost noise-free signal every band is full of fault
    and which one is "spikiest" stops meaning anything; real faults are
    buried in noise, which is the situation kurtosis band selection is for.

    shaft_modulation=True varies the impact strength once per shaft turn,
    as happens with an inner-race defect that moves in and out of the load
    zone.
    """
    rng = np.random.default_rng(seed)
    x = np.zeros(FS * seconds)
    t_ring = np.arange(int(0.01 * FS)) / FS
    ring = np.exp(-t_ring / 0.0015) * np.sin(2 * np.pi * resonance_hz * t_ring)
    for t0 in np.arange(0, seconds - 0.01, 1 / rate_hz):
        strength = 1 + 0.5 * np.cos(2 * np.pi * SHAFT_HZ * t0) if shaft_modulation else 1
        i = int(round(t0 * FS))
        x[i:i + ring.size] += strength * ring
    return x + rng.normal(0, noise, x.size)


class TestBandChoice(unittest.TestCase):

    def test_candidate_bands_stay_within_the_allowed_range(self):
        bands = sig.candidate_bands()
        self.assertEqual(bands[0], (400, 1600))
        self.assertEqual(bands[-1][1], config.LOWPASS_PASSBAND_EDGE_HZ)
        for low, high in bands:
            self.assertEqual(high - low, sig.BAND_WIDTH_HZ)

    def test_spikiest_band_contains_the_ringing_not_a_loud_hum(self):
        # Impacts ringing at 3.5 kHz, plus a much louder steady 1 kHz hum.
        t = np.arange(FS * 10) / FS
        x = impact_train(bp.fault_frequencies_hz(RPM)["BPFO"], resonance_hz=3_500)
        x += 2.0 * np.sin(2 * np.pi * 1_000 * t)
        (low, high), kurtosis = sig.most_impulsive_band(x)
        self.assertLessEqual(low, 3_500)
        self.assertGreaterEqual(high, 3_500)
        self.assertGreater(kurtosis, 1)

    def test_noise_is_not_spiky(self):
        rng = np.random.default_rng(3)
        self.assertLess(abs(sig.spikiness(rng.normal(size=120_000))), 0.1)


class TestSyntheticFaults(unittest.TestCase):

    def check(self, rate_name, label, **kwargs):
        x = impact_train(bp.fault_frequencies_hz(RPM)[rate_name], **kwargs)
        result, _ = sig.check_signal(x, RPM, label)
        return result

    def test_outer_race_fault_is_found(self):
        result = self.check("BPFO", "outer_race")
        self.assertEqual(result["clear_types"], "outer_race")
        self.assertEqual(result["verdict"], "matches label")
        self.assertEqual(result["verdict_narrow"], "matches label")

    def test_inner_race_fault_is_found(self):
        result = self.check("BPFI", "inner_race", shaft_modulation=True)
        self.assertEqual(result["clear_types"], "inner_race")
        self.assertEqual(result["verdict"], "matches label")
        self.assertEqual(result["verdict_narrow"], "matches label")

    def test_ball_fault_is_found(self):
        result = self.check("2xBSF", "ball")
        self.assertEqual(result["clear_types"], "ball")
        self.assertEqual(result["verdict"], "matches label")
        self.assertEqual(result["verdict_narrow"], "matches label")

    def test_peak_position_is_recorded(self):
        result = self.check("BPFO", "outer_race")
        self.assertAlmostEqual(result["sel_outer_race_at_order"],
                               bp.bpfo_multiplier(), delta=0.02)

    def test_mislabelled_signal_is_flagged(self):
        # An outer-race signal carrying a ball label must be called out.
        result = self.check("BPFO", "ball")
        self.assertEqual(result["verdict"], "looks like outer_race")

    def test_noise_shows_no_fault(self):
        rng = np.random.default_rng(4)
        x = rng.normal(size=FS * 10)
        normal, _ = sig.check_signal(x, RPM, "normal")
        faulty, _ = sig.check_signal(x, RPM, "inner_race")
        self.assertEqual(normal["clear_types"], "none")
        self.assertEqual(normal["verdict"], "matches label")
        self.assertEqual(faulty["verdict"], "no signature")


class TestWindows(unittest.TestCase):

    def test_narrow_ball_window_excludes_the_inner_race_sideband(self):
        """
        Inner-race files show a sideband at BPFI - 3 x shaft speed. Measured
        BPFI is 5.40 x, so the sideband is at 2.40 x: inside the +/-2% BSF
        window, outside the +/-1% one. That is why the narrow check exists.
        """
        sideband = 5.40 - 3
        bsf = bp.bsf_multiplier()
        self.assertGreaterEqual(bsf * (1 + sig.SEARCH_TOLERANCE), sideband)
        self.assertLess(bsf * (1 + sig.NARROW_TOLERANCE), sideband)

    def test_narrow_windows_still_allow_the_slip_seen_in_clean_files(self):
        # Clean files put BPFO at up to 3.61 x and BPFI at down to 5.40 x.
        self.assertGreater(bp.bpfo_multiplier() * (1 + sig.NARROW_TOLERANCE), 3.61)
        self.assertLess(bp.bpfi_multiplier() * (1 - sig.NARROW_TOLERANCE), 5.40)


class TestRigWideRawPeaks(unittest.TestCase):

    def test_finds_a_tone_at_the_fan_end_inner_race_frequency(self):
        t = np.arange(FS * 10) / FS
        fe_hz = config.FAN_END_CWRU_MULTIPLIERS["BPFI"] * SHAFT_HZ
        rng = np.random.default_rng(5)
        x = 0.2 * np.sin(2 * np.pi * fe_hz * t) + rng.normal(0, 0.3, t.size)
        found = sig.rig_wide_raw_peaks(x, RPM)
        ratio, position = found["raw_fan_end_BPFI"]
        self.assertGreater(ratio, 10)
        self.assertAlmostEqual(position, config.FAN_END_CWRU_MULTIPLIERS["BPFI"], delta=0.01)
        self.assertLess(found["raw_drive_end_BPFI"][0], 10)


class TestVerdictRules(unittest.TestCase):

    def test_rules(self):
        cases = [("normal", [], "matches label"),
                 ("normal", ["ball"], "unexpected: ball"),
                 ("ball", ["ball", "inner_race"], "matches label"),
                 ("ball", ["inner_race"], "looks like inner_race"),
                 ("outer_race", ["inner_race", "ball"], "looks like inner_race + ball"),
                 ("outer_race", [], "no signature")]
        for label, clear, expected in cases:
            with self.subTest(label=label, clear=clear):
                self.assertEqual(sig.verdict(label, clear), expected)


class TestPositiveControlsOnRealData(unittest.TestCase):
    """Textbook-clear files must pass; healthy files must show nothing."""

    def run_files(self, numbers, label, expected_verdict):
        if not all(load_data.mat_path(n).exists() for n in numbers):
            self.skipTest("files not in data/raw/")
        for number in numbers:
            with self.subTest(file=number):
                signal, rpm, fs = load_data.load_signal(number)
                result, _ = sig.check_signal(signal, rpm, label, fs)
                self.assertEqual(result["verdict"], expected_verdict)

    def test_inner_race_0_007_files_match(self):
        self.run_files([105, 106, 107, 108], "inner_race", "matches label")

    def test_outer_race_0_007_files_match(self):
        self.run_files([130, 131, 132, 133], "outer_race", "matches label")

    def test_normal_files_show_no_fault(self):
        self.run_files([97, 98, 99, 100], "normal", "matches label")


if __name__ == "__main__":
    unittest.main()
