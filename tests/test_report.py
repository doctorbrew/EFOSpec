"""Report contracts: portable assets, conditional availability and safe failures."""
from contextlib import redirect_stdout
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epessto_plus.inventory import sha256
from epessto_plus.report import build_report, write_report


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.images, self.ids = [], [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'img':
            self.images.append(attrs['src'])
        if 'id' in attrs:
            self.ids.append(attrs['id'])


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.run = Path(self.directory.name)
        (self.run/'products').mkdir()
        (self.run/'style-preview').mkdir()
        self.manifest = {'input_dir': '/old/location/2024-11-14', 'pypeit_version': '1.14.0',
                         'results': [], 'errors': [], 'skipped': [], 'limitations': ['No flats.']}
        self.add_exposure('a', 'SN<one>')

    def add_exposure(self, suffix, target):
        product = self.run/'products'/f'{suffix}_f.fits'
        product.write_bytes(suffix.encode())
        product.with_suffix('.asci').write_text('4000 1e-16\n')
        old_product = '/old/location/products/'+product.name
        self.manifest['results'].append({'object': target, 'product': old_product,
            'grism': 'Gr13', 'date_obs': '2024-11-15T01:02:03', 'exptime_s': 2700.,
            'median_native_snr_4000_8500': 17.8, 'target': {'association': 'UNVERIFIED_target_association'}})
        outputs = []
        for prefix in ['FitSpectrum_', 'FitTrace_', 'FitSpatialProfile_']:
            for extension in ['.jpg', '.pdf']:
                asset = self.run/'style-preview'/(prefix+suffix+extension)
                asset.write_bytes(b'fixture')
                outputs.append('/old/location/style-preview/'+asset.name)
        (self.run/'style-preview'/f'FitSpectrum_{suffix}.json').write_text(json.dumps({
            'outputs': outputs, 'input_sha256': {old_product: sha256(product)}}))
        (self.run/'run.json').write_text(json.dumps(self.manifest))

    def test_table_first_three_plots_portable_links_and_escaped_metadata(self):
        result = write_report(self.run)
        self.assertEqual(result['status'], 'complete')
        html = (self.run/'index.html').read_text()
        self.assertLess(html.index('id="observations"'), html.index('class="target"'))
        self.assertIn('SN&lt;one&gt;', html)
        self.assertNotIn('SN<one>', html)
        self.assertNotIn('Source selection', html)
        self.assertIn('Target identity is unverified', html)
        self.assertNotIn('/old/location', html)
        page = Page(html)
        self.assertEqual(len(page.images), 3)
        self.assertTrue(any('FitTrace_' in p for p in page.images))
        for link in page.links+page.images:
            if link.startswith('#'):
                self.assertIn(link[1:], page.ids)
            else:
                self.assertTrue((self.run/link).is_file(), link)

    def test_same_target_exposures_keep_distinct_anchors_and_all_six_plots(self):
        self.add_exposure('b', 'SN<one>')
        write_report(self.run)
        page = Page((self.run/'index.html').read_text())
        self.assertEqual(len(page.images), 6)
        self.assertEqual(len(page.ids), len(set(page.ids)))

    def test_missing_image_is_explicit_and_has_no_broken_image_link(self):
        (self.run/'style-preview/FitTrace_a.jpg').unlink()
        status = write_report(self.run)
        self.assertEqual(status['status'], 'incomplete')
        self.assertEqual(status['missing_figures'], [{'product': 'a_f.fits', 'figure': '2D trace'}])
        self.assertEqual(len(Page((self.run/'index.html').read_text()).images), 2)

    def test_changed_science_product_cannot_reuse_stale_figures(self):
        (self.run/'products/a_f.fits').write_bytes(b'new reduction')
        status = write_report(self.run)
        self.assertEqual(len(status['missing_figures']), 3)

    def test_renderer_failure_keeps_products_and_writes_honest_html(self):
        product = self.run/'products/a_f.fits'
        before = sha256(product)
        with patch('epessto_plus.report.subprocess.run') as process:
            process.return_value.returncode = 1
            status = build_report(self.run, plot_python='/chosen/python')
            self.assertEqual(process.call_args.args[0][0], '/chosen/python')
        self.assertEqual(status['status'], 'incomplete')
        self.assertIn('exited with status 1', status['generation_error'])
        self.assertEqual(sha256(product), before)
        self.assertTrue((self.run/'index.html').is_file())

    def test_html_only_does_not_start_a_renderer(self):
        with patch('epessto_plus.report.subprocess.run') as process:
            self.assertEqual(build_report(self.run, render_plots=False)['status'], 'complete')
            process.assert_not_called()

    def test_no_successful_exposures_still_lists_failure_and_skip(self):
        self.manifest['results'] = []
        self.manifest['errors'] = [{'object': 'SNfailed', 'error': 'No source'}]
        self.manifest['skipped'] = [{'path': 'Gr16.fits', 'reason': 'Unsupported grism'}]
        (self.run/'run.json').write_text(json.dumps(self.manifest))
        with patch('epessto_plus.report.subprocess.run') as process:
            build_report(self.run)
            process.assert_not_called()
        html = (self.run/'index.html').read_text()
        self.assertIn('SNfailed', html)
        self.assertIn('Unsupported grism', html)

    def test_cli_passes_report_options_and_surfaces_incomplete_report(self):
        from epessto_plus.__main__ import main
        result = {'output_dir': str(self.run), 'results': [], 'errors': [], 'skipped': [],
                  'report': {'status': 'incomplete'}}
        with patch('epessto_plus.rapid.reduce_night', return_value=result) as reduce, redirect_stdout(io.StringIO()):
            status = main(['reduce-rapid', '/data', '--output', str(self.run),
                           '--plot-python', '/chosen/python'])
        self.assertEqual(status, 1)
        self.assertEqual(reduce.call_args.kwargs['plot_python'], '/chosen/python')
        self.assertFalse(reduce.call_args.kwargs['skip_report'])


if __name__ == '__main__':
    unittest.main()
