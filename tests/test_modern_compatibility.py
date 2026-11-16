import os
os.environ.setdefault('MPLBACKEND','Agg')
import pytest
import numpy as np
from astropy.io import fits
from astropy import units as u
import ntt


def test_version_is_available():
    assert ntt.__version__ == '3.0.1'


def test_2d_flux_unit_matches_stored_scaling(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    h=fits.Header({'CRVAL2':5000.,'CD2_2':2.,'INSTRUME':'EFOSC','EXPTIME':10.,'ESO TEL AIRM START':0.,'ESO TEL AIRM END':0.})
    fits.writeto('science.fits',np.ones((5,3))*20,h)
    fits.writeto('sens.fits',np.zeros(5),fits.Header({'CRVAL1':5000.,'CD1_1':2.}))
    result=ntt.efoscspec1Ddef.fluxcalib2d('science.fits','sens.fits')
    data,header=fits.getdata(result,header=True)
    physical=(data.astype(float)*u.Unit(header['BUNIT'])).to_value(u.erg/u.s/u.cm**2/u.AA)
    # 20 counts / 10 seconds / sensitivity(2) = 1 in physical units.
    np.testing.assert_allclose(physical,1.,rtol=1e-6)


def test_import_preserves_selected_plot_backend():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-c',"import matplotlib; matplotlib.use('Agg'); import ntt; print(matplotlib.get_backend())"],capture_output=True,text=True,check=True)
    assert result.stdout.strip().lower()=='agg'


@pytest.mark.parametrize('interactive', [False, None, 'no', 'NO'])
def test_batch_standard_selection_does_not_prompt(tmp_path, monkeypatch, interactive):
    from ntt.efoscspec1Ddef import _select_flux_standard
    first=tmp_path/'first.fits';second=tmp_path/'second.fits'
    first.touch();second.touch()
    def forbidden(*args):
        raise AssertionError('Noninteractive reduction requested input')
    monkeypatch.setattr('builtins.input',forbidden)
    assert _select_flux_standard([str(first),str(second)],interactive)==str(first)


def test_interactive_standard_selection_rejects_unlisted_file(tmp_path, monkeypatch):
    from ntt.efoscspec1Ddef import _select_flux_standard
    first=tmp_path/'first.fits';second=tmp_path/'second.fits';other=tmp_path/'other.fits'
    for p in [first,second,other]:p.touch()
    answers=iter([str(other),str(second)])
    monkeypatch.setattr('builtins.input',lambda _:next(answers))
    assert _select_flux_standard([str(first),str(second)],True)==str(second)
