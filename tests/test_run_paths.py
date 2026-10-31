"""Moved runs must use their own data, even when the original still exists."""
from pathlib import Path
import tempfile
import unittest

from efospec.run_paths import resolve_result_paths


class RunPathTests(unittest.TestCase):
    def test_selected_run_wins_over_existing_old_paths_without_mutating_record(self):
        with tempfile.TemporaryDirectory() as directory:
            old, moved = Path(directory)/'old', Path(directory)/'moved'
            for run in (old, moved):
                (run/'products').mkdir(parents=True)
                (run/'native').mkdir()
                (run/'products/spectrum.fits').write_bytes(run.name.encode())
                (run/'native/spec1d.fits').write_bytes(run.name.encode())
            record = {'product': str(old/'products/spectrum.fits'),
                      'native_spec1d': str(old/'native/spec1d.fits'),
                      'raw': '/external/raw.fits', 'object': 'SNtest'}
            before = dict(record)
            resolved = resolve_result_paths(record, moved)
            self.assertEqual(Path(resolved['product']).read_bytes(), b'moved')
            self.assertEqual(Path(resolved['native_spec1d']).read_bytes(), b'moved')
            self.assertEqual(resolved['raw'], record['raw'])
            self.assertEqual(record, before)

    def test_missing_local_product_never_falls_back_to_an_old_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory)/'spectrum.fits'
            old.write_bytes(b'unrelated copy')
            with self.assertRaisesRegex(FileNotFoundError, 'selected run'):
                resolve_result_paths({'product': str(old)}, Path(directory)/'moved')

    def test_missing_local_native_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run/'products').mkdir()
            (run/'products/spectrum.fits').touch()
            with self.assertRaisesRegex(FileNotFoundError, 'native_spec1d'):
                resolve_result_paths({'product': 'spectrum.fits',
                                      'native_spec1d': 'missing.fits'}, run)
