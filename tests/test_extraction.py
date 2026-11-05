"""Exercise the actual PypeIt kernel with known injected source fluxes."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np
from astropy.io import fits

from efospec.extraction import extract_spectra, select_sources
from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
from test_pypeit_adapter import write_raw


def synthetic_image(seed=11, ratio=1.):
    spectral, spatial = np.indices((160, 141))
    sky = 100.+40.*np.exp(-.5*((spectral-70.)/2.)**2)
    wave = 5000.+5.*spectral+.02*spatial
    signal = np.zeros_like(wave)
    truth = {}
    for identity, center, amplitude in [('primary', 48., 8000.), ('host', 98., 8000./ratio)]:
        flux = amplitude*(1.+.1*np.sin(np.arange(160)/30.))
        trace = center+.004*(np.arange(160)-80.)
        sigma = 4./2.354820045
        signal += flux[:, None]*np.exp(-.5*((spatial-trace[:, None])/sigma)**2)/(np.sqrt(2*np.pi)*sigma)
        truth[identity] = flux
    rng = np.random.default_rng(seed)
    data = rng.poisson(sky+signal)+rng.normal(0., 7.8, sky.shape)
    return data, wave, truth


class SourceSelectionTests(unittest.TestCase):
    def test_automatic_selection_rejects_absent_and_ambiguous_targets(self):
        sources = [SimpleNamespace(NAME='a', SPAT_PIXPOS=10.), SimpleNamespace(NAME='b', SPAT_PIXPOS=50.)]
        self.assertEqual(select_sources(sources, 11.), {'primary': 'a'})
        for found, position in [([], 10.), (sources, 100.), (sources, None),
                                ([sources[0], SimpleNamespace(NAME='c', SPAT_PIXPOS=15.)], 12.)]:
            with self.subTest(position=position), self.assertRaises(ValueError):
                select_sources(found, position)

    def test_missing_manual_source_cannot_silently_select_a_neighbour(self):
        sources = [SimpleNamespace(NAME='a', hand_extract_flag=True,
                                   hand_extract_spat=10., hand_extract_spec=50.)]
        with self.assertRaisesRegex(ValueError, 'not found uniquely'):
            select_sources(sources, manual=[{'id':'primary','spat':11.,'spec':50.}])

    def test_central_selection_uses_positive_peak_strength_not_distance_or_field_brightness(self):
        sources = [SimpleNamespace(NAME=name,SPAT_PIXPOS=x,smash_peakflux=peak,smash_snr=snr,sign=1)
                   for name,x,peak,snr in [('near',70.,20.,8.),('bright',78.,100.,20.),
                                           ('field',110.,1000.,80.),('sky',69.,-2.,20.)]]
        self.assertEqual(select_sources(sources,70.),{'primary':'bright'})
        sources[1].smash_peakflux=20.
        with self.assertRaises(ValueError):select_sources(sources,70.)
        with self.assertRaises(ValueError):select_sources([sources[3]],70.)


class ExtractionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        raw = write_raw(self.root, 'raw.fits')
        with fits.open(raw) as hdu:
            self.detector = EFOSpecEFOSC2Spectrograph().get_detector_par(1, hdu)
        (self.root/'QA/PNGs').mkdir(parents=True)

    def test_two_separated_sources_recover_injected_flux_and_requested_apertures(self):
        for seed, ratio in [(11, 1.), (22, 5.), (33, .2)]:
            with self.subTest(seed=seed, ratio=ratio):
                data, wave, truth = synthetic_image(seed, ratio)
                mask = np.zeros_like(data, dtype=bool)
                mask[:, 5:30] = True
                mask[:, 120:136] = True
                manual = [dict(id=identity, spec=80., spat=spat, fwhm=4., radius=7.)
                          for identity, spat in [('primary',48.), ('host',98.)]]
                result = extract_spectra(data, wave, self.detector, exposure_time=600.,
                    read_noise=7.8, output=self.root, basename=f'synthetic-{seed}',
                    manual=manual, sky_input_mask=mask)
                self.assertEqual(set(result['objects']), {'primary','host'})
                selected = result['selection']['sky_input_mask']
                self.assertTrue(selected.any())
                self.assertFalse(selected[~mask].any())
                for identity, objects in result['objects'].items():
                    obj = objects[0]
                    self.assertEqual(float(obj.BOX_RADIUS), 7.)
                    use = obj.OPT_MASK & (np.arange(160)>25) & (np.arange(160)<135)
                    self.assertGreater(use.sum(), 90)
                    bias = np.median(obj.OPT_COUNTS[use]/truth[identity][use])-1.
                    self.assertLess(abs(bias), .02, f'{identity}: bias={bias}')
                    normalized = (obj.OPT_COUNTS[use]-truth[identity][use])*np.sqrt(obj.OPT_COUNTS_IVAR[use])
                    self.assertLess(abs(np.median(normalized)), .6)
                    self.assertTrue(np.all(obj.OPT_COUNTS_IVAR[use]>0))
                self.assertNotEqual(result['objects']['primary'][0].NAME,
                                    result['objects']['host'][0].NAME)

    def test_automatic_kernel_keeps_neighbours_but_exports_selected_source(self):
        data, wave, truth = synthetic_image()
        result = extract_spectra(data, wave, self.detector, exposure_time=600.,
            read_noise=7.8, output=self.root, basename='automatic', target_position=48.)
        self.assertEqual(list(result['objects']), ['primary'])
        self.assertGreaterEqual(len(result['found']), 2)
        self.assertAlmostEqual(float(np.median(result['objects']['primary'][0].TRACE_SPAT)), 48., delta=.2)

    def test_bad_geometry_and_sky_masks_fail_before_extraction(self):
        data, wave, _ = synthetic_image()
        for changes in [{'waveair':wave[:-1]}, {'read_noise':-1.},
                        {'sky_input_mask':np.zeros_like(data,dtype=bool)}]:
            args=dict(data=data,waveair=wave,detector=self.detector,exposure_time=600.,
                      read_noise=7.8,output=self.root,basename='invalid',target_position=48.)
            args.update(changes)
            with self.assertRaises(ValueError):
                extract_spectra(**args)


def test_source_failure_keeps_positions_and_diagnostic_images(tmp_path):
    from efospec.extraction import SourceSelectionError
    import pytest
    data, wave, _ = synthetic_image()
    raw = write_raw(tmp_path, 'raw.fits')
    with fits.open(raw) as hdus:
        detector = EFOSpecEFOSC2Spectrograph().get_detector_par(1, hdus)
    (tmp_path/'QA/PNGs').mkdir(parents=True)
    with pytest.raises(SourceSelectionError) as caught:
        extract_spectra(data, wave, detector, exposure_time=600., read_noise=7.8,
                        output=tmp_path, basename='unresolved', target_position=73.)
    info = caught.value.diagnostics
    assert len(info['candidates']) == 2
    assert info['expected_spatial_pixel'] == 73.
    with np.load(info['diagnostic_file']) as saved:
        np.testing.assert_array_equal(saved['data'], data)
        np.testing.assert_array_equal(saved['waveair'], wave)
        assert len(saved['found_traces']) == 2
    assert not list(tmp_path.glob('products/*.fits'))
