import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from astropy.io import fits

from epessto_plus.inventory import inventory, sha256
from epessto_plus.planning import build_plan
from test_foundations import raw_header
from test_planning import REFERENCE

PYPEIT_AVAILABLE = importlib.util.find_spec("pypeit") is not None
if PYPEIT_AVAILABLE:
    import pypeit
    PYPEIT_AVAILABLE = pypeit.__version__ == "1.14.0"
    from epessto_plus.pypeit_adapter import EPESSTOEFOSC2Spectrograph, inspect_setup
    from pypeit.metadata import PypeItMetaData
    from astropy.table import Table


def write_raw(root, name, **changes):
    h = raw_header()
    for key, value in {"DET OUT1 NX": 1024, "DET OUT1 NY": 1024,
                       "DET OUT1 OVSCY": 0, "DET OUT1 PRSCX": 0,
                       "DET OUT1 PRSCY": 0, "DET OUT1 X": 2049}.items():
        h["HIERARCH ESO " + key] = value
    h["ARCFILE"] = name
    for key, value in changes.items():
        h[("HIERARCH " if key.startswith("ESO ") else "") + key] = value
    path = Path(root) / name
    fits.PrimaryHDU(np.zeros((1030, 1030), dtype=np.int16), h).writeto(path)
    return path


@unittest.skipUnless(PYPEIT_AVAILABLE, "requires the existing PypeIt 1.14.0 environment")
class PypeItAdapterTests(unittest.TestCase):
    def test_profiles_have_explicit_effective_parameters(self):
        adapter = EPESSTOEFOSC2Spectrograph()
        for profile in ("rapid", "full"):
            par = adapter.profile_parameters(profile)
            self.assertEqual(par["calibrations"]["wavelengths"]["refframe"], "observed")
            for frame in (par["scienceframe"], par["calibrations"]["standardframe"]):
                self.assertFalse(frame["process"]["use_overscan"])
                self.assertFalse(frame["process"]["mask_cr"])
                self.assertEqual(frame["process"]["use_biasimage"], profile == "full")
                self.assertEqual(frame["process"]["use_pixelflat"], profile == "full")

    def test_frame_roles_are_mutually_exclusive(self):
        adapter = EPESSTOEFOSC2Spectrograph()
        table = Table({"idname": ["science", "standard_candidate", "non_spectroscopic", "processed", "dark"],
                       "exptime": [100., 100., 100., 100., 100.]})
        self.assertEqual(adapter.check_frame_type("science", table).tolist(), [True, False, False, False, False])
        self.assertEqual(adapter.check_frame_type("standard", table).tolist(), [False, True, False, False, False])
        self.assertFalse(adapter.check_frame_type("bias", table).any())
        self.assertTrue(adapter.check_frame_type("dark", table)[4])

    def test_filter_and_readout_split_native_configurations(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [write_raw(directory, "a.fits"),
                     write_raw(directory, "b.fits", **{"ESO INS FILT1 NAME": "GG495"}),
                     write_raw(directory, "c.fits", **{"ESO DET READ SPEED": "slow"})]
            instrument = EPESSTOEFOSC2Spectrograph()
            table = PypeItMetaData(instrument, instrument.profile_parameters("full"), files=[str(p) for p in paths])
            table.get_frame_types(user={p.name: "science" for p in paths})
            table.set_configurations()
            self.assertEqual(len(set(table.table["setup"])), 3)

    def test_native_reader_uses_header_noise_and_rejects_processed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_raw(directory, "a.fits")
            instrument = EPESSTOEFOSC2Spectrograph()
            det, raw, hdu, _, datamask, _ = instrument.get_rawimage(str(path), 1)
            try:
                self.assertEqual(float(det["ronoise"][0]), 7.8)
                self.assertEqual(float(det["gain"][0]), 0.91)
                self.assertEqual(raw.shape, (1030, 1030))
                self.assertEqual(np.count_nonzero(datamask), 1024*1024)
            finally:
                hdu.close()
            with fits.open(path) as hdu:
                hdu[0].header["FILETYPE"] = 22106
                with self.assertRaisesRegex(ValueError, "not an inspected raw"):
                    instrument.get_detector_par(1, hdu)

    def test_metadata_sorting_keeps_correct_file_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            late = write_raw(directory, "a-late.fits", OBJECT="Later", **{"MJD-OBS": 60629.2})
            early = write_raw(directory, "z-early.fits", OBJECT="Earlier", **{"MJD-OBS": 60629.1})
            report = inventory([directory])
            plan = build_plan(report, REFERENCE)
            result = inspect_setup(report, plan)
            rows = {Path(r["path"]).name: r for r in result["frames"]}
            self.assertEqual(rows[late.name]["target"], "Later")
            self.assertEqual(rows[early.name]["target"], "Earlier")
            self.assertEqual(rows[late.name]["sha256"], sha256(late))
            self.assertFalse(result["reduction_ready"])
            self.assertEqual(result["missing_wavelength_templates"], ["Gr13"])

    def test_changed_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_raw(directory, "a.fits")
            report = inventory([directory])
            plan = build_plan(report, REFERENCE)
            with fits.open(path, mode="update") as hdu:
                hdu[0].header["OBJECT"] = "Changed"
            with self.assertRaisesRegex(ValueError, "changed raw input"):
                inspect_setup(report, plan)

    def test_unmatched_standard_is_not_passed_to_pypeit(self):
        with tempfile.TemporaryDirectory() as directory:
            write_raw(directory, "std.fits", **{"ESO DPR TYPE": "STD"})
            report = inventory([directory])
            plan = build_plan(report, REFERENCE)
            with self.assertRaisesRegex(ValueError, "unverified standard"):
                inspect_setup(report, plan)


if __name__ == "__main__":
    unittest.main()
