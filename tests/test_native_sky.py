import numpy as np
import pytest


def test_standard_flexure_is_measured_and_failures_retain_arc_grid():
    from efospec.native_sky import exposure_flexure, SkyValidationError
    # Same independent line gate for science and standards; only failure delivery differs.
    wave = np.broadcast_to(np.arange(5400.,6500.,2.)[:,None], (550,60)).copy()
    rng = np.random.default_rng(34)
    image = rng.normal(20.,1.,wave.shape)
    for rest, amplitude in [(5577.338,1200.),(6300.304,600.),(6363.776,200.)]:
        image += amplitude*np.exp(-.5*((wave-(rest-4.))/7.)**2)
    shift, qa = exposure_flexure(image,wave,required=False)
    assert shift == pytest.approx(4.,abs=.1) and qa['held_out_6363_pass']
    image -= 200.*np.exp(-.5*((wave-(6363.776-4.))/7.)**2)
    shift, qa = exposure_flexure(image,wave,required=False)
    assert shift == 0. and qa['applied_shift_angstrom'] is None
    assert qa['status']=='unvalidated' and qa['validation_error'] and qa['lines']
    with pytest.raises(SkyValidationError):exposure_flexure(image,wave,required=True)
    # Malformed input is a programming/data error, not an allowed arc-only fallback.
    with pytest.raises(ValueError):exposure_flexure(image[0],wave,required=False)


def sky_image(include_check=True):
    rng=np.random.default_rng(42)
    w=np.linspace(3600.,9300.,1024)
    wave=w[:,None]+np.linspace(-2,2,141)[None,:]
    image=np.full(wave.shape,120.)
    for rest,amp in [(5577.338,1200.),(6300.304,600.),(6363.776,200. if include_check else 0.)]:
        image+=amp*np.exp(-.5*((wave-(rest+6.))/7.5)**2)
    return image+rng.normal(0,8,image.shape),wave


def test_held_out_6363_fit_is_not_seeded_by_stronger_6300_wing():
    from efospec.native_sky import measure_flexure
    image,wave=sky_image()
    shift,qa=measure_flexure(image,wave)
    assert shift==pytest.approx(-6.,abs=.2)
    assert qa['held_out_6363_pass']
    assert abs(qa['held_out_6363_residual_angstrom'])<.3


def test_missing_independent_sky_line_stops_native_delivery():
    from efospec.native_sky import measure_flexure
    image,wave=sky_image(False)
    with pytest.raises(ValueError,match='6363'):measure_flexure(image,wave)


def test_high_snr_line_reports_centroid_failure_without_calling_it_weak(monkeypatch):
    from efospec import native_sky
    original = native_sky.curve_fit
    calls = []
    def uncertain_centroid(*args, **kwargs):
        parameters, covariance = original(*args, **kwargs)
        calls.append(1)
        if len(calls)==3:
            covariance[1,1] = 3.33**2
        return parameters, covariance
    monkeypatch.setattr(native_sky,'curve_fit',uncertain_centroid)
    image,wave = sky_image()
    with pytest.raises(native_sky.SkyValidationError,match='centroid uncertainty 3.33 A exceeds 1.50 A') as caught:
        native_sky.measure_flexure(image,wave)
    line = caught.value.diagnostics['lines'][-1]
    assert line['peak_snr']>5
    assert len(line['quality']['failed_gates'])==1
    assert 'weak' not in str(caught.value)
    assert caught.value.diagnostics['held_out_6363_pass'] is False


def test_sky_measurement_excludes_masked_detector_artifacts():
    from efospec.native_sky import measure_flexure
    image,wave=sky_image()
    good=np.ones(image.shape,bool)
    good[:,20:80]=False
    image[:,20:80]=1e9
    shift,qa=measure_flexure(image,wave,good_pixels=good)
    assert shift==pytest.approx(-6.,abs=.2)
    assert qa['held_out_6363_pass']
    with pytest.raises(ValueError,match='sky mask'):
        measure_flexure(image,wave,good_pixels=good[:-1])


def test_uniformly_illuminated_slit_is_not_misfit_as_a_gaussian():
    from scipy.special import erf
    from efospec.native_sky import measure_flexure
    rng=np.random.default_rng(74)
    wave=np.linspace(3600.,9300.,1024)[:,None]+np.linspace(-2,2,201)[None,:]
    width_pixels=1.5/.24; width=width_pixels*(9300-3600)/1023
    image=120.-.01*(wave-6000)
    for rest,amplitude in [(5577.338,250.),(6300.304,125.),(6363.776,42.)]:
        u=wave-(rest+5.)
        image+=amplitude*.5*(erf((u+width/2)/(np.sqrt(2)*3.5))-erf((u-width/2)/(np.sqrt(2)*3.5)))
    image+=rng.normal(0,8,image.shape)
    with pytest.raises(ValueError,match='fitted width'):
        measure_flexure(image,wave)
    shift,qa=measure_flexure(image,wave,slit_width_pixels=width_pixels)
    assert shift==pytest.approx(-5.,abs=.3)
    assert qa['held_out_6363_pass']
    assert abs(qa['held_out_6363_residual_angstrom'])<.5
    assert all(x['centroid_error_angstrom']<1.5 for x in qa['lines'])
    held_out=qa['lines'][2]
    assert held_out['fit_half_window_angstrom']>39
    assert held_out['neighbour_guard_air_angstrom'] is not None
    assert min(held_out['fit_samples']['wave_air'])>held_out['neighbour_guard_air_angstrom']
    assert len(held_out['fit_samples']['wave_air'])>=11
    # A missing held-out line must still stop delivery under the slit model.
    image[abs(wave-6368.776)<35]=120.
    with pytest.raises(ValueError,match='6363'):
        measure_flexure(image,wave,slit_width_pixels=width_pixels)


def test_displaced_held_out_line_does_not_validate_anchor_shift():
    from scipy.special import erf
    from efospec.native_sky import SkyValidationError, measure_flexure
    wave=np.linspace(3600.,9300.,1024)[:,None]+np.linspace(-2,2,201)[None,:]
    width_pixels=1.5/.24; width=width_pixels*(9300-3600)/1023
    image=np.full(wave.shape,120.)
    for rest,amplitude,shift in [(5577.338,250.,5.),(6300.304,125.,5.),(6363.776,90.,11.)]:
        u=wave-(rest+shift)
        image+=amplitude*.5*(erf((u+width/2)/(np.sqrt(2)*3.5))-erf((u-width/2)/(np.sqrt(2)*3.5)))
    image+=np.random.default_rng(43).normal(0,8,image.shape)
    with pytest.raises(SkyValidationError,match='residual'):
        measure_flexure(image,wave,slit_width_pixels=width_pixels)
