"""Check scientific binning and geometry, independently of figure styling."""
import unittest

import numpy as np

from efospec.spatial_profiles import wavelength_binned_profiles


class SpatialProfileTests(unittest.TestCase):
    def test_tilted_wavelength_bins_partition_native_counts_without_resampling(self):
        data = {'data': np.array([[1., 2.], [3., 4.], [5., 6.]]),
                'sky': np.ones((3, 2)),
                'waveair': np.array([[10., 12.], [20., 22.], [30., 32.]]),
                'trace': np.full(3, 0.5), 'spatial_origin': 100,
                'sky_input_mask': np.ones((3, 2), dtype=bool)}
        first, second = wavelength_binned_profiles(data, [10., 22., 32.], 0.5)
        np.testing.assert_array_equal(first['summed_electrons'], [2., 1.])
        np.testing.assert_array_equal(second['summed_electrons'], [4., 8.])
        np.testing.assert_array_equal(first['native_pixel_count'], [2, 1])
        np.testing.assert_array_equal(first['summed_electrons']+second['summed_electrons'],
                                      (data['data']-data['sky']).sum(axis=0))
        np.testing.assert_array_equal(first['spatial_pixel'], [100, 101])
        self.assertEqual(first['median_trace_pixel'], 100.5)

    def test_curved_aperture_and_background_keep_their_selection_fractions(self):
        data = {'data': np.ones((2, 4)), 'sky': np.zeros((2, 4)),
                'waveair': np.array([[10.]*4, [20.]*4]),
                'trace': np.array([1., 1.5]), 'spatial_origin': 100,
                'sky_input_mask': np.array([[1, 0, 0, 1], [1, 0, 1, 0]], dtype=bool)}
        p, = wavelength_binned_profiles(data, [10., 20.], 0.5)
        np.testing.assert_allclose(p['aperture_fraction'], [0., 0.75, 0.25, 0.])
        np.testing.assert_allclose(p['background_fraction'], [1., 0., 0.5, 0.5])
        self.assertEqual(p['median_trace_pixel'], 101.25)
        self.assertEqual(p['trace_pixel_range'], [101., 101.5])

    def test_missing_coverage_is_nan_and_negative_signal_is_preserved(self):
        data = {'data': np.array([[-3., np.nan], [-2., np.nan]]),
                'sky': np.zeros((2, 2)), 'waveair': np.array([[10., 10.], [20., 20.]]),
                'trace': np.zeros(2), 'spatial_origin': 0,
                'sky_input_mask': np.ones((2, 2), dtype=bool)}
        p, = wavelength_binned_profiles(data, [10., 20.], 0.5)
        self.assertEqual(p['summed_electrons'][0], -5.)
        self.assertTrue(np.isnan(p['summed_electrons'][1]))
        np.testing.assert_array_equal(p['background_fraction'], [1., 0.])
        with self.assertRaisesRegex(ValueError, 'no trace coverage'):
            wavelength_binned_profiles(data, [30., 40.], 0.5)

    def test_off_slit_columns_with_no_sky_model_do_not_enter_profile(self):
        data = {'data': np.array([[1000., 8., 1000.], [1000., 12., 1000.]]),
                'sky': np.array([[0., 3., 0.], [0., 4., 0.]]),
                'waveair': np.array([[10.]*3, [20.]*3]), 'trace': np.ones(2),
                'spatial_origin': 0, 'sky_input_mask': np.zeros((2, 3), dtype=bool),
                'onslit': np.array([[False, True, False]]*2)}
        p, = wavelength_binned_profiles(data, [10., 20.], 0.5)
        np.testing.assert_allclose(p['summed_electrons'], [np.nan, 13., np.nan])
        np.testing.assert_array_equal(p['native_pixel_count'], [0, 2, 0])


if __name__ == '__main__':
    unittest.main()
