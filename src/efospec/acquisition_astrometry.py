"""Local acquisition-image astrometry; never alter the raw FITS header."""
from pathlib import Path
import shutil
import subprocess

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

from .inventory import sha256


def check_solution(wcs_path, correspondence_path, shape):
    wcs = WCS(fits.getheader(wcs_path)).celestial
    if not wcs.has_celestial:
        raise ValueError('solver did not provide celestial coordinates')
    scale = proj_plane_pixel_scales(wcs)*3600.
    if not np.isfinite(scale).all() or np.any((scale < .20) | (scale > .30)):
        raise ValueError('solution scale inconsistent with binned EFOSC2 acquisition')
    corr = fits.getdata(correspondence_path, 1)
    keep = np.asarray(corr['match_weight']) > .9
    # Astrometry.net correspondence coordinates are FITS pixels (origin 1).
    x, y = wcs.all_world2pix(corr['index_ra'][keep], corr['index_dec'][keep], 1)
    residual = np.hypot(x-corr['field_x'][keep], y-corr['field_y'][keep])
    if len(residual) < 8 or not np.isfinite(residual).all():
        raise ValueError('fewer than eight finite high-weight astrometric matches')
    rms = float(np.sqrt(np.mean(residual**2)))
    if rms > 2. or np.max(residual) > 5.:
        raise ValueError('astrometric correspondence residuals exceed 2-pixel RMS / 5-pixel maximum')
    ny, nx = shape
    px = np.array([0, nx-1, nx-1, 0, (nx-1)/2])
    py = np.array([0, 0, ny-1, ny-1, (ny-1)/2])
    sky = wcs.pixel_to_world(px, py)
    xx, yy = wcs.world_to_pixel(sky)
    if not np.allclose(np.column_stack([xx, yy]), np.column_stack([px, py]), atol=.01):
        raise ValueError('acquisition WCS fails pixel/sky round-trip')
    centre = sky[-1].icrs
    radius = float(centre.separation(sky[:-1]).arcmin.max())*1.02
    return wcs, {'status': 'solved', 'matched_stars': len(residual), 'rms_pixel': rms,
        'max_residual_pixel': float(np.max(residual)), 'pixel_scale_arcsec': scale.tolist(),
        'centre_icrs_deg': [float(centre.ra.deg), float(centre.dec.deg)],
        'radius_arcmin': radius, 'independent_astrometric_validation': False,
        'validation': 'Astrometry.net matched-star residuals and WCS round-trip; not held-out stars'}


def solve_acquisition(raw, output, *, executable='solve-field', timeout=90):
    raw, output = Path(raw).resolve(), Path(output).resolve()
    header = fits.getheader(raw)
    if header.get('NAXIS') != 2 or header.get('ESO DET WIN1 BINX') != 2 or header.get('ESO DET WIN1 BINY') != 2:
        raise ValueError('acquisition solver currently supports 2D, 2x2-binned EFOSC2 frames')
    ra, dec = float(header['RA']), float(header['DEC'])
    if not np.isfinite([ra, dec]).all() or not 0 <= ra < 360 or not -90 <= dec <= 90:
        raise ValueError('invalid pointing coordinates')
    program = shutil.which(executable)
    if not program:
        raise ValueError('local Astrometry.net solve-field is required, with installed reference indexes')
    output.mkdir(parents=True, exist_ok=False)
    digest = sha256(raw)
    command = [program, str(raw), '--dir', str(output), '--out', 'acquisition',
        '--ra', str(ra), '--dec', str(dec), '--radius', '.3',
        '--scale-units', 'arcsecperpix', '--scale-low', '.20', '--scale-high', '.30',
        '--no-plots', '--no-remove-lines', '--new-fits', 'none', '--cpulimit', str(int(timeout))]
    with (output/'solve.log').open('w') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout+15)
    if sha256(raw) != digest:
        raise ValueError('raw acquisition changed during astrometry')
    if result.returncode or not (output/'acquisition.solved').exists():
        raise ValueError('acquisition was not solved; see solve.log')
    wcs_path, corr_path = output/'acquisition.wcs', output/'acquisition.corr'
    wcs, record = check_solution(wcs_path, corr_path, (header['NAXIS2'], header['NAXIS1']))
    record.update(raw=str(raw), raw_sha256=digest, command=command,
        wcs=str(wcs_path), wcs_sha256=sha256(wcs_path),
        correspondences=str(corr_path), correspondences_sha256=sha256(corr_path))
    return wcs, record
