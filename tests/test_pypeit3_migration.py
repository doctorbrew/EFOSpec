"""Observable compatibility boundaries for the PypeIt 3 runtime."""
import json
import numpy as np
import pytest


def test_old_calibration_group_is_rejected_before_loading_fits(tmp_path):
    from efospec.native_calibrations import load_calibrations
    (tmp_path/'calibration.json').write_text(json.dumps(dict(
        status='experimental_complete', mode='native_raw_only', pypeit_version='1.14.0')))
    with pytest.raises(ValueError, match='rebuild.*raw|incompatible PypeIt'):
        load_calibrations(tmp_path)


@pytest.mark.parametrize('delta', [-10., 10.])
def test_correlation_recovers_coordinate_shift_with_fixed_sample_support(delta):
    from efospec.reduction_checks import correlate_sky
    wave=np.linspace(5300.,6500.,601)
    tw=np.linspace(5150.,6650.,3001)
    def sky(w, sigma):
        return 10.+sum(a*np.exp(-.5*((w-rest)/sigma)**2)
            for rest,a in [(5577.338,500.),(5890.,100.),(6300.304,400.),(6363.776,133.)])
    kwargs=dict(template=(tw,sky(tw,2.),2.35482*2./.5,'synthetic-air'),
                fwhm_angstrom=2.35482*7., wavelength_range=(5200.,6600.))
    initial,_=correlate_sky(wave,sky(wave,7.),**kwargs)
    shifted,_=correlate_sky(wave+delta,sky(wave,7.),**kwargs)
    assert shifted['pypeit_version']=='3.0.0'
    assert shifted['shift_angstrom']-initial['shift_angstrom']==pytest.approx(-delta,abs=.4)
    assert not shifted['applied']


def test_native_correlation_is_explicit_and_never_promotes_its_candidate():
    from efospec.reduction_checks import correlate_sky
    wave=np.linspace(5300.,6500.,601)
    tw=np.linspace(5150.,6650.,3001)
    def sky(w,sigma):
        return 10.+sum(a*np.exp(-.5*((w-rest)/sigma)**2)
            for rest,a in [(5577.338,500.),(5890.,100.),(6300.304,400.),(6363.776,133.)])
    result,_=correlate_sky(wave,sky(wave,7.),
        template=(tw,sky(tw,2.),2.35482*2./.5,'synthetic-air'),
        fwhm_angstrom=2.35482*7.,continuum_method='native')
    # Native percentile clipping is biased on this sparse-line fixture. Its
    # candidate remains diagnostic; no scientific acceptance is inferred here.
    assert result['method']=='PypeIt.spec_flex_shift'
    assert result['continuum_method']=='native'
    assert not result['applied']


def test_native_extraction_renders_qa_with_mandatory_latex(tmp_path):
    import matplotlib
    from astropy.io import fits
    from efospec.figure_style import HOUSE_RC
    from efospec.extraction import extract_spectra
    from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
    from test_extraction import synthetic_image
    from test_pypeit_adapter import write_raw
    raw=write_raw(tmp_path,'raw.fits')
    with fits.open(raw) as hdus:
        detector=EFOSpecEFOSC2Spectrograph().get_detector_par(1,hdus)
    data,wave,truth=synthetic_image()
    with matplotlib.rc_context(HOUSE_RC):
        before=matplotlib.rcParams['text.latex.preamble']
        result=extract_spectra(data,wave,detector,exposure_time=600.,read_noise=7.8,
            output=tmp_path,basename='latex-qa',target_position=48.)
        assert matplotlib.rcParams['text.usetex']
        assert matplotlib.rcParams['text.latex.preamble']==before
    obj=result['objects']['primary'][0]
    use=obj.OPT_MASK & (np.arange(160)>25) & (np.arange(160)<135)
    assert np.median(obj.OPT_COUNTS[use]/truth['primary'][use])==pytest.approx(1.,abs=.02)
    assert list((tmp_path/'QA').rglob('*.png'))


def test_historical_native_reidentification_template_is_rejected_before_fits(tmp_path):
    from efospec.native_calibration import load_native_template
    setup={'grism':'Gr13'}
    (tmp_path/'calibration.json').write_text(json.dumps(dict(
        status='calibrations_built',setup=setup,pypeit_version='1.14.0')))
    with pytest.raises(ValueError,match='incompatible PypeIt'):
        load_native_template(tmp_path,setup)


def test_historical_native_validation_run_is_rejected_before_fits(tmp_path):
    from efospec.native_validation import validate_native_run
    run=tmp_path/'historical';run.mkdir()
    (run/'run.json').write_text(json.dumps(dict(status='complete',pypeit_version='1.14.0')))
    with pytest.raises(ValueError,match='incompatible PypeIt'):
        validate_native_run(run,tmp_path/'validation')
