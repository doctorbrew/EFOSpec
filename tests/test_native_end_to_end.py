"""Synthetic raw photons through real PypeIt masters and exported products."""
from pathlib import Path
import builtins
import io
import json
import numpy as np
import pytest
from astropy.io import fits
from astropy import units as u
from test_pypeit_adapter import write_raw


@pytest.fixture(scope='module')
def synthetic_raw_night(tmp_path_factory):
    from efospec.native_wave import atlas
    from pypeit.core.wave import vactoair
    root=tmp_path_factory.mktemp('native_raw_photons')
    rng=np.random.default_rng(731)
    y,x=np.indices((1030,1030));slit=(x>80)&(x<970)
    q=y+.003*(x-525);wave=3650.+5.55*q+.00012*(q-512)**2
    air=vactoair(wave*u.AA).value
    def save(name,signal,**header):
        path=write_raw(root,name,**header)
        values=1000.+(rng.poisson(np.maximum(signal,0))+rng.normal(0,7.8,signal.shape))/.91
        with fits.open(path,mode='update') as h:h[0].data=values.astype(np.float32)
        return path
    for n in range(3):
        save(f'bias{n}.fits',np.zeros_like(wave),**{'ESO DPR CATG':'CALIB','ESO DPR TYPE':'BIAS','EXPTIME':0.})
        save(f'flat{n}.fits',slit*16000.*(1+.15*(y-512)/512),**{'ESO DPR CATG':'CALIB','ESO DPR TYPE':'FLAT','OBJECT':'dome','ESO OBS ID':101,'EXPTIME':10.})
    arc=np.full(wave.shape,10.)
    for line in atlas()['wave']:
        arc+=18000*np.exp(-.5*((wave-line)/9.)**2)
    save('arc.fits',slit*arc,**{'ESO DPR CATG':'CALIB','ESO DPR TYPE':'WAVE','EXPTIME':10.})
    sky=np.full(wave.shape,120.)
    for line,amplitude in [(5577.338,1000),(6300.304,600),(6363.776,200)]:
        sky+=amplitude*np.exp(-.5*((air-line)/8.)**2)
    profile=np.exp(-.5*((x-548.-1.5*np.sin(y/300))/2.)**2)
    profile/=profile.sum(axis=1)[:,None]
    science=save('science.fits',slit*(sky+profile*3000),OBJECT='SyntheticSN',EXPTIME=1200.)
    standard=save('standard.fits',slit*(sky+profile*20000),OBJECT='SyntheticStandard',EXPTIME=100.,
                  **{'ESO DPR CATG':'CALIB','ESO DPR TYPE':'STD','ESO DPR TECH':'SPECTRUM'})
    return root,science,standard


def test_full_raw_reduction_without_legacy_access(synthetic_raw_night,tmp_path,monkeypatch):
    from efospec.native_reduction import reduce_pair
    from efospec.revisions import Exposure,reextract
    from efospec.native_calibrations import load_calibrations
    from efospec import standard_reference
    root,science,standard=synthetic_raw_night
    # Independent physical flux truth: smooth flat F_lambda, no archived response.
    wave=np.arange(3000.,11001.,2.)
    def physical(frame,cache):
        return dict(name='SyntheticStandard',std_ra=0.,std_dec=0.,cal_file='synthetic-physical-truth',
                    std_source='test_photons',wave=wave*u.AA,
                    flux=np.full(wave.shape,1000.)*u.erg/u.s/u.cm**2/u.AA)
    monkeypatch.setattr(standard_reference,'standard_reference',physical)
    def guard(original):
        def guarded(file,*args,**kwargs):
            if isinstance(file,(str,Path)) and any(s in str(file) for s in ('trunk/src/ntt','/archive/efosc','/database/')):
                raise AssertionError('attempt to read an IRAF calibration')
            return original(file,*args,**kwargs)
        return guarded
    monkeypatch.setattr(builtins,'open',guard(builtins.open))
    monkeypatch.setattr(io,'open',guard(io.open))
    out=tmp_path/'native'
    result=reduce_pair(root,science,standard,out,render_report=False)
    assert len(result['results'])==1 and not result['errors']
    row=result['results'][0]
    assert row['sky_flexure']['held_out_6363_pass']
    assert row['processing']['bias'] and row['processing']['flat']
    with fits.open(row['product']) as h:
        assert h[0].header['FLUXCAL']=='NATIVE'
        assert h[0].header['WAVEMED']=='air'
        good=h['VALID'].data[0].astype(bool)
        # 3000 e-/1200 s vs 20000 e-/100 s, same response/airmass.
        assert np.median(h[0].data[0,0,good])/1.25e-16==pytest.approx(1.,rel=.08)
    exposure=Exposure(out,Path(row['product']).name,reference_root=tmp_path/'absent-IRAF')
    assert exposure.context.processed is not None
    replay=reextract(out,Path(row['product']).name,exposure.default_recipe(),tmp_path/'replay',
                     reference_root=tmp_path/'absent-IRAF',render_report=False)
    np.testing.assert_array_equal(fits.getdata(row['product']),fits.getdata(replay['results'][0]['product']))
    bundle=load_calibrations(out/'science-calibration/calibration')
    assert bundle['wavevac'].shape==(1024,1024)
