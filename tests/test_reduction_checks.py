"""Scientific checks remain inspectable even when no spectrum can be delivered."""
import json
import numpy as np
import pytest

from test_flexure_regressions import sky_image
from test_revisions import saved_exposure


def test_failed_sky_check_saves_curves_without_accepting_correlation(tmp_path, monkeypatch):
    tmp_path=tmp_path/'check'
    from efospec import reduction_checks as checks
    from efospec.archive_calibration import SkyFlexureError
    monkeypatch.setattr(checks, 'correlate_sky', lambda *a, **kw: ({'status':'measured',
        'shift_angstrom':12., 'applied':False}, {}))
    image, wave = sky_image(12., offsets=(12., 18., 18.))
    with pytest.raises(SkyFlexureError) as caught:
        checks.check_flexure(image, wave, tmp_path, {'raw':'raw.fits'})
    record=json.loads((tmp_path/'check.json').read_text())
    assert record['status']=='failed' and not record['correlation']['applied']
    assert 'anchor_disagreement' in record['line_check']['failed_gates']
    assert caught.value.diagnostics['review_file']==str(tmp_path/'check.json')
    with np.load(tmp_path/'curves.npz') as saved:
        assert {'sky','waveair','red_model','green_model'} <= set(saved.files)
        assert np.isfinite(saved['red_model']).all()


def test_optional_correlation_failure_is_explicit_and_does_not_change_shift(tmp_path, monkeypatch):
    tmp_path=tmp_path/'check'
    from efospec import reduction_checks as checks
    def unavailable(*args,**kwargs):raise OSError('template unavailable')
    monkeypatch.setattr(checks,'correlate_sky',unavailable)
    shift, qa=checks.check_flexure(*sky_image(-20.),tmp_path,{'raw':'raw.fits'})
    assert shift==pytest.approx(-20.,abs=.1)
    record=json.loads((tmp_path/'check.json').read_text())
    assert record['correlation']['status']=='unavailable'
    assert record['correlation']['error']=='template unavailable'
    assert qa['held_out_6363_pass']


@pytest.mark.parametrize('shift',[-12.,12.])
def test_pypeit_correlation_sign_units_and_known_shift(shift):
    from efospec.reduction_checks import correlate_sky
    # Explicit synthetic physical template avoids network access in tests.
    wave=np.linspace(5300.,6500.,601)
    template_wave=np.linspace(5200.,6600.,2801)
    def spectrum(w, offset, width):
        f=np.full(w.shape,10.)
        for rest,amplitude in [(5577.338,500.),(5890.,100.),(6300.304,400.),(6363.776,133.)]:
            f+=amplitude*np.exp(-.5*((w-(rest-offset))/width)**2)
        return f
    record, arrays=correlate_sky(wave,spectrum(wave,shift,7.),
        template=(template_wave,spectrum(template_wave,0.,2.),2.35482*2./.5,'synthetic-air'),
        fwhm_angstrom=2.35482*7.)
    assert record['status']=='measured' and not record['applied']
    assert record['shift_angstrom']==pytest.approx(shift,abs=.3)
    assert len(arrays['correlation_lags'])==7


def test_red_correlation_never_claims_a_validated_correction(tmp_path,monkeypatch):
    from efospec import reduction_checks as checks
    monkeypatch.setattr(checks,'correlate_sky',lambda *args,**kwargs:
        ({'status':'measured','applied':False,'shift_angstrom':-5.},{}))
    data,wave=sky_image(0.)
    record=checks.check_red_sky(data,wave,tmp_path/'red',{'raw':'red.fits'})
    assert record['status']=='unvalidated'
    assert record['applied_shift_angstrom'] is None
    assert record['line_check']['failed_gates']==['red_sky_validation_required']


def test_check_directory_cannot_be_overwritten(tmp_path,monkeypatch):
    from efospec import reduction_checks as checks
    with pytest.raises(FileExistsError):
        checks.check_flexure(*sky_image(0.),tmp_path,{'raw':'raw.fits'})


def test_plots_reject_changed_diagnostic_curves(tmp_path,monkeypatch):
    from efospec import reduction_checks as checks
    from efospec.check_plots import plot_check
    monkeypatch.setattr(checks,'correlate_sky',lambda *a,**kw:({'status':'unavailable'},{}))
    checks.check_flexure(*sky_image(0.),tmp_path/'check',{'raw':'raw.fits'})
    (tmp_path/'check/curves.npz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='arrays changed'):
        plot_check(tmp_path/'check/check.json')


def test_background_stop_retains_source_geometry_for_review(saved_exposure,tmp_path,monkeypatch):
    from efospec.revisions import Exposure
    from efospec.extraction import extract_spectra
    from efospec import local_sky
    from astropy.io import fits
    run,reference,_=saved_exposure
    context=Exposure(run,'test_f.fits',reference).context
    def no_clean_bands(*args,**kwargs):
        raise local_sky.BackgroundSupportError('No clean two-sided bands')
    monkeypatch.setattr(local_sky,'nearby_mask',no_clean_bands)
    output=tmp_path/'failed';(output/'QA/PNGs').mkdir(parents=True)
    with pytest.raises(local_sky.BackgroundSupportError) as caught:
        extract_spectra(context.data,context.waveair,context.detector,
            exposure_time=1200.,read_noise=7.8,output=output,basename='test',
            target_position=48.,bounded_background=True)
    info=caught.value.diagnostics
    assert info['candidates'] and info['expected_spatial_pixel']==48.
    with np.load(info['diagnostic_file']) as saved:
        np.testing.assert_array_equal(saved['data'],context.data)
        assert len(saved['found_traces'])==len(info['candidates'])
    assert fits.getheader(info['native_spec2d'])['QCSTAGE']=='background_support_failed'
