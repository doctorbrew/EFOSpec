"""Prepare separate public/private PESSTOWISE TGZs without uploading data.

The TSV follows the preserved PESSTOWISE column layout, NOT the WISeREP v2
bulk API schema. See docs/guides/wiserep-delivery.md for sources and ingestion steps.
"""

import argparse
import csv
from datetime import date, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import tarfile
from zipfile import ZipFile, ZIP_DEFLATED

from astropy import units as u
from astropy.io import fits
from astropy.time import Time

from .delivery import digest, prepare, inspect_product
from .delivery_identity import reviewed_name, delivery_filename, apply_identity
from .wiserep_tar import write_tar, validate_tar


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
# The handbook identifies the current programme as ePESSTO+; WISeREP records
# confirm this exact source/associated-group spelling. See docs/guides/wiserep-delivery.md.
DEFAULT_SOURCE_GROUP = 'ePESSTO+'
DEFAULT_PRIVATE_GROUPS = ('ePESSTO+',)
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
        hdus, *_ = inspect_product(product)
        h = hdus[0].header
        delivery_filename(product, h, h['OBJECT'])
        hdus.close()
        if h.get('FILETYPE') != 22208:
            raise ValueError('Select flux-calibrated _f.fits products: ' + product.name)
        rows.append(dict(
            product=os.path.relpath(product, output.parent), sha256=digest(product),
            object=h.get('OBJECT', ''), delivery_object=None, identity_evidence='', observers='', reducers='', reviewer='',
            review_notes='', source_group=DEFAULT_SOURCE_GROUP, reduction_date='', spectrum_type='Object',
            **{key: False for key in REVIEW_FIELDS}, visibility=None,
            associated_groups=[], proprietary_until=None,
            quality=h.get('QUALITY', ''), iau_name=None, object_type_id=None,
            redshift=None, host=None, related_files=[],
        ))
    if not rows:
        raise ValueError('Select at least one spectrum')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(dict(observing_night=night,
                       private_defaults=dict(associated_groups=list(DEFAULT_PRIVATE_GROUPS)),
                       spectra=rows), stream, indent=2)
        stream.write('\n')
    return output


def _legacy_row(row, header, names, related, *, tgz=False):
    stamp = Time(header['DATE-OBS'], format='isot', scale='utc')
    stamp.precision = 3 if tgz else 6
    day, ut = stamp.isot.split('T')
    slit = str(header['SLIT'])
    if slit.lower().startswith('slit'):
        slit = slit[4:]
    # 31 is the EFOSC instrument ID used by the preserved PESSTOWISE script.
    # TGZ reproduces the examples' FILTER-in-Grating convention. ZIP keeps the
    # literal grating field unknown and records FILTER separately in JSON/FITS.
    values = [
        header['OBJECT'], names['ascii'], names['fits'], day, ut, 31,
        row['observers'], int(header['EXPTIME']) if tgz else header['EXPTIME'], slit, row['reducers'],
        row['reduction_date'][:10] if tgz else row['reduction_date'], row['quality'], row['spectrum_type'],
        row['review_notes'], row.get('publish'), row.get('contrib'),
        header.get('AIRMASS'), header.get('DICHROIC'), header['GRISM'], header['FILTER'] if tgz else None,
        header['RA'], header['DEC'], row.get('iau_name'),
        (row.get('object_type_id') or 0) if tgz else row.get('object_type_id'),
        row.get('redshift'), row.get('host'), *related,
    ]
    return ['NULL' if v is None or v == '' else str(v) for v in values]


def package(manifest, destination, *, archive_format='tgz', timestamp=None):
    """Validate selections, then atomically expose independent upload archives."""
    if archive_format not in {'tgz', 'zip'}:
        raise ValueError('archive_format must be tgz or zip')
    tgz = archive_format == 'tgz'
    packaged_at = Time(timestamp, format='isot', scale='utc') if timestamp else Time.now()
    stamp = packaged_at.to_datetime(timezone=timezone.utc).strftime('%Y%m%d_%H_%M')
    manifest, destination = Path(manifest).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination exists; use a new delivery revision')
    config = json.loads(manifest.read_text())
    _text_checks(config)
    private_defaults = config.get('private_defaults', {})
    if not isinstance(private_defaults, dict):
        raise ValueError('private_defaults must be an object')
    night = _night(config['observing_night'])
    rows = config['spectra']
    if not rows:
        raise ValueError('No spectra selected')
    selected, attachments, names_seen, hashes_seen = [], [], set(), {}
    source_hashes = {}
    qualities = {}

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
        if row.get('visibility') == 'private' and (
                'associated_groups' not in row or row['associated_groups'] == []):
            row['associated_groups'] = private_defaults.get('associated_groups', [])
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
        if tgz:
            previous = qualities.setdefault(row.get('visibility'), row['quality'])
            if previous != row['quality']:
                raise ValueError('TGZ requires one quality per access class; use separate manifests')
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
        name = reviewed_name(row, h)
        filename = delivery_filename(source, h, name)
        stem = Path(filename).stem
        names = dict(fits=filename, ascii=stem + '.asci',
                     errors=stem + '-errors.txt', metadata=stem + '-metadata.json')
        for member_name in names.values():
            reserve(member_name)
        related = row.pop('related_files', [])
        if not isinstance(related, list) or len(related) > 2:
            raise ValueError('related_files permits at most two reviewed plot/2D files')
        files = []
        roles = set()
        for item in related:
            if item.get('role') not in {'plot', '2d'}:
                raise ValueError('Related file role must be plot or 2d')
            if tgz and item['role'] in roles:
                raise ValueError('TGZ supports one plot and one calibrated 2D attachment per spectrum')
            roles.add(item['role'])
            path = (manifest.parent / item['path']).resolve()
            if item['role'] == '2d' and path.suffix.lower() != '.fits':
                raise ValueError('Related 2D product must be a FITS file')
            if tgz and item['role'] == '2d':
                with fits.open(path) as hdus:
                    if (hdus[0].data is None or hdus[0].data.ndim != 2 or
                            u.Unit(hdus[0].header.get('BUNIT', '')) != u.Unit('erg / (s cm2 Angstrom)')):
                        raise ValueError('TGZ needs a calibrated primary 2D image, not native PypeIt spec2d')
            if item['role'] == 'plot' and path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.pdf', '.ps'}:
                raise ValueError('Related plot must be PNG, JPG, PDF or PS')
            if name != h['OBJECT'] and item['role'] == 'plot':
                raise ValueError('Identity correction: omit plots and regenerate/review their visible labels separately')
            if name != h['OBJECT'] and item['role'] == '2d':
                ah = fits.getheader(path)
                if ah.get('OBJECT') != h['OBJECT'] or ah.get('DATE-OBS') != h['DATE-OBS']:
                    raise ValueError('2D attachment identity/exposure mismatch')
            register(path, item['sha256'], row.get('visibility'))
            target = filename.replace('_f.fits', '_2df.fits') if name != h['OBJECT'] and item['role'] == '2d' else path.name
            reserve(target)
            files.append((path, item['role'], target))
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
            for path, role, target in related:
                copied = folder / target
                shutil.copyfile(path, copied)
                if role == '2d' and header['OBJECT'] != row['object']:
                    with fits.open(copied, mode='update') as attached:
                        apply_identity(attached[0].header, header['OBJECT'], row)
                        for hdu in attached:
                            hdu.add_checksum()
                related_names.append(target)
                related_records.append(dict(filename=target, role=role, source_sha256=digest(path), sha256=digest(copied)))
            record = json.loads((original / 'metadata.json').read_text())
            record.update(observing_night=night.isoformat(), related_files=related_records,
                          archive_ingestion=(
                              'PESSTOWISE TGZ matching supplied examples; local format validation only. '
                              'Share the separate public/private TGZ with the intended ingest team. '
                              'No upload performed.' if tgz else HANDOFF_NOTE.strip()),
                          files={name: digest(folder / name) for key, name in names.items() if key != 'metadata'})
            (folder / names['metadata']).write_text(json.dumps(record, indent=2) + '\n')
            if tgz:
                by_role = {role: target for path, role, target in related}
                related_names = [by_role.get('plot'), by_role.get('2d')]
            tables.setdefault(visibility, []).append(_legacy_row(
                row, header, names, related_names + [None] * (2 - len(related_names)), tgz=tgz))
            access.setdefault(visibility, []).append(dict(
                fits=names['fits'], object=header['OBJECT'], source_group=row['source_group'],
                associated_groups=row['associated_groups'], proprietary_until=row.get('proprietary_until')))
        for visibility, table in tables.items():
            folder = exported / visibility
            if not tgz:
                with (folder / 'pesstowise-metadata.tsv').open('w', newline='') as stream:
                    writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
                    writer.writerow(LEGACY_COLUMNS)
                    writer.writerows(table)
            (folder / 'access.json').write_text(json.dumps(dict(
                visibility=visibility, observing_night=night.isoformat(), spectra=access[visibility]), indent=2) + '\n')
            introduction = (
                'Local audit sidecars; share the separate TGZ. It matches the supplied PESSTOWISE '
                'layout, including the defaults line. Masks remain in these audit FITS; the TGZ '
                'contains primary-only four-band FITS. No upload performed.\n' if tgz else
                HANDOFF_NOTE + 'The TSV uses one header row; no legacy defaults row.\n')
            (folder / 'README.txt').write_text(introduction +
                'ASCII: header-free wavelength in air Angstrom, flux in erg/s/cm2/Angstrom '
                '(coefficient 1); topocentric observed frame. Error sidecars contain statistical '
                'sigma only. Invalid samples are omitted from ASCII, not filled or resampled. '
                'FITS retains all four bands and masks. No extinction/telluric correction '
                'or final-quality claim is added. Inspect the original correction keywords.\n')
            files = sorted(folder.iterdir())
            (folder / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in files))
            if tgz:
                base = f'pessto_{stamp}_{qualities[visibility]}_upload'
                archive = exported / f'{base}_{visibility}.tgz'
                result = write_tar(folder, staging / f'tar-{visibility}', archive,
                                   table, base + '.txt', packaged_at.unix)
                result['archive'] = archive.name
                result['sha256'] = digest(archive)
                (folder / 'tar-validation.json').write_text(json.dumps(result, indent=2) + '\n')
            else:
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
    build = commands.add_parser('build', help='Build reviewed public/private TGZs; never upload')
    build.add_argument('manifest', type=Path)
    build.add_argument('destination', type=Path)
    build.add_argument('--format', choices=('tgz', 'zip'), default='tgz')
    build.add_argument('--timestamp', help='UTC packaging time for reproducible filenames (ISO format)')
    validate = commands.add_parser('validate', help='Check existing PESSTOWISE TGZ layout and spectra')
    validate.add_argument('--strict', action='store_true', help='Require consistent delivery identities and calibrated product names')
    validate.add_argument('archives', type=Path, nargs='+')
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            for archive in args.archives:
                print(json.dumps(validate_tar(archive, strict=args.strict)))
            return
        output = (init_manifest(args.night, args.products, args.output) if args.command == 'init'
                  else package(args.manifest, args.destination,
                               archive_format=args.format, timestamp=args.timestamp))
    except (ValueError, KeyError, TypeError, OSError, tarfile.TarError) as error:
        parser.exit(2, f'Packaging failed: {error}\n')
    print(output)


if __name__ == '__main__':
    main()
