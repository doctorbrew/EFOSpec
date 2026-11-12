from pathlib import Path
import numpy as np
import pytest

from efospec.telluric_model import correct_flux,pixel_edges
from efospec.telluric_night import read_config


def test_config_checks_real_pypeit_names_and_resolution_units(tmp_path):
    path=tmp_path/'bad.par'
    path.write_text('[telluric]\nmethod = pca\nresln = 10.\nobjmodel = poly\n')
    with pytest.raises(ValueError,match='recognized'):read_config(path)
    valid=Path(__file__).resolve().parents[1]/'configs/telluric_efosc.par'
    config=read_config(valid)
    assert config['tell_npca']==2 and config['resln_guess']==500.
    path.write_text(valid.read_text().replace('500.','10.'))
    with pytest.raises(ValueError,match='resolving power'):read_config(path)


def test_uncertainty_propagation_negative_flux_and_deep_absorption():
    flux=np.array([10.,-2.,3.,4.]);var=np.ones(4)
    t=np.array([.5,.5,.1,.5]);tv=np.array([.01,.01,.01,.01])
    f,v,g,stat,model=correct_flux(flux,var,t,tv,[True,True,True,False])
    np.testing.assert_array_equal(g,[True,True,False,False])
    np.testing.assert_allclose(f[:2],[20.,-4.])
    np.testing.assert_allclose(stat[:2],4.)
    np.testing.assert_allclose(model[:2],[16.,.64])
    np.testing.assert_allclose(v[:2],[20.,4.64])
    assert np.isnan(f[2:]).all()


def test_wavelength_edges_reject_invalid_grids():
    np.testing.assert_allclose(pixel_edges([1.,2.,3.]),[.5,1.5,2.5,3.5])
    with pytest.raises(ValueError):pixel_edges([2.,1.])
    with pytest.raises(ValueError):pixel_edges([1.,np.nan])


def test_real_pypeit_atmosphere_recovers_synthetic_transmission():
    # Integration uses the same public model as the real nightly run. No data fitting
    # fixture is substituted. Model-file availability is explicit for offline CI.
    from efospec.telluric_model import Atmosphere,fit_standard,predict
    from pypeit.pkg import cache
    if not cache.search_cache('TellPCA_3000_26000_R10000.fits'):
        pytest.skip('PypeIt atmospheric PCA must be installed for this integration test')
    a=Atmosphere(npca=2)
    wave=np.arange(6000.,9000.,5.)
    truth=np.array([-15.,-8.,430.,4.])
    transmission=a.evaluate(wave,truth)
    rng=np.random.default_rng(51);sigma=np.full(len(wave),.01)
    ratio=transmission*np.exp(.03+.02*(wave-7500)/1500)+rng.normal(0,sigma)
    fit,arrays=fit_standard(a,wave,ratio,sigma,np.ones(wave.size,bool),resolution=500.)
    predicted,variance=predict(a,arrays['wave'],fit)
    strong=transmission<.95
    assert np.sqrt(np.mean((predicted[strong]-transmission[strong])**2))<.015
    assert abs(fit['shift_vacuum_angstrom']-truth[-1])<1.
    assert np.isfinite(variance).all() and np.all(variance>=0)
    assert np.mean(abs(predicted[strong]-transmission[strong])<3*np.sqrt(variance[strong]))>.9
    # Slant-column scaling belongs before convolution; saturated lines do not
    # follow a power of the already blurred transmission.
    scaled=a.evaluate(wave,truth,airmass_scale=1.5)
    assert np.max(abs(scaled-transmission**1.5))>.005
    assert np.median(scaled[strong])<np.median(transmission[strong])
    # A science offset replaces the standard offset, not its marginal PCA errors.
    _,_,details=predict(a,arrays['wave'],fit,shift=0.,shift_sigma=3.,return_details=True)
    np.testing.assert_allclose(details['covariance'][-1,:-1],0.)
    assert details['covariance'][-1,-1]==9.


def test_independent_transfer_rejects_changed_atmosphere(monkeypatch):
    from types import SimpleNamespace
    from astropy import units as u
    from pypeit.core.wave import airtovac
    import efospec.telluric_night as night
    from efospec.telluric_model import BANDS
    air=np.arange(6000.,8900.,4.);wave=airtovac(air*u.AA).value
    t=np.ones(wave.size)
    for lo,hi in BANDS.values():
        t-=.35*np.exp(-.5*((air-(lo+hi)/2)/25.)**2)
    monkeypatch.setattr(night,'predict',lambda a,w,r,**kw:(t,np.zeros_like(t)))
    a=SimpleNamespace(lower=6000.,upper=9000.)
    data=dict(wave=wave,ratio=t.copy(),sigma=np.full(wave.size,.01),valid=np.ones(wave.size,bool))
    good,arrays=night.validate_transfer(a,{},data,airmass_scale=1.,return_arrays=True)
    assert all(b['passed'] for b in good.values())
    np.testing.assert_allclose(arrays['variance'],arrays['statistical_variance']+arrays['model_variance'])
    np.testing.assert_allclose(arrays['corrected'][arrays['valid']],1.,atol=.01)
    continuum=night.test_continuum(a,data)
    lo,hi=BANDS['O2_A'];band=(air>lo)&(air<hi)
    data['ratio'][band]=1.  # A fit to this test exposure could hide the failed transfer.
    bad=night.validate_transfer(a,{},data,airmass_scale=1.)
    assert not bad['O2_A']['passed'] and bad['O2_B']['passed']
    np.testing.assert_array_equal(continuum,night.test_continuum(a,data))


@pytest.fixture
def science_transfer(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from astropy.io import fits
    from efospec.inventory import inspect_file,sha256
    import efospec.telluric_night as night
    raw=tmp_path/'raw.fits'
    h=fits.Header({'INSTRUME':'EFOSC','OBJECT':'synthetic science','DATE-OBS':'2026-10-29T03:00:00',
        'MJD-OBS':61342.,'EXPTIME':900.})
    for key,value in {'TEL AIRM START':1.15,'INS GRIS1 NAME':'Gr13','INS FILT1 NAME':'Free',
                      'INS SLIT1 NAME':'slit1.0','DET WIN1 BINX':2,'DET WIN1 BINY':2,
                      'DET READ SPEED':'fastL','DPR TYPE':'OBJECT','DPR CATG':'SCIENCE',
                      'DPR TECH':'SPECTRUM'}.items():h['HIERARCH ESO '+key]=value
    fits.PrimaryHDU(np.zeros((1030,1030),np.int16),h).writeto(raw)
    frame=inspect_file(raw)
    source=tmp_path/'science.fits';wave=np.arange(6000.,9000.,5.)
    data=np.ones((4,1,len(wave)));data[:3]*=10.;data[0,0,320]=-2.
    valid=np.ones((1,len(wave)),np.uint8);valid[0,325]=0
    h=fits.Header({'CRVAL1':6000.,'CD1_1':5.,'CRPIX1':1.,'WAVEMED':'air','BUNIT':'erg/cm2/s/Angstrom'})
    fits.HDUList([fits.PrimaryHDU(data,h),fits.ImageHDU(valid,name='VALID')]).writeto(source,checksum=True)
    item=dict(role='science',raw=str(raw),raw_sha256=sha256(raw),product=str(source),
              sky_flexure=dict(held_out_6363_pass=True))
    train=dict(raw='standard',fit_id=1,mjd=61342.-.02,airmass=1.1,resolution=500.)
    checks=dict(training_raw='standard',delta_airmass=.2,test_airmass=1.3,
                bands={b:dict(passed=b=='O2_A',fractional_variance_floor=.001) for b in night.BANDS})
    report=dict(fits=[train],transfers=[checks],products=[],skipped=[])
    atmosphere=SimpleNamespace(lower=6000.,upper=9000.,sha256='abcdef'*11)
    def model(a,w,r,**kwargs):
        return np.full(w.size,.8),np.full(w.size,.002),dict(theta=np.ones(4),
            covariance=np.eye(4),jacobian=np.full((w.size,4),.01))
    monkeypatch.setattr(night,'predict',model)
    return dict(run={'results':[item]},report=report,entries={'standard':{'frame':frame}},
                atmosphere=atmosphere,output=tmp_path,protected={})


def test_science_fits_preserves_original_masks_bands_and_propagates_variance(science_transfer):
    from astropy.io import fits
    from efospec.inventory import sha256
    from efospec.telluric_night import apply_products,BANDS
    kw=science_transfer;source=Path(kw['run']['results'][0]['product']);before=sha256(source)
    apply_products(**kw)
    product=kw['report']['products'][0]
    assert product['airmass_transfer_validated'] and sha256(source)==before
    assert Path(product['uncorrected_product']).read_bytes()==source.read_bytes()
    assert Path(product['ascii']).exists() and Path(product['uncorrected_ascii']).exists()
    with fits.open(product['product']) as out,fits.open(source) as original:
        assert all(h.verify_checksum()==1 and h.verify_datasum()==1 for h in out)
        np.testing.assert_array_equal(out['UNCORRECTED'].data,original[0].data)
        applied=out['TELLURIC'].data['APPLIED'];wave=out['TELLURIC'].data['WAVE_AIR']
        affected=np.zeros(wave.size,bool)
        for lo,hi in BANDS.values():affected|=(wave>=lo)&(wave<=hi)
        np.testing.assert_array_equal(out[0].data[:,:,~affected],original[0].data[:,:,~affected])
        np.testing.assert_array_equal(out[0].data[2],original[0].data[2])
        assert np.isnan(out[0].data[0,0,affected&~applied]).all()
        assert np.all(out['VALID'].data[0,affected&~applied]==0)
        assert out[0].data[0,0,320]<0  # Negative science samples remain valid.
        np.testing.assert_allclose(out[0].data[0,0,applied],original[0].data[0,0,applied]/.8)
        expected=1/.8**2+original[0].data[0,0,applied]**2*(.002+.8**2*.001)/.8**4
        np.testing.assert_allclose(out[0].data[3,0,applied]**2,expected)
        assert out['TELL_PARAM_COV'].data.shape==(4,4)
        assert out['TELL_JACOBIAN'].data.shape==(wave.size,4)


def test_airmass_extrapolation_requires_explicit_review_option(science_transfer):
    from astropy.io import fits
    from efospec.telluric_night import apply_products
    kw=science_transfer;kw['report']['transfers'][0].update(delta_airmass=.01,test_airmass=1.11)
    apply_products(**kw)
    assert not kw['report']['products']
    assert 'airmass' in kw['report']['skipped'][0]['reason']
    kw['output']=kw['output']/'review';kw['output'].mkdir()
    apply_products(**kw,review_extrapolation=True)
    product=kw['report']['products'][0]
    assert product['status']=='review_required_transfer'
    assert not product['airmass_transfer_validated']
    with fits.open(product['product']) as out:assert out[0].header['TELVALID']=='REVIEW'


def test_failed_validation_is_not_silently_omitted(science_transfer):
    from efospec.telluric_night import apply_products
    kw=science_transfer
    kw['report']['transfers'].append(dict(training_raw='standard',error='missing independent continuum'))
    apply_products(**kw)
    assert not kw['report']['products']
    assert kw['report']['skipped'][0]['reason']=='No independently passing band'


def test_science_raw_tampering_blocks_correction(science_transfer):
    from efospec.telluric_night import apply_products
    kw=science_transfer;Path(kw['run']['results'][0]['raw']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='raw input changed'):apply_products(**kw)


def test_airmass_must_be_inside_actual_tested_range(science_transfer):
    from efospec.telluric_night import apply_products
    kw=science_transfer
    # The science is 1.15, close to the training 1.10, but on the opposite side
    # of the sole test at 1.00. Absolute delta alone would wrongly pass it.
    kw['report']['transfers'][0].update(test_airmass=1.,delta_airmass=.1)
    apply_products(**kw)
    assert not kw['report']['products']
    assert kw['report']['skipped'][0]['tested_airmass_range']==[1.,1.1]


def test_time_review_is_retained_without_claiming_validation(science_transfer):
    from efospec.telluric_night import apply_products
    kw=science_transfer;kw['report']['fits'][0]['mjd']-=.1
    apply_products(**kw)
    assert not kw['report']['products']
    kw['output']=kw['output']/'review';kw['output'].mkdir()
    apply_products(**kw,review_extrapolation=True)
    assert kw['report']['products'][0]['review_reasons']==['standard more than two hours away']


def test_wavelength_gate_still_blocks_review_products(science_transfer):
    from efospec.telluric_night import apply_products
    kw=science_transfer;kw['run']['results'][0]['sky_flexure']['held_out_6363_pass']=False
    apply_products(**kw,review_extrapolation=True)
    assert not kw['report']['products']
    assert 'wavelength' in kw['report']['skipped'][0]['reason']


def test_correction_uses_fits_reference_pixel(science_transfer):
    from astropy.io import fits
    from efospec.telluric_night import apply_products
    kw=science_transfer
    with fits.open(kw['run']['results'][0]['product'],mode='update',checksum=True) as h:
        h[0].header['CRPIX1']=3.
    apply_products(**kw)
    with fits.open(kw['report']['products'][0]['product']) as h:
        table=h['TELLURIC'].data
        assert table['WAVE_AIR'][0]==5990.
        assert table['WAVE_AIR'][table['APPLIED']].min()==7540.
