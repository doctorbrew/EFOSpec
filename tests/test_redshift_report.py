"""Catalogue associations, reference frames, and honest table statuses."""
import json
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from efospec.redshift_run import ned_candidate,heliocentric
from efospec.redshift_report import redshift_cells


def test_nearest_galaxy_without_z_never_borrows_farther_redshift(tmp_path,monkeypatch):
    centre=SkyCoord(10*u.deg,20*u.deg,frame='fk5').icrs
    def fetch(catalogue,point,radius,directory,timeout):
        directory.mkdir()
        result=dict(status='ok',rows=[dict(name='nearest',ra=centre.ra.deg,dec=centre.dec.deg,
            galaxy_candidate=True,metadata=dict(z=None,zflag='')),
            dict(name='farther',ra=centre.ra.deg+.002,dec=centre.dec.deg,
            galaxy_candidate=True,metadata=dict(z=.2,zflag='SUN'))])
        (directory/'NED.json').write_text(json.dumps(result));return result
    monkeypatch.setattr('efospec.field_catalogues.fetch_catalogue',fetch)
    r=ned_candidate(dict(RA=10.,DEC=20.),tmp_path/'catalogue')
    assert r['candidate']['name']=='nearest' and r['candidate']['metadata']['z'] is None
    assert len(r['candidates'])==2
    cells=redshift_cells(dict(ned=r,spectral=dict(status='no_reliable_line_system'),raw='raw.fits'))
    assert 'z unavailable' in cells[0] and '0.2' not in cells[0]
    assert 'Insufficient matching lines' in cells[1]


def test_heliocentric_correction_is_multiplicative(monkeypatch):
    monkeypatch.setattr(SkyCoord,'radial_velocity_correction',lambda *a,**kw:30*u.km/u.s)
    r=heliocentric(.2,dict(RA=10.,DEC=20.,**{'ESO TEL GEOLON':-70.,'ESO TEL GEOLAT':-29.,
        'ESO TEL GEOELEV':2377.,'MJD-OBS':61000.,'EXPTIME':1000.}))
    assert r['z_heliocentric']==pytest.approx(1.2*(1+30/299792.458)-1,abs=1e-12)
    assert r['mid_exposure_mjd']==pytest.approx(61000+500/86400)


def test_provisional_spectral_and_photometric_catalogue_statuses_are_separate():
    r=dict(raw='science.fits',ned=dict(candidate=dict(name='galaxy',metadata=dict(z=.074716,zflag='PUN'),
        separation_arcsec=6.1)),spectral=dict(z_heliocentric=.023834,wavelength_validated=False,status='provisional_wavelength'))
    ned,spectral=redshift_cells(r)
    assert 'photometric' in ned and '0.074716' in ned and 'candidate host' in ned
    assert '0.0238' in spectral and 'provisional wavelength' in spectral
    assert redshift_cells(None,standard=True)==['—','—']
