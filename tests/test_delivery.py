import json
import numpy as np
import pytest
from astropy.io import fits
from efospec.delivery import prepare, digest

@pytest.fixture
def example(tmp_path):
    h=fits.Header(dict(OBJECT='AT2026example',INSTRUME='EFOSC',FILETYPE=22208,WAVEMED='air',SPECSYS='TOPOCENT',CTYPE1='LINEAR',CUNIT1='Angstrom',CRVAL1=4000.,CRPIX1=1.,CDELT1=5.5,BUNIT='erg / (s cm2 Angstrom)',EXPTIME=100.,RA=10.,DEC=-20.,GRISM='Gr13',FILTER='Free',SLIT='slit1.0',EPSTATUS='EXPERIMENTAL',QUALITY='Rapid'))
    h['DATE-OBS']='2026-10-28T00:00:00'; h['MJD-OBS']=61341.
    from astropy.time import Time
    h['MJD-OBS']=Time(h['DATE-OBS']).mjd
    data=np.ones((4,1,5))*1e-16; data[0,0,2]=-2e-17
    mask=np.ones(data.shape,dtype=np.uint8); mask[:,:,1]=0
    product=tmp_path/'input.fits'
    fits.HDUList([fits.PrimaryHDU(data,h),fits.ImageHDU(mask,name='VALID')]).writeto(product)
    row=dict(product=str(product),sha256=digest(product),object='AT2026example',observers='Test Observer',reducers='Test Reducer',reviewer='Test Reviewer',review_notes='Synthetic test only',source_group='Test',reduction_date='2026-11-13T00:00:00',spectrum_type='Object',identity_reviewed=True,wavelength_reviewed=True,flux_reviewed=True,release_authorized=True,visibility='public',associated_groups=[],proprietary_until=None)
    return tmp_path,row

def run(example, **changes):
    p,row=example; row.update(changes)
    manifest=p/'manifest.json'; manifest.write_text(json.dumps({'spectra':[row]}))
    return prepare(manifest,p/'out')

def test_roundtrip_and_mask(example):
    p,row=example; before=digest(row['product']); out=run(example)
    folder=out/'public/spectrum-001'; ascii=np.loadtxt(folder/'spectrum.ascii')
    assert ascii.shape==(4,2) and ascii[1,1]<0
    assert np.array_equal(fits.getdata(folder/'spectrum.fits'),fits.getdata(row['product']))
    assert digest(row['product'])==before
    assert fits.getheader(folder/'spectrum.fits')['EPSTATUS']=='EXPERIMENTAL'
    assert not (out/'private').exists()

@pytest.mark.parametrize('changes',[{'visibility':None},{'identity_reviewed':False},{'sha256':'wrong'},{'visibility':'private'},{'associated_groups':['Private team']},{'object':'Other'}])
def test_reject(example,changes):
    with pytest.raises(ValueError): run(example,**changes)
    assert not (example[0]/'out').exists()

def test_private(example):
    out=run(example,visibility='private',associated_groups=['Test'],proprietary_until='2099-01-01T00:00:00')
    assert (out/'private/spectrum-001/metadata.json').exists()
    assert not (out/'public').exists()

def test_provisional(example):
    _,row=example
    with fits.open(row['product'],mode='update') as h: h[0].header['EPSTATUS']='PROVISIONAL'
    with pytest.raises(ValueError,match='Provisional'): run(example,sha256=digest(row['product']))

def test_no_overwrite(example):
    run(example)
    with pytest.raises(ValueError,match='exists'): run(example)

def test_duplicate_across_classes(example):
    p,row=example
    second=dict(row,visibility='private',associated_groups=['Test'],proprietary_until='2099-01-01T00:00:00')
    manifest=p/'manifest.json'; manifest.write_text(json.dumps({'spectra':[row,second]}))
    with pytest.raises(ValueError,match='Duplicate'): prepare(manifest,p/'out')
