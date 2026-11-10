import json
from types import SimpleNamespace

import numpy as np
import pytest
from astropy import units as u
from astropy.io import fits


def test_coverage_retains_empty_bins_and_internal_holes():
    from efospec.native_acceptance import wavelength_coverage
    wave=np.arange(4500.,8000.,5.);valid=np.ones(wave.size,bool)
    valid[(wave>=6000)&(wave<6500)]=False
    rows=wavelength_coverage(wave,valid)
    assert len(rows)==9
    assert rows[0]['valid_fraction']==rows[-1]['valid_fraction']==0
    assert rows[4]['valid_fraction']==0 and rows[3]['valid_fraction']==1
    with pytest.raises(ValueError):wavelength_coverage(wave[::-1],valid)


def test_standard_training_closure_cannot_claim_independent_accuracy(tmp_path):
    from efospec.native_acceptance import standard_recovery
    from pypeit.core import flux_calib
    from pypeit.core.wave import airtovac
    air=np.arange(4000.,8501.,5.);vac=airtovac(air*u.AA).value
    zp0=np.full_like(vac,20.);zp=zp0-2.5*np.log10(2./flux_calib.Nlam_to_Flam(vac,zp0))
    response=tmp_path/'response.fits'
    h=fits.Header({'LONGITUD':-70.7336,'LATITUDE':-29.2584,'EXTFILE':'lasillaextinct.dat'})
    fits.HDUList([fits.PrimaryHDU(header=h),fits.BinTableHDU.from_columns([
        fits.Column(name='WAVE',format='D',array=vac),fits.Column(name='ZEROPOINT',format='D',array=zp),
        fits.Column(name='VALID',format='L',array=np.ones(vac.size,bool))],name='RESPONSE')]).writeto(response)
    response.with_suffix('.json').write_text(json.dumps({'standard_sha256':'training'}))
    from pypeit.core.atmextinction import AtmosphericExtinction
    extinction=AtmosphericExtinction.from_file('lasillaextinct.dat')
    correction=extinction.correction_factor(vac,1.)
    # 2e-17 response, 100 s, 5 air-A bins: this photon rate implies 1e-14 cgs/air-A.
    counts=np.full(air.size,250000.)/correction
    spectrum=SimpleNamespace(OPT_WAVE=vac,OPT_COUNTS=counts,OPT_COUNTS_IVAR=np.ones(vac.size),OPT_MASK=np.ones(vac.size,bool))
    reference={'wave':vac*u.AA,'flux':1000*np.gradient(air)/np.gradient(vac),'name':'Known truth'}
    frame={'path':'standard.fits','sha256':'training','metadata':{'EXPTIME':100.,'ESO TEL AIRM START':1.}}
    record,arrays=standard_recovery(frame,spectrum,response,reference)
    assert record['median_ratio']==pytest.approx(1.,rel=1e-6)
    assert not record['independent_exposure'] and not record['science_validated']
    spectrum.OPT_COUNTS*=.8;frame['sha256']='held-out'
    record,_=standard_recovery(frame,spectrum,response,reference)
    assert record['independent_exposure'] and not record['science_validated']
    assert record['median_ratio']==pytest.approx(.8,rel=1e-6)
