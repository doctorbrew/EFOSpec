"""Real IRAF arithmetic regression; skipped when the IRAF runtime is absent."""
import os
from pathlib import Path
import numpy as np
import pytest
from astropy.io import fits


@pytest.mark.parametrize('transmission', [np.full(20,0.5),np.linspace(0.4,0.8,20)])
def test_telluric_sigma_scales_with_flux(tmp_path, monkeypatch, transmission):
    root=Path(os.environ.get('iraf','/usr/local/lib/iraf/'))
    if not (root/'noao/bin.macos64/x_onedspec.e').exists():
        pytest.skip('Local IRAF runtime unavailable')
    monkeypatch.setenv('iraf',str(root)+'/')
    monkeypatch.setenv('PYRAF_NO_DISPLAY','1')
    monkeypatch.setenv('PYRAF_CLCACHE_PATH',str(tmp_path/'cache'))
    (tmp_path/'cache').mkdir()
    monkeypatch.chdir(tmp_path)
    with open(os.devnull) as stdin:
        monkeypatch.setattr('sys.stdin',stdin)
        from pyraf import iraf
        iraf.noao(_doprint=0);iraf.imred(_doprint=0);iraf.specred(_doprint=0);iraf.imutil(_doprint=0)
        iraf.chdir(str(tmp_path))
        from ntt.efoscspec1Ddef import _correct_telluric
        h=fits.Header({'CRVAL1':5000.,'CRPIX1':1.,'CD1_1':2.,'CTYPE1':'LINEAR','DC-FLAG':0,'WCSDIM':3,'WAT0_001':'system=equispec','WAT1_001':'wtype=linear label=Wavelength units=angstroms','WAT2_001':'wtype=linear','WAT3_001':'wtype=linear','CD2_2':1.,'CD3_3':1.,'CTYPE2':'LINEAR','CTYPE3':'LINEAR','APNUM1':'1 1 1 5'})
        for band,label in enumerate(['spectrum','raw','background','sigma'],1):
            h['BANDID'+str(band)]=label+' - background fit'
        source=np.array([10.,12.,3.,2.],dtype=np.float32)[:,None,None]*np.ones((4,1,20),np.float32)
        # Only band 1 of an atmosphere product is transmission; other bands can
        # retain unrelated extraction diagnostics. Do not divide sigma by band 4.
        atmosphere=np.array([.5,7.,9.,11.],dtype=np.float32)[:,None,None]*np.ones((4,1,20),np.float32)
        atmosphere[0,0]=transmission
        fits.writeto('source.fits',source,h);fits.writeto('atmo.fits',atmosphere,h)
        _correct_telluric('source.fits','atmo.fits','corrected.fits')
        corrected=fits.getdata('corrected.fits')
        np.testing.assert_allclose(corrected[0],source[0]/transmission)
        np.testing.assert_allclose(corrected[3],source[3]/transmission)
        np.testing.assert_array_equal(corrected[1:3],source[1:3])


def test_python_wavelength_update_reaches_running_iraf(tmp_path, monkeypatch):
    root=Path(os.environ.get('iraf','/usr/local/lib/iraf/'))
    if not (root/'noao/bin.macos64/x_onedspec.e').exists():
        pytest.skip('Local IRAF runtime unavailable')
    monkeypatch.setenv('iraf',str(root)+'/')
    monkeypatch.setenv('PYRAF_NO_DISPLAY','1')
    monkeypatch.chdir(tmp_path)
    with open(os.devnull) as stdin:
        monkeypatch.setattr('sys.stdin',stdin)
        from pyraf import iraf
        import ntt
        iraf.noao(_doprint=0);iraf.onedspec(_doprint=0)
        iraf.chdir(str(tmp_path))
        h=fits.Header({'CRVAL1':5000.,'CD1_1':2.,'CRPIX1':1.,'WAT0_001':'system=equispec',
                       'WAT1_001':'wtype=linear label=Wavelength units=angstroms','CTYPE1':'LINEAR','APNUM1':'1 1 1 5'})
        fits.writeto('input.fits',np.arange(20,dtype=np.float32)+1,h)
        iraf.sarith('input.fits','*','1','before.fits')
        ntt.util.updateheader('input.fits',0,{'CRVAL1':[4993.,'Applied shift']})
        iraf.sarith('input.fits','*','1','after.fits')
        assert fits.getheader('after.fits')['CRVAL1']==4993.
