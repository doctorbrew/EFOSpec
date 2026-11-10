"""Pinned, externally published VMa2 spectrophotometry for response trials."""
import hashlib
import io
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

URL = ('https://www.ing.iac.es/Astronomy/observing/manuals/html_manuals/'
       'tech_notes/tn065-100/small/vma2.tab')
SHA256 = '0946bf47436a0c8b02d465e0621d1dafba2e2c644dc58b593357eb4163957675'
ASTROMETRY = 'https://arxiv.org/html/1411.0299v2#S3.T2'


def position_at(mjd):
    """PESSTO Table 2 FK5/J2000 coordinates and proper motions in mas/year.

    A tangent-plane propagation is adequate for this 100-arcsec association
    gate; it is not acquisition-image astrometry or a source identity proof.
    """
    reference = SkyCoord('00h49m09.902s', '+05d23m19.01s', frame='fk5', equinox='J2000')
    years = (Time(mjd, format='mjd').jyear-2000.)
    return reference.spherical_offsets_by(1236.90*years*u.mas, -2709.19*years*u.mas).icrs


def parse_table(text):
    """Convert the explicitly labelled mJy table to cgs per air Angstrom."""
    if 'SET .Z.UNITS = "mjy"' not in text:
        raise ValueError('VMa2 reference must explicitly specify mJy')
    rows = [line for line in text.splitlines() if line.strip()
            and not line.lstrip().startswith(('*', 'SET'))]
    table = np.loadtxt(io.StringIO('\n'.join(rows)), ndmin=2)
    if (table.shape[1] != 2 or len(table) < 2 or not np.isfinite(table).all()
            or np.any(table <= 0) or np.any(np.diff(table[:,0]) <= 0)):
        raise ValueError('invalid VMa2 reference grid or flux')
    air = table[:,0]
    flux = (table[:,1]*u.mJy).to_value(u.erg/u.s/u.cm**2/u.AA,
                                      equivalencies=u.spectral_density(air*u.AA))
    return air, flux


def reference(frame, cache):
    """Return None for an unrelated pointing, regardless of its OBJECT string."""
    h = frame['metadata']
    predicted = position_at(h['MJD-OBS'])
    separation = SkyCoord(h['RA']*u.deg, h['DEC']*u.deg).separation(predicted).arcsec
    if separation > 100.:
        return None
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    path = cache/'vma2-oke1974-ing.tab'
    if not path.exists():
        import requests
        response = requests.get(URL, timeout=(10,45)); response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != SHA256:
            raise ValueError('downloaded VMa2 reference failed its pinned checksum')
        path.write_bytes(response.content)
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError('VMa2 physical reference changed')
    from pypeit.core.wave import airtovac
    air, flux_air = parse_table(path.read_text())
    vacuum = airtovac(air*u.AA).value
    flux = flux_air*np.gradient(air)/np.gradient(vacuum)/1e-17
    return dict(name='VMa2', std_ra=predicted.ra.deg, std_dec=predicted.dec.deg,
        cal_file=str(path.resolve()), std_source='Oke_1974_ING', wave=vacuum*u.AA,
        flux=flux*u.erg/u.s/u.cm**2/u.AA, reference_url=URL, reference_sha256=SHA256,
        coordinate_separation_arcsec=float(separation),
        astrometry_reference=ASTROMETRY, coordinate_epoch_mjd=float(h['MJD-OBS']),
        wavelength_interpretation='air assumed for historical ground-based Oke table; header does not specify medium',
        limitations=['Published reference has variable wavelength sampling (10 to 80 A).',
                     'Coordinate association does not verify the extracted trace identity.',
                     'This reference enables experimental responses, not independent absolute-flux validation.'])
