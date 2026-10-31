import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ci_metrics',
    Path(__file__).resolve().parents[1]/'.github/scripts/parse_ci_metrics.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class MetricsTests(unittest.TestCase):
    def prepare(self, junit, coverage='<coverage line-rate="0.75"/>', code=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if junit is not None:
                (root/'junit.xml').write_text(junit)
            (root/'coverage.xml').write_text(coverage)
            return metrics.prepare(root/'junit.xml', root/'coverage.xml', code)

    def test_passing_nested_suites_are_not_double_counted(self):
        result = self.prepare('<testsuites tests="2"><testsuite tests="2"><testcase/><testcase/></testsuite></testsuites>')
        self.assertEqual(result['tests.json']['message'], '2 passed')
        self.assertEqual(result['coverage.json']['message'], '75.0%')

    def test_failed_test_cannot_publish_green_or_complete_coverage(self):
        result = self.prepare('<testsuite tests="2" failures="1"><testcase/><testcase><failure/></testcase></testsuite>', code=1)
        self.assertEqual(result['tests.json']['color'], 'red')
        self.assertEqual(result['coverage.json']['message'], 'unavailable')

    def test_collection_error_or_missing_report_is_not_zero_tests_passed(self):
        for junit in [None, '<invalid', '<testsuite tests="0" errors="1"/>']:
            with self.subTest(junit=junit):
                result = self.prepare(junit, code=2)
                self.assertEqual(result['tests.json']['color'], 'red')
                self.assertNotEqual(result['tests.json']['message'], '0 passed')

    def test_all_skipped_and_empty_suites_are_not_green(self):
        for junit in ['<testsuite tests="0"/>', '<testsuite tests="1" skipped="1"><testcase><skipped/></testcase></testsuite>']:
            result = self.prepare(junit)
            self.assertEqual(result['tests.json']['color'], 'yellow')
            self.assertEqual(result['coverage.json']['message'], 'unavailable')

    def test_nonzero_exit_overrides_passing_report(self):
        result = self.prepare('<testsuite tests="1"><testcase/></testsuite>', code=1)
        self.assertEqual(result['tests.json']['color'], 'red')
        self.assertEqual(result['coverage.json']['message'], 'unavailable')

    def test_invalid_coverage_is_never_a_percentage(self):
        for rate in ['NaN', 'inf', '-1', '1.2', 'not-a-number']:
            result = self.prepare('<testsuite tests="1"><testcase/></testsuite>', f'<coverage line-rate="{rate}"/>')
            self.assertEqual(result['coverage.json']['message'], 'unavailable')

    def test_inconsistent_declared_counts_are_unavailable(self):
        result = self.prepare('<testsuite tests="2"><testcase/></testsuite>')
        self.assertEqual(result['tests.json']['message'], 'report unavailable')


if __name__ == '__main__':
    unittest.main()
