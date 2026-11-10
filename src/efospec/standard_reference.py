"""Physical stellar references, independent of the legacy reduction library."""
from pathlib import Path
import hashlib
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord

# Public reference distributed by the instrument team's PyWiFeS repository.
# The table header specifies Bessell January 2009, cgs F_lambda and 4-A sampling.
L745_URL='https://raw.githubusercontent.com/PyWiFeS/pywifes/e854c3648d81ff940c84036082e114c5a6e57b62/reference_data/l745-46a_v2.tab'
L745_SHA256='49bfb6c156b85e3f8cd74b57f6c147f9d7f885125bdca43c1c86e05f986acc58'


def standard_reference(frame, cache):
    from pypeit.core import standard
    from pypeit.core.wave import airtovac
    h=frame['metadata']
    # PypeIt 3 returns a Spectrum with vacuum A and flux in 1e-17 cgs units.
    # Preserve our 100-arcsec physical-reference match; exclude model fallbacks.
    archives=['xshooter','calspec','esofil','noao','ing','lbtmods']
    if standard.get_archive_standard(h['RA'],h['DEC'],tol=100./60.,archives=archives,check=True):
        spectrum=standard.get_archive_standard(h['RA'],h['DEC'],tol=100./60.,archives=archives)
        meta=spectrum.meta
        return dict(name=str(meta['Name']),std_ra=float(meta['ra_deg']),std_dec=float(meta['dec_deg']),
            cal_file=str(spectrum.file),std_source=meta['source'],
            wave=spectrum.wave*u.AA,flux=spectrum.flux*u.erg/u.s/u.cm**2/u.AA)
    position=SkyCoord(h['RA']*u.deg,h['DEC']*u.deg)
    reference=SkyCoord('07h40m20.79s','-17d24m49.2s')
    if position.separation(reference)>100*u.arcsec:
        from .vma2_reference import reference as vma2_reference
        vma2 = vma2_reference(frame, cache)
        if vma2 is not None:
            return vma2
        raise ValueError('No independently registered physical reference within 100 arcsec; raw standard identity needs review')
    # Coordinate matching, not a potentially abbreviated OBJECT string, controls selection.
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);path=cache/'l745-46a_v2.tab'
    if not path.exists():
        import requests
        response=requests.get(L745_URL,timeout=(10,45));response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest()!=L745_SHA256:
            raise ValueError('downloaded physical standard reference failed its pinned checksum')
        path.write_bytes(response.content)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=L745_SHA256:
        raise ValueError('physical standard reference changed')
    table=np.loadtxt(path);air=table[:,0];vac=airtovac(air*u.AA).value
    # Air convention follows PyWiFeS' native AIR grid. Retain this interpretation
    # explicitly because this historical ASCII file has no wavelength-medium card.
    flux=table[:,1]*np.gradient(air)/np.gradient(vac)/1e-17
    return dict(name='L745-46A',std_ra=reference.ra.deg,std_dec=reference.dec.deg,
        cal_file=str(path.resolve()),std_source='Bessell_2009_PyWiFeS',wave=vac*u.AA,
        flux=flux*u.erg/u.s/u.cm**2/u.AA,reference_url=L745_URL,reference_sha256=L745_SHA256,
        wavelength_interpretation='air, inferred from PyWiFeS native AIR convention; ASCII header does not specify medium',
        coordinate_separation_arcsec=float(position.separation(reference).arcsec))
