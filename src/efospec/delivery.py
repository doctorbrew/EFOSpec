"""Offline, explicitly reviewed EFOSpec delivery copies; never upload or re-reduce."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from astropy.io import fits
from astropy import units as u
from astropy.time import Time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(manifest, destination):
    manifest, destination = Path(manifest).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination exists; use a new delivery revision')
    config = json.loads(manifest.read_text())
    rows = config['spectra']
    if not rows:
        raise ValueError('No spectra selected')
    prepared, seen = [], set()
    for row in rows:
        for key in ('object', 'observers', 'reducers', 'reviewer', 'review_notes',
                    'source_group', 'reduction_date', 'spectrum_type'):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip() or value.upper() in {'UNKNOWN','NULL','TODO'} or '\n' in value:
                raise ValueError('Missing or invalid '+key)
        Time(row['reduction_date'], format='isot', scale='utc')
        if row['spectrum_type'] not in {'Object', 'Host', 'Sky', 'Arcs'}:
            raise ValueError('Unsupported spectrum_type')
        for key in ('identity_reviewed', 'wavelength_reviewed', 'flux_reviewed', 'release_authorized'):
            if row.get(key) is not True:
                raise ValueError('Review required: '+key)
        visibility = row.get('visibility')
        groups = row.get('associated_groups', [])
        if visibility not in {'public','private'}:
            raise ValueError('Explicit public/private visibility required')
        if not isinstance(groups, list) or any(not isinstance(g,str) or not g.strip() for g in groups):
            raise ValueError('Invalid associated_groups')
        if visibility == 'private':
            if not groups or not row.get('proprietary_until'):
                raise ValueError('Private delivery requires groups and proprietary_until')
            if Time(row['proprietary_until'], format='isot', scale='utc') <= Time.now():
                raise ValueError('Private proprietary_until must be in the future')
        elif row.get('proprietary_until') or groups:
            raise ValueError('Public delivery must not carry private access settings')
        source = (manifest.parent / row['product']).resolve()
        if digest(source) != row.get('sha256'):
            raise ValueError('Reviewed product hash mismatch')
        if source in seen:
            raise ValueError('Duplicate spectrum, including across access classes')
        seen.add(source)
        with fits.open(source, checksum=True) as hdus:
            hdus.verify('exception')
            for hdu in hdus:
                if ('CHECKSUM' in hdu.header and hdu.verify_checksum() != 1) or ('DATASUM' in hdu.header and hdu.verify_datasum() != 1):
                    raise ValueError('FITS checksum verification failed')
            h, data = hdus[0].header, hdus[0].data
            if data is None or data.ndim != 3 or data.shape[:2] != (4,1) or 'VALID' not in hdus:
                raise ValueError('Expected EFOSpec four-band FITS with VALID masks')
            if h.get('FILETYPE') != 22208 or h.get('WAVEMED') != 'air' or h.get('SPECSYS') != 'TOPOCENT':
                raise ValueError('Unsupported product or wavelength convention')
            if h.get('EPSTATUS') == 'PROVISIONAL' or h.get('QUALITY') == 'Provisional' or h.get('WAVEVAL') is False or h.get('FLXVALID') is False:
                raise ValueError('Provisional or failed calibration is not release ready')
            for key in ('DATE-OBS','MJD-OBS','EXPTIME','RA','DEC','OBJECT','INSTRUME','GRISM','FILTER','SLIT','BUNIT','CRVAL1','CRPIX1','CDELT1'):
                if key not in h:
                    raise ValueError('Missing FITS metadata: '+key)
            if row['object'] != h['OBJECT']:
                raise ValueError('Object differs from reviewed FITS; revise identity upstream')
            if h['INSTRUME'].upper() != 'EFOSC':
                raise ValueError('Only NTT/EFOSC products supported')
            utc = Time(h['DATE-OBS'], format='isot', scale='utc')
            if abs(utc.mjd - h['MJD-OBS']) > 1 / 86400:
                raise ValueError('DATE-OBS/MJD-OBS disagree by over one second')
            if not (np.isfinite(h['EXPTIME']) and h['EXPTIME'] > 0 and 0 <= h['RA'] < 360 and -90 <= h['DEC'] <= 90):
                raise ValueError('Invalid exposure or coordinates')
            if h.get('CTYPE1') != 'LINEAR' or h.get('CUNIT1') != 'Angstrom' or h['CDELT1'] <= 0 or h.get('CD1_1',h['CDELT1']) != h['CDELT1']:
                raise ValueError('Expected increasing linear Angstrom grid')
            if u.Unit(h['BUNIT']) != u.Unit('erg / (s cm2 Angstrom)'):
                raise ValueError('Expected unscaled physical flux density')
            valid = hdus['VALID'].data
            if valid.shape != data.shape:
                raise ValueError('Mask shape mismatch')
            wave = h['CRVAL1'] + (np.arange(data.shape[-1])+1-h['CRPIX1'])*h['CDELT1']
            flux, sigma = data[0,0], data[3,0]
            good = (valid[0,0] == 1) & (valid[3,0] == 1) & np.isfinite(wave) & np.isfinite(flux) & np.isfinite(sigma) & (sigma > 0)
            if np.count_nonzero(good) < 2 or not np.all(np.diff(wave[good]) > 0):
                raise ValueError('Insufficient valid samples')
            metadata = {k:h[k] for k in ('OBJECT','DATE-OBS','MJD-OBS','EXPTIME','RA','DEC','INSTRUME','GRISM','FILTER','SLIT','BUNIT','WAVEMED','SPECSYS')}
            metadata.update({k:h.get(k) for k in ('AIRMASS','FLUXCAL','TELLURIC','QUALITY','EPSTATUS','PYPEITV','SENSFUN','ARCREF','EXTRPRI')})
            copied = fits.HDUList([hdu.copy() for hdu in hdus])
        if digest(source) != row['sha256']:
            raise ValueError('Source changed while packaging')
        prepared.append((row, source, copied, wave, flux, sigma, good, metadata))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.delivery-',dir=destination.parent))
    try:
        for i,(row,source,hdus,wave,flux,sigma,good,metadata) in enumerate(prepared,1):
            folder = temp / row['visibility'] / ('spectrum-%03d' % i)
            folder.mkdir(parents=True)
            if row['visibility']=='private':
                (temp/'private').chmod(0o700)
            h = hdus[0].header
            for key,value in {'OBSERVER':row['observers'],'REDUCER':row['reducers'],'DATE-RED':row['reduction_date'],'TELESCOP':'ESO-NTT','HIERARCH PESSTO ACCESS':row['visibility']}.items():
                h[key] = value
            h['HISTORY'] = 'Delivery copy; original status and science arrays retained. Access must be set on archive.'
            hdus.writeto(folder/'spectrum.fits', checksum=True)
            # Header-free two-column import file; full metadata travels alongside it.
            np.savetxt(folder/'spectrum.ascii', np.column_stack((wave[good],flux[good])),fmt='%.17e')
            np.savetxt(folder/'spectrum-with-errors.txt',np.column_stack((wave[good],flux[good],sigma[good])),fmt='%.17e',header='air_A flux_erg_s-1_cm-2_A-1 sigma_same_units; topocentric; statistical errors only')
            record = {k:v for k,v in row.items() if k not in {'product'}}
            record.update(metadata=metadata, original_filename=source.name,
                omitted_samples=int(np.count_nonzero(~good)), retained_samples=int(good.sum()),
                archive_ingestion='NOT VALIDATED: enter metadata and access settings in current service form',
                files={p.name:digest(p) for p in folder.iterdir()})
            (folder/'metadata.json').write_text(json.dumps(record,indent=2)+'\n')
        # No combined metadata index: each access class remains independently shareable.
        (temp/'README.txt').write_text('Share public/ and private/ separately. Metadata JSON is a collaborator handoff, not a service TSV/API payload. Set archive access controls explicitly. No upload performed. Original reduction statuses remain authoritative.\n')
        os.rename(temp,destination)
    except BaseException:
        shutil.rmtree(temp)
        raise
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    print(prepare(args.manifest,args.destination))


if __name__ == '__main__':
    main()
