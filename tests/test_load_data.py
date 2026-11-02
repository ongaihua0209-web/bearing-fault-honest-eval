"""
Tests for src/load_data.py and the file list in src/config.py.

Most tests use small made-up examples (so they test the LOGIC and run
fast). A few use the real files in data/raw/ and are skipped automatically
for any file that is not there.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import scipy.io
import scipy.signal

from src import config, load_data


class TestExpectedFileList(unittest.TestCase):

    def setUp(self):
        self.rows = {r["file_number"]: r for r in config.expected_files()}

    def test_forty_unique_files(self):
        self.assertEqual(len(config.expected_files()), 40)
        self.assertEqual(len(self.rows), 40)

    def test_some_labels(self):
        # (location, size, load) for a few files, copied from the project brief
        checks = {97: ("normal", 0.0, 0), 100: ("normal", 0.0, 3),
                  105: ("inner_race", 0.007, 0), 172: ("inner_race", 0.014, 3),
                  120: ("ball", 0.007, 2), 225: ("ball", 0.021, 3),
                  130: ("outer_race", 0.007, 0), 237: ("outer_race", 0.021, 3)}
        for number, (location, size, load) in checks.items():
            with self.subTest(file=number):
                r = self.rows[number]
                self.assertEqual(r["fault_location"], location)
                self.assertEqual(r["fault_size_in"], size)
                self.assertEqual(r["load_hp"], load)


class TestPickVariables(unittest.TestCase):

    def test_variable_named_after_file_is_chosen(self):
        variables = {"X099_DE_time": [1], "X098_DE_time": [2]}
        chosen, notes = load_data.pick_de_variable(variables, 99)
        self.assertEqual(chosen, "X099_DE_time")
        self.assertIn("X098_DE_time", notes[0])      # extra variable reported

    def test_single_misnamed_variable_is_used_with_a_note(self):
        chosen, notes = load_data.pick_de_variable({"X056_DE_time": [1]}, 130)
        self.assertEqual(chosen, "X056_DE_time")
        self.assertEqual(len(notes), 1)

    def test_no_de_variable_is_an_error(self):
        with self.assertRaises(ValueError):
            load_data.pick_de_variable({"X100_FE_time": [1]}, 100)

    def test_several_misnamed_variables_is_an_error(self):
        with self.assertRaises(ValueError):
            load_data.pick_de_variable({"X001_DE_time": [1], "X002_DE_time": [2]}, 100)

    def test_stored_rpm_is_used(self):
        rpm, source = load_data.pick_rpm({"X105RPM": np.array([[1796]])},
                                         "X105_DE_time", load_hp=0)
        self.assertEqual((rpm, source), (1796.0, "stored"))

    def test_nominal_rpm_when_none_stored(self):
        rpm, source = load_data.pick_rpm({}, "X097_DE_time", load_hp=2)
        self.assertEqual((rpm, source), (1750.0, "nominal"))

    def test_rpm_of_another_recording_is_not_used(self):
        # X098RPM belongs to X098's signal, not to X099's.
        rpm, source = load_data.pick_rpm({"X098RPM": np.array([[1772]])},
                                         "X099_DE_time", load_hp=2)
        self.assertEqual(source, "nominal")


class TestDuplicates(unittest.TestCase):

    def test_identical_signals_are_found(self):
        a = np.arange(5000.0)
        signals = [(98, "X098_DE_time", a), (99, "X099_DE_time", a.copy()),
                   (100, "X100_DE_time", a + 1)]
        exact, shared = load_data.find_duplicates(signals)
        self.assertEqual(exact, [[(98, "X098_DE_time"), (99, "X099_DE_time")]])
        self.assertEqual(shared, [])

    def test_partial_copy_is_reported_separately(self):
        a = np.arange(5000.0)
        b = a.copy()
        b[-1] = -1.0                      # same start, different end
        exact, shared = load_data.find_duplicates([(1, "x", a), (2, "y", b)])
        self.assertEqual(exact, [])
        self.assertEqual(len(shared), 1)

    def test_same_label_copies_keep_lowest_number(self):
        labels = {98: ("normal", 0.0), 99: ("normal", 0.0)}
        excluded = load_data.choose_exclusions({98: "abc", 99: "abc"}, labels)
        self.assertEqual(list(excluded), [99])

    def test_different_label_copies_are_all_excluded(self):
        labels = {99: ("normal", 0.0), 105: ("inner_race", 0.007)}
        excluded = load_data.choose_exclusions({99: "abc", 105: "abc"}, labels)
        self.assertEqual(sorted(excluded), [99, 105])


class TestBuildManifestOnFakeFolder(unittest.TestCase):
    """Build a manifest from a temporary folder holding 3 fake files."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name)
        rng = np.random.default_rng(0)
        signal = rng.normal(size=(1200, 1))
        scipy.io.savemat(folder / "97.mat", {"X097_DE_time": signal, "X097RPM": 1796})
        # 98 is an exact copy of 97's signal under its own name, no RPM stored
        scipy.io.savemat(folder / "98.mat", {"X098_DE_time": signal})
        scipy.io.savemat(folder / "105.mat", {"X105_DE_time": rng.normal(size=(2400, 1))})
        scipy.io.savemat(folder / "999.mat", {"X999_DE_time": signal[:10]})
        cls.manifest, cls.findings = load_data.build_manifest(folder)
        cls.by_number = cls.manifest.set_index("file_number")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_one_row_per_expected_file(self):
        self.assertEqual(len(self.manifest), 40)

    def test_required_columns(self):
        for column in ("file_number", "fault_location", "fault_size_in", "load_hp",
                       "rpm", "sampling_rate_hz", "n_samples", "duration_s", "status"):
            self.assertIn(column, self.manifest.columns)

    def test_missing_files_are_reported(self):
        self.assertEqual((self.manifest["status"] == "missing").sum(), 37)

    def test_duplicate_is_excluded_and_original_kept(self):
        self.assertEqual(self.by_number.loc[97, "status"], "ok")
        self.assertEqual(self.by_number.loc[98, "status"], "excluded_duplicate")

    def test_rpm_source(self):
        self.assertEqual(self.by_number.loc[97, "rpm_source"], "stored")
        self.assertEqual(self.by_number.loc[98, "rpm_source"], "nominal")
        self.assertEqual(self.by_number.loc[98, "rpm"], 1772)

    def test_duration(self):
        self.assertAlmostEqual(self.by_number.loc[105, "duration_s"], 0.2)

    def test_unexpected_file_is_reported(self):
        self.assertEqual(self.findings["unexpected_files"], ["999.mat"])


class TestResampling(unittest.TestCase):

    def test_48k_to_12k_keeps_a_30hz_sine_at_30hz(self):
        t = np.arange(48_000 * 4) / 48_000                  # 4 seconds at 48 kHz
        x = np.sin(2 * np.pi * 30 * t)
        y = load_data.resample_to_target(x, 48_000, 12_000)
        self.assertEqual(len(y), len(x) // 4)
        freqs = np.fft.rfftfreq(len(y), 1 / 12_000)
        peak = freqs[np.argmax(np.abs(np.fft.rfft(y)))]
        self.assertAlmostEqual(peak, 30.0, delta=0.3)

    def test_no_change_when_rates_match(self):
        x = np.arange(10.0)
        np.testing.assert_array_equal(load_data.resample_to_target(x, 12_000, 12_000), x)


class TestAgainstOfficialWebsite(unittest.TestCase):
    """
    data/cwru_official_reference.csv records what CWRU's official website
    listed on 2026-11-02: every file's official name and size in bytes.
    These tests compare our labels and files with it, without going online.
    """

    @classmethod
    def setUpClass(cls):
        import csv
        with open(config.OFFICIAL_REFERENCE_CSV, newline="") as f:
            cls.official = {int(r["file_number"]): r for r in csv.DictReader(f)}

    def test_reference_covers_exactly_our_40_files(self):
        ours = {r["file_number"] for r in config.expected_files()}
        self.assertEqual(set(self.official), ours)

    def test_every_label_matches_the_official_name(self):
        for r in config.expected_files():
            with self.subTest(file=r["file_number"]):
                self.assertEqual(r["cwru_name"],
                                 self.official[r["file_number"]]["cwru_name"])

    def test_name_examples(self):
        self.assertEqual(config.cwru_name("inner_race", 0.007, 0), "IR007_0")
        self.assertEqual(config.cwru_name("outer_race", 0.021, 3), "OR021@6_3")
        self.assertEqual(config.cwru_name("ball", 0.014, 2), "B014_2")
        self.assertEqual(config.cwru_name("normal", 0.0, 1), "Normal_1")

    def test_every_file_is_the_official_size_to_the_byte(self):
        for number, row in self.official.items():
            path = load_data.mat_path(number)
            if not path.exists():
                continue
            with self.subTest(file=number):
                self.assertEqual(path.stat().st_size, int(row["size_bytes"]))


class TestLowpass(unittest.TestCase):
    """The 5 kHz low-pass filter must meet the spec written in config.py."""

    def setUp(self):
        taps = load_data.lowpass_filter_taps()
        freqs = np.linspace(0, 6000, 6001)
        _, h = scipy.signal.freqz(taps, worN=freqs, fs=12_000)
        self.freqs = freqs
        # Applied forwards and backwards, so the dB effect doubles.
        self.gain_db = 2 * 20 * np.log10(np.maximum(np.abs(h), 1e-15))

    def test_passband_is_flat(self):
        keep = self.freqs <= config.LOWPASS_PASSBAND_EDGE_HZ
        self.assertLess(np.abs(self.gain_db[keep]).max(), 0.1)

    def test_stopband_is_at_least_120_db_down(self):
        cut = self.freqs >= config.LOWPASS_STOPBAND_EDGE_HZ
        self.assertLess(self.gain_db[cut].max(), -120)

    def test_low_frequency_sine_is_unchanged_and_not_delayed(self):
        t = np.arange(12_000 * 2) / 12_000
        x = np.sin(2 * np.pi * 1000 * t)
        y = load_data.lowpass(x)
        middle = slice(1000, -1000)                 # ignore the very ends
        self.assertLess(np.abs(y[middle] - x[middle]).max(), 1e-3)

    def test_high_frequency_sine_is_removed(self):
        t = np.arange(12_000 * 2) / 12_000
        y = load_data.lowpass(np.sin(2 * np.pi * 5500 * t))
        self.assertLess(np.abs(y[1000:-1000]).max(), 1e-5)


class TestRealFiles(unittest.TestCase):
    """Sanity checks on whichever real CWRU files are present."""

    def test_present_files_load_sensibly(self):
        present = [r for r in config.expected_files()
                   if load_data.mat_path(r["file_number"]).exists()]
        if not present:
            self.skipTest("no CWRU files in data/raw/")
        for r in present:
            with self.subTest(file=r["file_number"]):
                signal, rpm, fs = load_data.load_signal(r["file_number"])
                self.assertEqual(signal.ndim, 1)
                self.assertEqual(fs, 12_000)
                # > 4 seconds (the shortest file, normal 97, is about 5 s)
                self.assertGreater(signal.size, 12_000 * 4)
                self.assertTrue(np.all(np.isfinite(signal)))
                self.assertGreater(rpm, 1650)
                self.assertLess(rpm, 1850)

    def test_known_copy_inside_file_99_is_reported_not_used(self):
        """
        CWRU's 99.mat also contains X098_DE_time, an exact copy of 98.mat's
        signal. It must be reported, and 99 must use its own X099 signal.
        """
        if not (load_data.mat_path(98).exists() and load_data.mat_path(99).exists()):
            self.skipTest("files 98 and 99 not in data/raw/")
        manifest, findings = load_data.build_manifest()
        self.assertIn([(98, "X098_DE_time"), (99, "X098_DE_time")],
                      findings["exact_duplicate_groups"])
        row = manifest.set_index("file_number").loc[99]
        self.assertEqual(row["de_variable"], "X099_DE_time")
        self.assertEqual(row["status"], "ok")


if __name__ == "__main__":
    unittest.main()
