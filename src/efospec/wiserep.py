"""Prepare separate, reviewed WISeREP handoff ZIPs without uploading data.

The TSV follows the preserved PESSTOWISE column layout, NOT the WISeREP v2
bulk API schema. See docs/wiserep-delivery.md for sources and ingestion steps.
"""

import argparse
import csv
from datetime import date, timedelta
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from astropy.io import fits
from astropy.time import Time

from .delivery import digest, prepare


LEGACY_COLUMNS = (
    'Obj-name', 'Ascii-filename', 'FITS-filename', 'Obs-date [YYYY-MM-DD]',
    'Obs-UT [HH:MM:SS]', 'Inst-Id', 'Observer/s', 'Exptime', 'Slit', 'Reducer',
    'Reduction-date', 'Quality [Rapid/Final/Low/Med/High]',
    'Spec-Type [Object/Host/Sky/Arcs]', 'Spec-Remarks', 'Publish', 'Contrib',
    'Airmass', 'Dichroic', 'Grism', 'Grating', 'Obj-RA', 'Obj-DEC', 'IAU-name',
    'Obj-type-Id', 'Redshift', 'Host', 'Related-file1', 'Related-file2',
)
REVIEW_FIELDS = ('identity_reviewed', 'wavelength_reviewed', 'flux_reviewed',
                 'release_authorized')
HANDOFF_NOTE = (
    'PESSTOWISE-style collaborator handoff; not a WISeREP v2 bulk payload. '
    'Unzip, inspect the spectra and metadata, and set source group, associated '
    'groups and proprietary period explicitly in WISeREP. ZIP names and FITS '
    'access keywords do not enforce archive permissions. No upload performed. '
    'Private ZIPs are not encrypted.\n'
)


def _night(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('observing_night must be YYYY-MM-DD')
    return parsed


def _safe_name(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', name):
        raise ValueError('Unsafe archive filename: ' + name)
    return name


def _text_checks(value):
    """Do not permit metadata to create extra TSV rows/columns or FITS cards."""
    if isinstance(value, str) and any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Control character in manifest metadata')
    if isinstance(value, dict):
        for item in value.values():
            _text_checks(item)
    if isinstance(value, list):
        for item in value:
            _text_checks(item)


def init_manifest(night, products, output):
    """Inventory explicit flux products; leave release decisions unset."""
    _night(night)
    output = Path(output).resolve()
    rows = []
    for product in products:
        product = Path(product).resolve()
        h = fits.getheader(product)
        if h.get('FILETYPE') != 22208:
            raise ValueError('Select flux-calibrated _f.fits products: ' + product.name)
        rows.append(dict(
            product=os.path.relpath(product, output.parent), sha256=digest(product),
            object=h.get('OBJECT', ''), observers='', reducers='', reviewer='',
            review_notes='', source_group='', reduction_date='', spectrum_type='Object',
            **{key: False for key in REVIEW_FIELDS}, visibility=None,
            associated_groups=[], proprietary_until=None,
            quality=h.get('QUALITY', ''), iau_name=None, object_type_id=None,
            redshift=None, host=None, related_files=[],
        ))
    if not rows:
        raise ValueError('Select at least one spectrum')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(dict(observing_night=night, spectra=rows), stream, indent=2)
        stream.write('\n')
    return output


def _legacy_row(row, header, names, related):
    stamp = Time(header['DATE-OBS'], format='isot', scale='utc')
    stamp.precision = 6
    day, ut = stamp.isot.split('T')
    slit = str(header['SLIT'])
    if slit.lower().startswith('slit'):
        slit = slit[4:]
    # 31 is the EFOSC instrument ID used by the preserved PESSTOWISE script.
    # FILTER is recorded in JSON/FITS, never mislabeled as a grating.
    values = [
        row['object'], names['ascii'], names['fits'], day, ut, 31,
        row['observers'], header['EXPTIME'], slit, row['reducers'],
        row['reduction_date'], row['quality'], row['spectrum_type'],
        row['review_notes'], row.get('publish'), row.get('contrib'),
        header.get('AIRMASS'), header.get('DICHROIC'), header['GRISM'], None,
        header['RA'], header['DEC'], row.get('iau_name'), row.get('object_type_id'),
        row.get('redshift'), row.get('host'), *related,
    ]
    return ['NULL' if v is None or v == '' else str(v) for v in values]


def package(manifest, destination):
    """Validate all selections, then atomically expose independently shareable ZIPs."""
    manifest, destination = Path(manifest).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination exists; use a new delivery revision')
    config = json.loads(manifest.read_text())
    _text_checks(config)
    night = _night(config['observing_night'])
    rows = config['spectra']
    if not rows:
        raise ValueError('No spectra selected')
    selected, attachments, names_seen, hashes_seen = [], [], set(), {}
    source_hashes = {}

    def register(path, expected, visibility):
        actual = digest(path)
        if actual != expected:
            raise ValueError('Reviewed file hash mismatch: ' + path.name)
        if actual in hashes_seen and hashes_seen[actual] != visibility:
            raise ValueError('Same content selected across public/private classes')
        hashes_seen[actual] = visibility
        source_hashes[path] = actual

    def reserve(name):
        _safe_name(name)
        if name.casefold() in names_seen:
            raise ValueError('Duplicate archive filename: ' + name)
        names_seen.add(name.casefold())

    for original in rows:
        row = dict(original)
        source = (manifest.parent / row['product']).resolve()
        if source.suffix.lower() != '.fits':
            raise ValueError('Selected flux products must have .fits filenames')
        row['product'] = str(source)
        register(source, row['sha256'], row.get('visibility'))
        h = fits.getheader(source)
        obs_day = date.fromisoformat(str(h['DATE-OBS'])[:10])
        if obs_day not in {night, night + timedelta(days=1)}:
            raise ValueError('Spectrum is outside the specified observing night')
        if row.get('quality') not in {'Rapid', 'Final', 'Low', 'Med', 'High'}:
            raise ValueError('Explicit spectrum quality required')
        if h.get('QUALITY') and h['QUALITY'] != row['quality']:
            raise ValueError('Quality differs from source FITS; resolve upstream')
        for key in ('iau_name', 'host', 'publish', 'contrib'):
            if row.get(key) is not None and not isinstance(row[key], str):
                raise ValueError(key + ' must be a string or null')
        z = row.get('redshift')
        if z is not None and (type(z) not in (int, float) or not math.isfinite(z) or z <= -1):
            raise ValueError('redshift must be finite and greater than -1, or null')
        kind = row.get('object_type_id')
        if kind is not None and (type(kind) is not int or kind < 0):
            raise ValueError('object_type_id must be an explicit nonnegative integer or null')
        for key in ('CRVAL1', 'CRPIX1', 'CDELT1', 'MJD-OBS'):
            if not math.isfinite(h[key]):
                raise ValueError('Nonfinite FITS metadata: ' + key)
        names = dict(fits=source.name, ascii=source.stem + '.asci',
                     errors=source.stem + '-errors.txt', metadata=source.stem + '-metadata.json')
        for name in names.values():
            reserve(name)
        related = row.pop('related_files', [])
        if not isinstance(related, list) or len(related) > 2:
            raise ValueError('related_files permits at most two reviewed plot/2D files')
        files = []
        for item in related:
            if item.get('role') not in {'plot', '2d'}:
                raise ValueError('Related file role must be plot or 2d')
            path = (manifest.parent / item['path']).resolve()
            if item['role'] == '2d' and path.suffix.lower() != '.fits':
                raise ValueError('Related 2D product must be a FITS file')
            if item['role'] == 'plot' and path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.pdf', '.ps'}:
                raise ValueError('Related plot must be PNG, JPG, PDF or PS')
            register(path, item['sha256'], row.get('visibility'))
            reserve(path.name)
            files.append((path, item['role']))
        selected.append(row)
        attachments.append((names, files))

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.wiserep-', dir=destination.parent))
    try:
        # Reuse the existing science/review checks without changing its interface.
        reviewed_manifest = staging / 'review.json'
        reviewed_manifest.write_text(json.dumps({'spectra': selected}))
        prepared = prepare(reviewed_manifest, staging / 'reviewed')
        exported = staging / 'export'
        exported.mkdir()
        tables, access = {}, {}
        for i, (row, (names, related)) in enumerate(zip(selected, attachments), 1):
            visibility = row['visibility']
            folder = exported / visibility
            folder.mkdir(exist_ok=True, mode=0o700 if visibility == 'private' else 0o755)
            original = prepared / visibility / ('spectrum-%03d' % i)
            for key, source_name in [('fits', 'spectrum.fits'), ('ascii', 'spectrum.ascii'),
                                     ('errors', 'spectrum-with-errors.txt')]:
                shutil.copyfile(original / source_name, folder / names[key])
            with fits.open(folder / names['fits'], mode='update', checksum=True) as hdus:
                h = hdus[0].header
                h['HIERARCH EFOSPEC NIGHT'] = night.isoformat()
                h['HIERARCH WISEREP SOURCE GROUP'] = row['source_group']
                h['HIERARCH WISEREP SPECTRUM TYPE'] = row['spectrum_type']
                h['HIERARCH WISEREP QUALITY'] = row['quality']
                # A newly authorized public copy must not retain an older
                # delivery's private group/embargo instructions.
                for key in ('WISEREP ASSOCIATED GROUPS', 'WISEREP PROPRIETARY UNTIL'):
                    h.remove(key, ignore_missing=True, remove_all=True)
                if visibility == 'private':
                    h['HIERARCH WISEREP ASSOCIATED GROUPS'] = ', '.join(row['associated_groups'])
                    h['HIERARCH WISEREP PROPRIETARY UNTIL'] = row['proprietary_until']
                for hdu in hdus:
                    hdu.add_checksum()
                header = h.copy()
            related_names = []
            related_records = []
            for path, role in related:
                shutil.copyfile(path, folder / path.name)
                related_names.append(path.name)
                related_records.append(dict(filename=path.name, role=role, sha256=digest(path)))
            record = json.loads((original / 'metadata.json').read_text())
            record.update(observing_night=night.isoformat(), related_files=related_records,
                          archive_ingestion=HANDOFF_NOTE.strip(),
                          files={name: digest(folder / name) for key, name in names.items() if key != 'metadata'})
            (folder / names['metadata']).write_text(json.dumps(record, indent=2) + '\n')
            tables.setdefault(visibility, []).append(_legacy_row(
                row, header, names, related_names + [None] * (2 - len(related_names))))
            access.setdefault(visibility, []).append(dict(
                fits=names['fits'], object=row['object'], source_group=row['source_group'],
                associated_groups=row['associated_groups'], proprietary_until=row.get('proprietary_until')))
        for visibility, table in tables.items():
            folder = exported / visibility
            with (folder / 'pesstowise-metadata.tsv').open('w', newline='') as stream:
                writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
                writer.writerow(LEGACY_COLUMNS)
                writer.writerows(table)
            (folder / 'access.json').write_text(json.dumps(dict(
                visibility=visibility, observing_night=night.isoformat(), spectra=access[visibility]), indent=2) + '\n')
            (folder / 'README.txt').write_text(HANDOFF_NOTE +
                'The TSV uses the 28 PESSTOWISE columns with one header row; no legacy defaults row.\n'
                'ASCII: header-free wavelength in air Angstrom, flux in erg/s/cm2/Angstrom '
                '(coefficient 1); topocentric observed frame. Error sidecars contain statistical '
                'sigma only. Invalid samples are omitted from ASCII, not filled or resampled. '
                'FITS retains all four bands and masks. No extinction/telluric correction '
                'or final-quality claim is added. Inspect the original correction keywords.\n')
            files = sorted(folder.iterdir())
            (folder / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in files))
            archive = exported / f'efospec_{night.isoformat()}_upload_{visibility}.zip'
            with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as zipped:
                for path in sorted(folder.iterdir()):
                    zipped.write(path, arcname=path.name)
            with ZipFile(archive) as zipped:
                if zipped.testzip() is not None:
                    raise ValueError('ZIP integrity check failed')
            if visibility == 'private':
                archive.chmod(0o600)
        for source, expected in source_hashes.items():
            if digest(source) != expected:
                raise ValueError('Source changed while packaging')
        os.rename(exported, destination)
    finally:
        shutil.rmtree(staging)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    initial = commands.add_parser('init', help='Inventory explicit products; review flags remain false')
    initial.add_argument('night')
    initial.add_argument('products', nargs='+', type=Path)
    initial.add_argument('--output', required=True, type=Path)
    build = commands.add_parser('build', help='Build reviewed public/private ZIPs; never upload')
    build.add_argument('manifest', type=Path)
    build.add_argument('destination', type=Path)
    args = parser.parse_args(argv)
    try:
        output = (init_manifest(args.night, args.products, args.output) if args.command == 'init'
                  else package(args.manifest, args.destination))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f'Packaging failed: {error}\n')
    print(output)


if __name__ == '__main__':
    main()
