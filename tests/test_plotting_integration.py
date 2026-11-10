"""Render a synthetic exposure through the real plotting/report entry point.

No observed data, IRAF products, or external reference downloads are needed.
LaTeX and the project plotting extras are required, as they are in CI.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
from astropy.io import fits
from PIL import Image

from efospec.inventory import sha256
from efospec.report import build_report
from test_report import Page


class PlottingIntegrationTests(unittest.TestCase):
    def test_same_target_two_slit_widths_render_distinct_portable_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)/'original'
            run.mkdir()
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
            signal += 10.*np.exp(-0.5*((x[None,:]-31.)/1.5)**2)
            signal[:,38] += 5000.  # Explicit display-only spike; keep the pixels.
            signal[:,1:5] -= 5000.  # Unsupported extrapolation must not set limits.
            sky_mask = (abs(x[None, :]-trace[:, None]) > 8.) & (x > 0) & (x < 40)
            sky_mask &= (x>=5)&(x<=35)
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
            result = {'object': 'SN_test', 'grism': 'Gr13', 'exptime_s': 600.,
                      'raw':'/synthetic/science.fits','raw_sha256':'synthetic-raw-hash',
                      'date_obs': header['DATE-OBS'], 'product': str(product),
                      'native_spec1d': str(native), 'median_native_snr_4000_8500': 20.,
                      'target': {'selected': 'TARGET', 'association': 'synthetic_fixture'}}
            # Decimal slit widths are part of the product name, not a file
            # extension. Both exposures must survive plot-metadata indexing.
            second_product = product.with_name(product.name.replace('slit1.0', 'slit1.5'))
            second_image = image.with_name(image.name.replace('slit1.0', 'slit1.5'))
            shutil.copyfile(product, second_product)
            shutil.copyfile(image, second_image)
            second_result = {**result, 'product': str(second_product),
                             'raw':'/synthetic/science-auto.fits',
                             'joint': {'profile_model': 'fixed_gaussian_shared_trace'}}
            display=run/'profile-display.json'
            display.write_text(json.dumps(dict(schema_version=1,display_only=True,
                coordinates='zero_based_legacy_trimmed_detector_pixels',exposures={
                    'science.fits':dict(raw_sha256='synthetic-raw-hash',ylim_exclude_intervals=[[138,139]],
                        limits_within_background_and_candidates=True,
                        profile_candidates=[dict(label='C2',search_interval=[128,135])])})))
            (run/'run.json').write_text(json.dumps({
                'input_dir': 'synthetic', 'pypeit_version': '1.14.0',
                'results': [result, second_result], 'errors': [], 'skipped': [], 'limitations': []}))
            before = {p.relative_to(run): sha256(p)
                      for p in [product, native, image, second_product, second_image, display]}
            manifest_before = (run/'run.json').read_bytes()
            moved = Path(directory)/'moved'
            run.rename(moved)
            self.assertFalse(run.exists())
            run = moved

            status = build_report(run)
            log = (run/'report-generation.log').read_text()
            self.assertEqual(status['status'], 'complete', log)
            records = [json.loads(p.read_text()) for p in (run/'style-preview').glob('FitSpectrum_*.json')]
            self.assertEqual(len(records), 2)
            self.assertEqual({Path(r['product']).name for r in records},
                             {product.name, second_product.name})
            record = next(r for r in records if Path(r['product']).name == product.name)
            self.assertIsNone(record['legacy_comparison'])
            self.assertEqual(record['legend_labels'], ['PypeIt', r'Propagated $\pm 1\sigma$'])
            joint_record = next(r for r in records if Path(r['product']).name == second_product.name)
            self.assertEqual(joint_record['legend_labels'],
                             ['Joint fixed profiles', r'Conditional $\pm 1\sigma$'])
            self.assertEqual(joint_record['spatial_profile_diagnostics']['display_settings'],{})
            for panel in joint_record['spatial_profile_diagnostics']['bins']:
                self.assertIn(138,panel['automatic_spike_excluded_spatial_pixels'])
                self.assertNotIn(131,panel['ylim_excluded_spatial_pixels'])
                self.assertGreater(panel['summed_electrons'][38]/1000.,panel['ylim'][1])
            self.assertEqual(record['footer_text'], [])
            self.assertTrue(record['latex'])
            self.assertTrue(record['combined_upper_wavelength_ticklabels'])
            self.assertEqual(record['trace_diagnostics']['image_display']['colormap'], 'gray_r')
            self.assertEqual(record['trace_diagnostics']['image_display']['center'], 0.)
            self.assertEqual(record['spatial_profile_diagnostics']['sky_model']['source'],
                             'saved extraction sky image; no new fit')
            for panel in record['spatial_profile_diagnostics']['bins']:
                np.testing.assert_allclose(np.asarray(panel['summed_data_electrons'],dtype=float)
                    -np.asarray(panel['summed_sky_electrons'],dtype=float),
                    np.asarray(panel['summed_electrons'],dtype=float),atol=1e-8)
                self.assertIn(138,panel['ylim_excluded_spatial_pixels'])
                self.assertGreater(panel['summed_electrons'][38]/1000.,panel['ylim'][1])
                self.assertLess(panel['summed_electrons'][2]/1000.,panel['ylim'][0])
                self.assertEqual(panel['background_interpolation_span'],[105.,135.])
                self.assertEqual(panel['candidate_annotations'][0]['label'],'C2')
                self.assertEqual(panel['candidate_annotations'][0]['spatial_pixel'],131.)
                self.assertLess(panel['summed_electrons'][31]/1000.,panel['ylim'][1])
            self.assertEqual(len(record['outputs']), 8)
            for name in [name for record in records for name in record['outputs']]:
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
            self.assertEqual(len(page.images), 6)
            for link in page.links+page.images:
                if not link.startswith('#'):
                    self.assertTrue((run/link).is_file(), link)
            self.assertEqual(before, {p: sha256(run/p) for p in before})
            self.assertEqual(manifest_before, (run/'run.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
