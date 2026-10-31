from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from efospec.native_readiness import assess_native_readiness
from test_planning import frame, report


class NativeReadinessTests(unittest.TestCase):
    def test_processed_calibrations_never_fill_missing_raw_inputs(self):
        result = assess_native_readiness(report([frame(), frame('archived_arc', 'processed'),
                                                frame('archived_sensitivity', 'processed')]))
        self.assertEqual(result['exposures'][0]['raw_calibrations']['arc']['status'], 'missing')
        self.assertEqual(len(result['processed_inputs_ignored']), 2)
        self.assertFalse(result['iraf_calibration_products_allowed'])
        self.assertFalse(result['raw_candidates_complete'])

    def test_complete_candidates_do_not_claim_native_execution_or_flux_validation(self):
        frames = [frame(), frame('arc', 'arc'), frame('std', 'standard_candidate')]
        for role in ['bias', 'flat']:
            for n in range(3):
                f = frame(f'{role}{n}', role)
                f['metadata']['OBJECT'] = role
                frames.append(f)
        # A native preflight must not open a legacy reference catalogue/file.
        with patch('builtins.open', side_effect=AssertionError('unexpected reference access')):
            result = assess_native_readiness(report(frames))
        self.assertTrue(result['raw_candidates_complete'])
        self.assertFalse(result['native_execution_implemented'])
        self.assertFalse(result['reduction_ready'])
        self.assertIn('physical flux references', ' '.join(result['blockers']))

    def test_wrong_setup_arc_is_rejected(self):
        arc = frame('arc', 'arc')
        arc['setup']['grism'] = 'Gr11'
        result = assess_native_readiness(report([frame(), arc]))
        selection = result['exposures'][0]['raw_calibrations']['arc']
        self.assertEqual(selection['status'], 'missing')
        self.assertIn('different grism', selection['rejected'][0]['reasons'])

    def test_invalid_metadata_blocks_all_associations(self):
        target = frame()
        target['metadata']['ESO DET OUT1 GAIN'] = 0
        result = assess_native_readiness(report([target]))
        self.assertEqual(result['exposures'], [])
        self.assertTrue(result['invalid_inputs'])

    def test_no_raw_targets_is_not_ready(self):
        result = assess_native_readiness(report([frame('processed', 'processed')]))
        self.assertFalse(result['raw_candidates_complete'])
        self.assertIn('No usable raw', ' '.join(result['blockers']))

    def test_unclassified_detector_frame_requires_review(self):
        result = assess_native_readiness(report([frame(), frame('unknown', 'review_geometry')]))
        self.assertEqual(result['exposures'], [])
        self.assertEqual(result['invalid_inputs'][0]['path'], '/data/unknown.fits')
        self.assertFalse(result['raw_candidates_complete'])

    def test_cli_returns_nonzero_with_explicit_native_blockers(self):
        from efospec.__main__ import main
        output = io.StringIO()
        with patch('efospec.__main__.inventory', return_value=report([frame()])), redirect_stdout(output):
            status = main(['native-readiness', '/data'])
        self.assertEqual(status, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result['calibration_policy'], 'native_only')
        self.assertFalse(result['reduction_ready'])
        self.assertFalse(result['native_execution_implemented'])
        self.assertTrue(result['blockers'])


if __name__ == '__main__':
    unittest.main()
