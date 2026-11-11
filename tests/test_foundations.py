from datetime import date
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from astropy.io import fits

from efospec.inventory import classify, inventory
from efospec.naming import observing_night, processing_mjd, product_name, science_stem


def raw_header(**changes):
    header = fits.Header({
        "INSTRUME": "EFOSC", "OBJECT": "Target", "DATE-OBS": "2024-11-15T01:00:00.100",
        "MJD-OBS": 60629.0416678, "EXPTIME": 600.0, "ARCFILE": "exposure.fits",
        "RA": 10.0, "DEC": -30.0, "NAXIS": 2, "NAXIS1": 1030, "NAXIS2": 1030,
        "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN", "CDELT1": 2.0, "CDELT2": 2.0,
    })
    for key, value in {
        "DPR CATG": "SCIENCE", "DPR TYPE": "OBJECT", "DPR TECH": "SPECTRUM",
        "INS GRIS1 NAME": "Gr#13", "INS FILT1 NAME": "Free", "INS SLIT1 NAME": "slit#1.0",
        "DET WIN1 BINX": 2, "DET WIN1 BINY": 2, "DET READ SPEED": "fastL",
        "DET OUT1 GAIN": 0.91, "DET OUT1 RON": 7.8, "TEL AIRM START": 1.1,
    }.items():
        header["HIERARCH ESO " + key] = value
    header.update(changes)
    return header


class NamingTests(unittest.TestCase):
    def test_night_noon_boundary_and_fractional_seconds(self):
        self.assertEqual(observing_night("2024-11-15T11:59:59.999"), "20241114")
        self.assertEqual(observing_night("2024-11-15T12:00:00"), "20241115")
        self.assertEqual(observing_night("2025-01-01T01:00:00Z"), "20241231")

    def test_actual_template_name(self):
        stem = science_stem("LSQ12btn", "2012-04-12T00:21:13.428", "Gr#13", "Free", "slit#1.0")
        self.assertEqual(product_name(stem, "2012-04-12T00:21:13.428", {}),
                         "tLSQ12btn_20120411_Gr13_Free_slit1.0_1.fits")

    def test_full_run_date_is_explicit(self):
        self.assertEqual(processing_mjd(date(2012, 1, 1)), 55927)
        args = ("SN A/B#1", "2024-11-15T01:00:00", "Gr#13", "Free", "slit#1.0")
        with self.assertRaises(ValueError):
            science_stem(*args, profile="full")
        self.assertEqual(science_stem(*args, profile="full", run_mjd=60630),
                         "tSNA_B1_20241114_Gr13_Free_slit1.0_60630")

    def test_allocation_is_idempotent_and_fills_gaps(self):
        existing = {"tA_1_f.fits": "old", "tA_3_f.fits": "same"}
        self.assertEqual(product_name("tA", "same", existing, "_f"), "tA_3_f.fits")
        self.assertEqual(product_name("tA", "new", existing, "_f"), "tA_2_f.fits")

    def test_collisions_above_99(self):
        existing = {f"tA_{n}.fits": str(n) for n in range(1, 101)}
        self.assertEqual(product_name("tA", "new", existing), "tA_101.fits")
        self.assertEqual(product_name("tA", "100", existing), "tA_100.fits")

    def test_ambiguous_identity_and_path_traversal_fail(self):
        with self.assertRaises(ValueError):
            product_name("tA", "same", {"tA_1.fits": "same", "tA_2.fits": "same"})
        with self.assertRaises(ValueError):
            science_stem("SN", "2024-11-15", "../Gr13", "Free", "slit1.0")
        with self.assertRaises(ValueError):
            product_name("../tA", "date", {})

    def test_observing_night_matches_unmodified_legacy_code(self):
        path = Path(__file__).resolve().parents[1] / "trunk/src/ntt/util.py"
        spec = importlib.util.spec_from_file_location("legacy_util", path)
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        for value in ("2012-04-12T00:21:13.428", "2024-11-15T11:59:59", "2025-01-01T12:00:00"):
            h = raw_header(**{"DATE-OBS": value})
            self.assertEqual(observing_night(value), legacy.readkey3(h, "date-night"))


class ClassificationTests(unittest.TestCase):
    def test_science_and_named_standard(self):
        self.assertEqual(classify(raw_header()), "science")
        self.assertEqual(classify(raw_header(**{"OBJECT": "Feige110", "ESO DPR TYPE": "STD"})),
                         "standard_candidate")

    def test_imaging_standard_is_excluded(self):
        self.assertEqual(classify(raw_header(**{"ESO DPR TYPE": "STD", "ESO DPR TECH": "IMAGE"})),
                         "non_spectroscopic")

    def test_calibration_types(self):
        for kind, tech, expected in (("WAVE", "SPECTRUM", "arc"), ("LAMP,FLAT", "SPECTRUM", "flat"),
                                     ("BIAS", "IMAGE", "bias"), ("DARK", "IMAGE", "dark")):
            with self.subTest(kind=kind):
                self.assertEqual(classify(raw_header(**{"ESO DPR TYPE": kind,
                    "ESO DPR TECH": tech, "ESO DPR CATG": "CALIB"})), expected)

    def test_zero_exposure_dark_template_is_bias_without_changing_header(self):
        header = raw_header(**{'ESO DPR CATG': 'CALIB', 'ESO DPR TECH': 'IMAGE',
            'ESO DPR TYPE': 'DARK', 'ESO TPL ID': 'EFOSC_img_cal_Darks', 'EXPTIME': 0.})
        before = header.tostring()
        self.assertEqual(classify(header), 'bias')
        self.assertEqual(header.tostring(), before)
        for changes in ({'EXPTIME': 1.}, {'EXPTIME': None},
                        {'ESO TPL ID': 'unknown'}, {'ESO DPR TECH': 'SPECTRUM'}):
            with self.subTest(changes=changes):
                candidate = header.copy()
                candidate.update(changes)
                self.assertEqual(classify(candidate), 'dark')

    def test_processed_arc_and_rectified_science_are_not_raw(self):
        self.assertEqual(classify(raw_header(**{"FILETYPE": 22104, "ESO DPR TYPE": "WAVE"})), "processed")
        self.assertEqual(classify(raw_header(**{"CTYPE2": "LINEAR"})), "processed")
        self.assertEqual(classify(raw_header(**{"NAXIS1": 851})), "review_geometry")

    def test_missing_or_unrecognized_type_needs_review(self):
        self.assertEqual(classify(raw_header(**{"ESO DPR TYPE": "STD,TELLURIC"})), "review_type")
        self.assertEqual(classify(raw_header(**{"ESO DPR TECH": ""})), "review_type")
        self.assertEqual(classify(raw_header(**{"INSTRUME": "SOFI"})), "other_instrument")


class InventoryTests(unittest.TestCase):
    def write_raw(self, directory, name="raw.fits", **changes):
        path = Path(directory) / name
        fits.PrimaryHDU(np.zeros((1030, 1030), dtype=np.int16), raw_header(**changes)).writeto(path)
        return path

    def test_read_only_duplicate_source_details_and_missing_calibrations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_raw(directory)
            before = path.read_bytes()
            (Path(directory) / "copy.fits").write_bytes(before)
            report = inventory([directory, path])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(report["duplicate_count"], 1)
            self.assertEqual(report["counts_unique_content"], {"science": 1})
            self.assertFalse(report["reduction_ready"])
            self.assertTrue(any("Gr13" in b for b in report["blockers"]))
            self.assertTrue(any("raw arc" in b for b in report["blockers"]))
            self.assertEqual(report["frames"][0]["issues"], [])
            self.assertEqual(len(report["frames"][0]["sha256"]), 64)

    def test_flat_template_test_exposure_does_not_block_or_fill_calibration_stack(self):
        from efospec.native_readiness import assess_native_readiness

        with tempfile.TemporaryDirectory() as directory:
            self.write_raw(directory)
            self.write_raw(directory, "flat-test.fits", **{
                "ARCFILE": "flat-test.fits", "ESO DPR CATG": "CALIB",
                "ESO DPR TYPE": "DOME", "ESO TPL ID": "EFOSC_spec_cal_Flats",
                "ESO TPL EXPNO": 1, "ESO TPL NEXP": 6,
            })
            report = inventory([directory])
            self.assertEqual(report["counts_unique_content"], {"flat_test": 1, "science": 1})
            test = next(f for f in report['frames'] if f['role'] == 'flat_test')
            self.assertEqual(test['metadata']['ESO TPL EXPNO'], 1)
            readiness = assess_native_readiness(report)
            self.assertEqual(readiness['invalid_inputs'], [])
            self.assertEqual(readiness['calibration_tests_ignored'], [test['path']])
            self.assertEqual(readiness['exposures'][0]['raw_calibrations']['flat']['status'], 'missing')

    def test_dome_label_alone_does_not_exempt_unknown_frames(self):
        for changes in ({}, {'ESO TPL ID': 'EFOSC_spec_cal_Flats'},
                        {'ESO TPL ID': 'EFOSC_spec_cal_Flats', 'ESO TPL EXPNO': 2},
                        {'ESO TPL ID': 'different', 'ESO TPL EXPNO': 1}):
            with self.subTest(changes=changes):
                header = raw_header(**{'ESO DPR CATG': 'CALIB', 'ESO DPR TYPE': 'DOME', **changes})
                self.assertEqual(classify(header), 'review_type')

    def test_arcff_test_is_visible_but_never_selected_as_a_master_flat(self):
        from efospec.native_readiness import assess_native_readiness

        with tempfile.TemporaryDirectory() as directory:
            self.write_raw(directory)
            path = self.write_raw(directory, 'arcff-test.fits', **{
                'ARCFILE': 'arcff-test.fits', 'ESO DPR CATG': 'CALIB',
                'ESO DPR TYPE': 'DOME', 'ESO TPL ID': 'EFOSC_spec_cal_ArcFF',
                'ESO TPL EXPNO': 2, 'ESO TPL NEXP': 9})
            before = path.read_bytes()
            report = inventory([directory])
            self.assertEqual(report['counts_unique_content'], {'flat_test': 1, 'science': 1})
            readiness = assess_native_readiness(report)
            self.assertEqual(readiness['invalid_inputs'], [])
            self.assertEqual(readiness['calibration_tests_ignored'], [str(path.resolve())])
            self.assertEqual(readiness['exposures'][0]['raw_calibrations']['flat']['files'], [])
            self.assertEqual(path.read_bytes(), before)
        for number in (1, 3, None):
            header = raw_header(**{'ESO DPR CATG': 'CALIB', 'ESO DPR TYPE': 'DOME',
                'ESO TPL ID': 'EFOSC_spec_cal_ArcFF', 'ESO TPL EXPNO': number})
            self.assertEqual(classify(header), 'review_type')

    def test_conflicting_archive_identity_is_not_silently_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_raw(directory)
            self.write_raw(directory, "different.fits", OBJECT="Other")
            report = inventory([directory])
            self.assertIn("exposure.fits", report["identity_conflicts"])
            self.assertEqual(report["counts_unique_content"]["science"], 2)

    def test_corrupt_file_reported_and_valid_files_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_raw(directory)
            (Path(directory) / "broken.fits").write_text("not FITS")
            report = inventory([directory])
            self.assertEqual(len(report["errors"]), 1)
            self.assertEqual(len(report["frames"]), 1)

    def test_binning_disagreement_and_missing_header_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_raw(directory, CDELT1=1, **{"ESO DET OUT1 RON": ""})
            report = inventory([directory])
            self.assertIn("CDELT1 disagrees with detector binning", report["frames"][0]["issues"])
            self.assertIn("missing ESO DET OUT1 RON", report["frames"][0]["issues"])

    def test_missing_and_empty_input_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                inventory([directory])
            with self.assertRaises(FileNotFoundError):
                inventory([Path(directory) / "missing"])


if __name__ == "__main__":
    unittest.main()
