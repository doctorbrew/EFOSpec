"""Raw-only orchestration and physical-response tests; no legacy library fixture."""
from pathlib import Path
from copy import deepcopy
import json
import numpy as np
import pytest
from astropy.io import fits
from astropy import units as u
from efospec.inventory import inspect_file,inventory,sha256
from efospec.native_readiness import assess_native_readiness
from test_pypeit_adapter import write_raw


@pytest.fixture
def raw_group(tmp_path):
    raw=write_raw(tmp_path,'science.fits')
    for i in range(3):
        write_raw(tmp_path,f'bias{i}.fits',**{'ESO DPR CATG':'CALIB','ESO DPR TYPE':'BIAS','EXPTIME':0.})
        write_raw(tmp_path,f'flat{i}.fits',**{'ESO DPR CATG':'CALIB','ESO DPR TYPE':'FLAT','OBJECT':'dome','ESO OBS ID':101,'EXPTIME':10.})
    write_raw(tmp_path,'arc.fits',**{'ESO DPR CATG':'CALIB','ESO DPR TYPE':'WAVE','EXPTIME':10.})
    f=inspect_file(raw);r=assess_native_readiness(inventory([str(tmp_path)]))
    return f,r['exposures'][0]['raw_calibrations']


def test_raw_associations_cannot_accept_processed_or_changed_inputs(raw_group,tmp_path):
    from efospec.native_calibrations import validate_associations
    f,a=raw_group
    selected=validate_associations(f,a)
    assert len(selected)==8 and selected[f['path']]=='science'
    changed=deepcopy(a);changed['arc']['sha256']=['0'*64]
    with pytest.raises(ValueError,match='changed raw arc'):validate_associations(f,changed)
    missing=deepcopy(a);missing['bias']['files']=missing['bias']['files'][:2]
    with pytest.raises(ValueError,match='incomplete'):validate_associations(f,missing)
    invalid=deepcopy(f);invalid['setup']['grism']='Gr16'
    with pytest.raises(ValueError,match='Gr11/Gr13'):validate_associations(invalid,a)


def test_processing_preserves_flat_corrected_noise(raw_group,tmp_path):
    from efospec.native_calibrations import native_parameters,process_exposure
    from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
    from pypeit.images.buildimage import BiasImage
    from pypeit.flatfield import FlatImages
    from pypeit.slittrace import SlitTraceSet
    from types import SimpleNamespace
    f,_=raw_group
    with fits.open(f['path'],mode='update') as h:h[0].data=np.full((1030,1030),1000.)
    f=inspect_file(Path(f['path']));inst=EFOSpecEFOSC2Spectrograph();par=native_parameters(inst)
    with fits.open(f['path']) as hdus:detector=inst.get_detector_par(1,hdus)
    bias=BiasImage(np.full((1024,1024),100*.91),ivar=np.full((1024,1024),1/10),
                   detector=detector,PYP_SPEC=inst.name)
    slit=SlitTraceSet(np.full(1024,10.),np.full(1024,1010.),'MultiSlit',nspat=1024,detname='DET01',PYP_SPEC=inst.name)
    flat=FlatImages(pixelflat_norm=np.full((1024,1024),2.),PYP_SPEC=inst.name,spat_id=slit.spat_id)
    par['scienceframe']['process']['use_illumflat']=False
    cal=SimpleNamespace(msbias=bias,msbpm=np.zeros((1024,1024),bool),flatimages=flat,slits=slit)
    b=dict(calibrations=cal,parameters=par,instrument=inst)
    image=process_exposure(f,b)
    assert np.median(image.image)==pytest.approx((1000-100)*.91/2)
    assert np.median(image.img_scale)==pytest.approx(.5)
    assert np.all(image.ivar>0)
    assert not par['calibrations']['biasframe']['process']['use_biasimage']
    assert par['calibrations']['wavelengths']['reid_arxiv'] is None
    f['sha256']='0'*64
    with pytest.raises(ValueError,match='changed'):process_exposure(f,b)


def test_native_response_cgs_air_units_and_no_extrapolation(tmp_path):
    from efospec.native_flux import response_factor
    from pypeit.core import flux_calib
    from pypeit.core.wave import airtovac
    air=np.arange(4000.,8001.,5.);vac=airtovac(air*u.AA).value
    # Fix the physical response at 2e-17 cgs per (e-/s/vacuum-A).
    # Invert PypeIt's AB zero-point relation numerically (linear in log sensitivity).
    zp0=np.full_like(vac,20.);s0=flux_calib.Nlam_to_Flam(vac,zp0)
    zp=zp0-2.5*np.log10(2./s0)
    response=tmp_path/'response.fits'
    header=fits.Header({'LONGITUD':-70.7336,'LATITUDE':-29.2584,'EXTFILE':'lasillaextinct.dat'})
    fits.HDUList([fits.PrimaryHDU(header=header),fits.BinTableHDU.from_columns([
        fits.Column(name='WAVE',format='D',array=vac),fits.Column(name='ZEROPOINT',format='D',array=zp),
        fits.Column(name='VALID',format='L',array=np.ones(len(vac),bool))],name='RESPONSE')]).writeto(response)
    f,good=response_factor(air,response,100.,1.)
    ext=flux_calib.load_extinction_data(-70.7336,-29.2584,'lasillaextinct.dat')
    corr=flux_calib.extinction_correction(vac*u.AA,1.,ext)
    np.testing.assert_allclose(f[good],2e-17*corr[good]/100/5,rtol=1e-10)
    f,m=response_factor(np.arange(3500.,8501.,5.),response,100.,1.)
    assert not m[0] and not m[-1] and np.isnan(f[0])
    with fits.open(response,mode='update') as h:h['RESPONSE'].data['VALID'][300:320]=False
    f,m=response_factor(air,response,100.,1.)
    assert not m[300:320].any() and np.isnan(f[300:320]).all()
    assert m[250] and m[350]


def test_standard_reference_may_not_be_extrapolated(tmp_path):
    from types import SimpleNamespace
    from efospec.native_flux import build_response
    wave=np.linspace(4000.,8000.,400)
    spectrum=SimpleNamespace(OPT_WAVE=wave,OPT_COUNTS=np.ones(400),
                             OPT_COUNTS_IVAR=np.ones(400),OPT_MASK=np.ones(400,bool))
    reference={'wave':np.array([4500.,7500.])*u.AA}
    with pytest.raises(ValueError,match='does not cover'):
        build_response({'metadata':{}},spectrum,tmp_path/'response.fits',reference)


def test_unverified_standard_is_not_replaced_by_nearest_star(raw_group,tmp_path,monkeypatch):
    from efospec.standard_reference import standard_reference
    from pypeit.core import flux_calib
    f,_=raw_group;f['metadata'].update(RA=12.3,DEC=5.3)
    monkeypatch.setattr(flux_calib,'find_standard_file',lambda *a,**k:False)
    with pytest.raises(ValueError,match='No independently'):standard_reference(f,tmp_path/'cache')


def test_failed_group_records_its_error_without_archived_fallback(raw_group,tmp_path,monkeypatch):
    from efospec.native_calibrations import build_calibrations
    from pypeit.calibrations import Calibrations
    f,a=raw_group
    monkeypatch.setattr(Calibrations,'get_bias',lambda *args:None)
    with pytest.raises(ValueError,match='native bias'):build_calibrations(f,a,tmp_path/'failed')
    record=json.loads((tmp_path/'failed/calibration.json').read_text())
    assert record['status']=='failed' and record['mode']=='native_raw_only'
    assert 'bias' in record['error']


def test_downloaded_physical_reference_is_pinned_and_reused(tmp_path,monkeypatch):
    import hashlib
    import requests
    from types import SimpleNamespace
    from efospec import standard_reference as module
    from pypeit.core import flux_calib
    body=b'# cgs F_lambda\n4000 1e-14\n5000 8e-15\n6000 6e-15\n'
    monkeypatch.setattr(module,'L745_SHA256',hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(flux_calib,'find_standard_file',lambda *a,**k:False)
    calls=[]
    def get(url,**kwargs):
        calls.append(url);return SimpleNamespace(content=body,raise_for_status=lambda:None)
    monkeypatch.setattr(requests,'get',get)
    frame={'metadata':{'RA':115.086625,'DEC':-17.413667}}
    result=module.standard_reference(frame,tmp_path/'refs')
    assert calls==[module.L745_URL] and result['name']=='L745-46A'
    assert result['wave'][0].value>4000
    assert result['flux'][0].value==pytest.approx(1000.,rel=.001)
    module.standard_reference(frame,tmp_path/'refs');assert len(calls)==1
    Path(result['cal_file']).write_text('changed')
    with pytest.raises(ValueError,match='changed'):module.standard_reference(frame,tmp_path/'refs')
    monkeypatch.setattr(module,'L745_SHA256','0'*64)
    with pytest.raises(ValueError,match='checksum'):module.standard_reference(frame,tmp_path/'bad')


def test_pypeit_physical_reference_is_used_directly(tmp_path,monkeypatch):
    from efospec.standard_reference import standard_reference
    from pypeit.core import flux_calib
    physical={'name':'known-physical-star'}
    monkeypatch.setattr(flux_calib,'find_standard_file',lambda *a,**k:True if k.get('check') else physical)
    assert standard_reference({'metadata':{'RA':0.,'DEC':0.}},tmp_path)==physical
