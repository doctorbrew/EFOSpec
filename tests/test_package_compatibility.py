"""The EFOSpec rename must preserve observer scripts and saved product identity."""
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from astropy.io import fits

from test_foundations import raw_header


class PackageCompatibilityTests(unittest.TestCase):
    def test_old_imports_use_the_same_module_objects(self):
        for name in ('inventory', 'naming', 'planning', 'native_readiness',
                     'archive_calibration', 'download', 'rapid', 'report',
                     'qa', 'sky_regions', 'spatial_profiles'):
            with self.subTest(module=name):
                self.assertIs(importlib.import_module('epessto_plus.'+name),
                              importlib.import_module('efospec.'+name))
        from efospec.__main__ import main
        from epessto_plus.__main__ import main as old_main
        self.assertIs(old_main, main)

    def test_new_and_old_commands_produce_identical_inventories(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'raw.fits'
            fits.PrimaryHDU(np.zeros((8, 8)), raw_header()).writeto(path)
            commands = [[sys.executable, '-m', 'efospec'],
                        [sys.executable, '-m', 'epessto_plus'],
                        [str(Path(sys.executable).with_name('efospec'))],
                        [str(Path(sys.executable).with_name('epessto-plus'))]]
            inventories = []
            for command in commands:
                process = subprocess.run(command+['inventory', str(path)],
                                         capture_output=True, text=True, check=True)
                inventories.append(json.loads(process.stdout))
            self.assertEqual(len(inventories[0]['frames']), 1)
            for result in inventories[1:]:
                self.assertEqual(result, inventories[0])

    def test_old_sky_recovery_module_still_dispatches(self):
        for name in ('efospec.sky_regions', 'epessto_plus.sky_regions'):
            process = subprocess.run([sys.executable, '-m', name, '--help'],
                                     capture_output=True, text=True, check=True)
            self.assertIn('--target', process.stdout)

    @unittest.skipUnless(importlib.util.find_spec('pypeit'), 'requires PypeIt')
    def test_saved_instrument_identifier_and_old_class_remain_compatible(self):
        from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
        from epessto_plus.pypeit_adapter import EPESSTOEFOSC2Spectrograph
        self.assertIs(EFOSpecEFOSC2Spectrograph, EPESSTOEFOSC2Spectrograph)
        self.assertEqual(EFOSpecEFOSC2Spectrograph.name, 'ntt_efosc2_epessto')
