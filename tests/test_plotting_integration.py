"""Render a synthetic exposure through the real plotting/report entry point.

No observed data, IRAF products, or external reference downloads are needed.
LaTeX and the project plotting extras are required, as they are in CI.
"""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from astropy.io import fits
from PIL import Image

from epessto_plus.inventory import sha256
from epessto_plus.report import build_report
from test_report import Page


class PlottingIntegrationTests(unittest.TestCase):
    def test_standalone_exposure_renders_all_figures_and_portable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run/'products').mkdir()
            (run/'native').mkdir()
            product = run/'products/tSNtest_20241114_Gr13_Free_slit1.0_1_f.fits'
            wave = np.linspace(4000., 9000., 240)
            flux = 1e-16*(1.+0.2*np.sin(wave/400.))
            bands = np.stack([flux, flux, np.zeros_like(flux), flux/20.])[:, None, :]
            header = fits.Header({'CRVAL1': wave[0], 'CRPIX1': 1.,
                                  'CD1_1': wave[1]-wave[0],
                                  'DATE-OBS': '2024-11-15T01:00:00'})
            fits.PrimaryHDU(bands, header).writeto(product)
            np.savetxt(product.with_suffix('.asci'), np.column_stack([wave, flux]))

            x = np.arange(41)
            trace = 20.+0.5*np.sin(np.arange(len(wave))/50.)
            sky = np.full((len(wave), len(x)), 100.)
            signal = 20.*np.exp(-0.5*((x[None, :]-trace[:, None])/2.)**2)
            sky_mask = (abs(x[None, :]-trace[:, None]) > 8.) & (x > 0) & (x < 40)
            image = run/'native'/(product.name[:-7]+'_images.npz')
            np.savez(image, data=sky+signal, sky=sky,
                     waveair=np.broadcast_to(wave[:, None], sky.shape),
                     trace=trace, spatial_origin=100, sky_input_mask=sky_mask,
                     sky_mask_stage='global_sky_input_before_iterative_rejection')
            native = run/'native/spec1d_test.fits'
            table = fits.BinTableHDU.from_columns(
                [fits.Column(name='TRACE_SPAT', format='D', array=trace)], name='TARGET')
            table.header['BOX_RADIUS'] = 4.
            fits.HDUList([fits.PrimaryHDU(), table]).writeto(native)
            result = {'object': 'SNtest', 'grism': 'Gr13', 'exptime_s': 600.,
                      'date_obs': header['DATE-OBS'], 'product': str(product),
                      'native_spec1d': str(native), 'median_native_snr_4000_8500': 20.,
                      'target': {'selected': 'TARGET', 'association': 'synthetic_fixture'}}
            (run/'run.json').write_text(json.dumps({
                'input_dir': 'synthetic', 'pypeit_version': '1.14.0',
                'results': [result], 'errors': [], 'skipped': [], 'limitations': []}))
            before = {p: sha256(p) for p in [product, native, image]}

            status = build_report(run)
            log = (run/'report-generation.log').read_text()
            self.assertEqual(status['status'], 'complete', log)
            record_path, = (run/'style-preview').glob('FitSpectrum_*.json')
            record = json.loads(record_path.read_text())
            self.assertIsNone(record['legacy_comparison'])
            self.assertEqual(record['legend_labels'], ['PypeIt', r'Propagated $\pm 1\sigma$'])
            self.assertEqual(record['footer_text'], [])
            self.assertTrue(record['latex'])
            self.assertTrue(record['combined_upper_wavelength_ticklabels'])
            self.assertEqual(len(record['outputs']), 8)
            for name in record['outputs']:
                path = Path(name)
                if path.suffix == '.pdf':
                    self.assertTrue(path.read_bytes().startswith(b'%PDF-'))
                else:
                    with Image.open(path) as img:
                        self.assertEqual(img.format, 'JPEG')
                        self.assertEqual(img.info['dpi'], (300, 300))
                        self.assertGreater(img.width, 2000)
                        img.verify()
            page = Page((run/'index.html').read_text())
            self.assertEqual(len(page.images), 3)
            for link in page.links+page.images:
                if not link.startswith('#'):
                    self.assertTrue((run/link).is_file(), link)
            self.assertEqual(before, {p: sha256(p) for p in before})


if __name__ == '__main__':
    unittest.main()
