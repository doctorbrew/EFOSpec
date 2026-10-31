"""Physical unit, wavelength-sign, masking, and variance regression tests."""
import tempfile
import unittest
import importlib.util
from pathlib import Path

import numpy as np
from astropy.io import fits

HAS_SCIPY = importlib.util.find_spec('scipy') is not None
if HAS_SCIPY:
    from efospec.archive_calibration import rebin_density, sensitivity_factor, sky_flexure


@unittest.skipUnless(HAS_SCIPY, 'rapid calibration tests require SciPy in the PypeIt environment')
class ArchiveCalibrationTests(unittest.TestCase):
    def test_rebin_conserves_integrated_flux_and_propagates_variance(self):
        # Four bins of width 1 become two bins of width 2, with matching edges.
        flux, var, valid = rebin_density(np.array([1.,2.,3.,4.]),
            np.array([2.,4.,6.,8.]), np.full(4,4.), np.ones(4,dtype=bool), np.array([1.5,3.5]))
        np.testing.assert_allclose(flux,[3.,7.])
        self.assertAlmostEqual(float(np.sum(flux)*2),20.)
        np.testing.assert_allclose(var,[2.,2.])
        self.assertTrue(valid.all())

    def test_bad_input_and_partial_coverage_stay_invalid(self):
        flux,var,good=rebin_density(np.array([1.,2.,3.,4.]),np.ones(4),np.ones(4),
                                   [True,False,True,True],np.array([1.5,3.5,5.5]))
        np.testing.assert_array_equal(good,[False,True,False])
        self.assertTrue(np.isnan(flux[[0,2]]).all())
        self.assertTrue(np.isnan(var[[0,2]]).all())

    def test_nonmonotonic_grid_rejected(self):
        with self.assertRaisesRegex(ValueError,'increasing'):
            rebin_density([1.,3.,2.],[1.]*3,[1.]*3,[True]*3,[1.,2.])

    def test_sensitivity_units_include_gain_time_dispersion_and_extinction(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            # S=25 means response 10^10 ADU/s/A per physical flux unit.
            h=fits.Header({'CRVAL1':5000.,'CRPIX1':1.,'CD1_1':2.})
            fits.writeto(path/'s.fits',np.full(3,25.),h)
            np.savetxt(path/'ext.dat',[[4900.,0.2],[5100.,0.2]])
            wave=np.array([4998.,5000.,5002.,5004.,5006.])
            factor,good=sensitivity_factor(wave,path/'s.fits',path/'ext.dat',100.,1.5,2.)
            expected=10**(0.4*1.5*0.2)/(2*100*2*1e10)
            np.testing.assert_allclose(factor,expected)
            np.testing.assert_array_equal(good,[False,True,True,True,False])

    def test_flexure_sign_and_independent_line_check(self):
        wave=np.linspace(5200.,6700.,501)
        spectrum=np.full_like(wave,30.)
        shift=37.
        for rest,amp in [(5577.338,500.),(6300.304,400.),(6363.776,150.)]:
            spectrum+=amp*np.exp(-0.5*((wave-(rest-shift))/6.)**2)
        data=np.repeat(spectrum[:,None],81,axis=1)
        data+=np.random.default_rng(48).normal(0,0.2,data.shape)
        measured,qa=sky_flexure(data,np.repeat(wave[:,None],81,axis=1))
        # Sampling is 3 A/pixel; require recovery within 1/30 pixel.
        self.assertAlmostEqual(measured,shift,delta=0.1)
        self.assertTrue(qa['held_out_6363_pass'])
        self.assertLess(abs(qa['held_out_6363_residual_angstrom']),0.1)

    def test_flat_sky_cannot_establish_flexure(self):
        wave=np.repeat(np.linspace(5200.,6700.,501)[:,None],81,axis=1)
        data=np.random.default_rng(7).normal(30.,2.,wave.shape)
        with self.assertRaisesRegex(ValueError,'cannot establish'):
            sky_flexure(data,wave)


if __name__=='__main__':
    unittest.main()
