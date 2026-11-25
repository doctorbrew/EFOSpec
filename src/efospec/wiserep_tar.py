"""The PESSTOWISE TGZ contract observed in the four supplied October examples."""
import io
from pathlib import Path
import tarfile

import numpy as np
from astropy import units as u
from astropy.io import fits
from .delivery_identity import delivery_filename


# Preserve even the legacy trailing space and the short (21-field) defaults row.
HEADER = ('Obj-name\tAscii-filename\tFITS-filename\tObs-date [YYYY-MM-DD]\t'
          'Obs-UT [HH:MM:SS]\tInst-Id\tObserver/s\tExptime\tSlit\tReducer\t'
          'Reduction-date\tQuality [Rapid/Final/Low/Med/High] \t'
          'Spec-Type [Object/Host/Sky/Arcs]\tSpec-Remarks\tPublish\tContrib\t'
          'Airmass\tDichroic\tGrism\tGrating\tObj-RA\tObj-DEC\tIAU-name\t'
          'Obj-type-Id\tRedshift\tHost\tRelated-file1\tRelated-file2')
DEFAULTS = '\t'.join(['[NULL]', '[NULL]', '[Unknown]', '[0]', '[0]',
                      '[Unknown]', '[Obs-date]'] + ['[NULL]'] * 14)


def primary_copy(source, destination):
    """Make a single-HDU legacy reader copy, retaining the four scientific bands."""
    with fits.open(source) as hdus:
        primary = hdus[0].copy()
    h = primary.header
    h['BUNIT'] = 'erg/cm2/s/Angstrom'
    h['CD1_1'] = h['CDELT1']
    h['WCSDIM'] = 3
    h['WAT0_001'] = 'system=equispec'
    h['WAT1_001'] = 'wtype=linear label=Wavelength units=angstroms'
    h['DC-FLAG'] = 0
    for axis in (1, 2, 3):
        h[f'LTM{axis}_{axis}'] = 1.0
    for axis in (2, 3):
        h[f'CTYPE{axis}'] = 'LINEAR'
        h[f'CD{axis}_{axis}'] = 1.0
        h[f'WAT{axis}_001'] = 'wtype=linear'
    # Do not fabricate IRAF aperture coordinates or replace PypeIt BANDID labels.
    h['HISTORY'] = 'PESSTOWISE primary-only delivery; validity masks retained in local audit FITS.'
    primary.writeto(destination, checksum=True)


def write_tar(source, staging, archive, table, metadata_name, timestamp):
    """Keep JSON/error/checksum sidecars local; archive exactly the referenced files."""
    staging.mkdir()
    metadata = staging / metadata_name
    metadata.write_text(HEADER + '\n' + DEFAULTS + '\n' +
                        ''.join('\t'.join(row) + '\n' for row in table))
    members = {metadata_name: metadata}
    for row in table:
        fits_name, ascii_name = row[2], row[1]
        primary_copy(source / fits_name, staging / fits_name)
        members[fits_name] = staging / fits_name
        samples = np.loadtxt(source / ascii_name, ndmin=2)
        np.savetxt(staging / ascii_name, samples, fmt='%.17e', delimiter='\t')
        members[ascii_name] = staging / ascii_name
        for name in row[26:28]:
            if name != 'NULL':
                members[name] = source / name
    with tarfile.open(archive, 'w:gz', format=tarfile.USTAR_FORMAT) as tar:
        for name, path in sorted(members.items()):
            info = tar.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mode = 0o644
            info.mtime = int(timestamp)
            with path.open('rb') as stream:
                tar.addfile(info, stream)
    return validate_tar(archive, strict=True)


def validate_tar(path, *, strict=False):
    """Read without extraction; check layout, file references and ASCII/FITS agreement.

    Accept the source examples' macOS AppleDouble files but never create them.
    This is a local format check, not a remote-server acceptance test.
    """
    with tarfile.open(path, 'r:gz') as tar:
        members = {}
        ignored = 0
        for member in tar:
            if (not member.isfile() or '/' in member.name or '\\' in member.name
                    or member.name in members or member.name in {'.', '..'}):
                raise ValueError('Unsafe or duplicate TGZ member: ' + member.name)
            if member.name.startswith('._'):
                ignored += 1
                continue
            members[member.name] = member
        tables = [n for n in members if n.startswith('pessto_') and n.endswith('_upload.txt')]
        if len(tables) != 1:
            raise ValueError('Expected exactly one pessto_*_upload.txt table')
        lines = tar.extractfile(members[tables[0]]).read().decode('utf-8').splitlines()
        if len(lines) < 3 or lines[:2] != [HEADER, DEFAULTS]:
            raise ValueError('PESSTOWISE header/defaults mismatch or empty table')
        referenced = {tables[0]}
        spectra = set()
        for line in lines[2:]:
            row = line.split('\t')
            if len(row) != 28 or row[5] != '31':
                raise ValueError('Expected 28-column EFOSC spectrum row')
            if row[2] in spectra:
                raise ValueError('Duplicate FITS spectrum row')
            spectra.add(row[2])
            names = [row[1], row[2]] + [n for n in row[26:28] if n != 'NULL']
            if any(n not in members for n in names):
                raise ValueError('Metadata references missing archive files')
            referenced.update(names)
            samples = np.loadtxt(io.BytesIO(tar.extractfile(members[row[1]]).read()), ndmin=2)
            if (samples.shape[1] != 2 or len(samples) < 2 or not np.isfinite(samples).all()
                    or not (np.diff(samples[:, 0]) > 0).all()):
                raise ValueError('Expected increasing finite two-column ASCII')
            with fits.open(io.BytesIO(tar.extractfile(members[row[2]]).read())) as hdus:
                h, data = hdus[0].header, hdus[0].data
                if len(hdus) != 1 or data is None or data.ndim != 3 or data.shape[:2] != (4, 1):
                    raise ValueError('Expected primary-only four-band FITS')
                if h.get('CTYPE1') != 'LINEAR' or not np.isfinite(h['CD1_1']) or h['CD1_1'] <= 0:
                    raise ValueError('Expected increasing linear FITS wavelength grid')
                if h['BUNIT'] != 'erg/cm2/s/Angstrom' and u.Unit(h['BUNIT']) != u.Unit('erg / (s cm2 Angstrom)'):
                    raise ValueError('Unexpected FITS flux units')
                if h.get('WAT1_001') != 'wtype=linear label=Wavelength units=angstroms':
                    raise ValueError('Missing legacy Angstrom wavelength descriptor')
                if strict:
                    if h.get('OBJECT') != row[0] or (row[22] != 'NULL' and row[22] != row[0]):
                        raise ValueError('Upload table/FITS identity mismatch')
                    if row[2] != delivery_filename(Path(row[2]), h, row[0]) or row[1] != row[2][:-5] + '.asci':
                        raise ValueError('Noncanonical or inconsistent delivery filenames')
                    if (h.get('FILETYPE') != 22208 or h.get('CUNIT1') != 'Angstrom'
                            or h.get('WAVEMED') != 'air' or h.get('SPECSYS') != 'TOPOCENT'
                            or h.get('WAVEVAL') is False or h.get('FLXVALID') is False
                            or str(h.get('FLUXCAL', '')).upper() in {'NONE', 'COUNTS', 'UNCALIBRATED'}
                            or h.get('EPSTATUS') == 'PROVISIONAL' or h.get('QUALITY') == 'Provisional'):
                        raise ValueError('Not a calibrated release-ready EFOSpec product')
                    if samples[:, 0].min() < 1000 or samples[:, 0].max() > 30000:
                        raise ValueError('Implausible EFOSC Angstrom wavelengths')
                for hdu in hdus:
                    if ('CHECKSUM' in hdu.header and hdu.verify_checksum() != 1
                            or 'DATASUM' in hdu.header and hdu.verify_datasum() != 1):
                        raise ValueError('FITS checksum failure')
                pixel = (samples[:, 0] - h['CRVAL1']) / h['CD1_1'] + h['CRPIX1'] - 1
                index = np.rint(pixel).astype(int)
                if not ((index >= 0) & (index < data.shape[-1])).all():
                    raise ValueError('ASCII wavelengths outside FITS grid')
                if strict and (not np.isfinite(data[3, 0, index]).all()
                               or not (data[3, 0, index] > 0).all()):
                    raise ValueError('Invalid uncertainty for delivered ASCII samples')
                if (not np.allclose(pixel, index, rtol=0, atol=1e-5)
                        or not np.allclose(samples[:, 1], data[0, 0, index], rtol=1e-6, atol=0)):
                    raise ValueError('ASCII/FITS spectrum mismatch')
        if set(members) != referenced:
            raise ValueError('Unreferenced files in upload tarball')
        return dict(archive=str(path), spectra=len(spectra), files=len(members),
                    ignored_appledouble=ignored, format='PESSTOWISE TGZ', strict=strict, valid=True)
