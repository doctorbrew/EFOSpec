import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from astropy.io import fits
from astropy.time import Time

from efospec.delivery import digest
from efospec.wiserep import init_manifest, package, main
from functools import partial

zip_package = partial(package, archive_format="zip")


@pytest.fixture
def reviewed(tmp_path):
    rows = []
    for name, visibility in [('AT2026public', 'public'), ('AT2026private', 'private')]:
        h = fits.Header(dict(
            OBJECT=name, INSTRUME='EFOSC', FILETYPE=22208, WAVEMED='air',
            SPECSYS='TOPOCENT', CTYPE1='LINEAR', CUNIT1='Angstrom', CRVAL1=4000.,
            CRPIX1=1., CDELT1=5.5, BUNIT='erg / (s cm2 Angstrom)', EXPTIME=100.5,
            RA=10., DEC=-20., GRISM='Gr13', FILTER='Free', SLIT='slit1.0',
            EPSTATUS='EXPERIMENTAL', QUALITY='Rapid', WAVEVAL=True, FLXVALID=True))
        h['DATE-OBS'] = '2026-11-11T02:34:56.789'
        h['MJD-OBS'] = Time(h['DATE-OBS']).mjd
        data = np.ones((4, 1, 5)) * 1e-16
        data[0, 0, 2] = -2e-17
        mask = np.ones(data.shape, dtype=np.uint8)
        mask[:, :, 1] = 0
        product = tmp_path / f'{name}_f.fits'
        fits.HDUList([fits.PrimaryHDU(data, h), fits.ImageHDU(mask, name='VALID')]).writeto(product, checksum=True)
        rows.append(dict(
            product=product.name, sha256=digest(product), object=name,
            observers='Test Observer', reducers='Test Reducer', reviewer='Reviewer',
            review_notes='Synthetic review', source_group='Test team',
            reduction_date='2026-11-12T13:00:00', spectrum_type='Object',
            identity_reviewed=True, wavelength_reviewed=True, flux_reviewed=True,
            release_authorized=True, quality='Rapid', visibility=visibility,
            associated_groups=['Restricted team'] if visibility == 'private' else [],
            proprietary_until='2099-01-01T00:00:00' if visibility == 'private' else None,
        ))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(observing_night='2026-11-10', spectra=rows)))
    return manifest, rows


def rewrite(manifest, rows, **extra):
    manifest.write_text(json.dumps(dict(observing_night='2026-11-10', spectra=rows, **extra)))


def test_split_roundtrip_and_metadata(reviewed):
    manifest, rows = reviewed
    sources = {manifest.parent / row['product']: row['sha256'] for row in rows}
    output = zip_package(manifest, manifest.parent / 'out')
    for visibility, other in [('public', 'private'), ('private', 'public')]:
        archive = output / f'efospec_2026-11-10_upload_{visibility}.zip'
        with ZipFile(archive) as zipped:
            assert zipped.testzip() is None
            assert not any(other in name for name in zipped.namelist())
            table = list(csv.reader(io.StringIO(zipped.read('pesstowise-metadata.tsv').decode()), delimiter='\t'))
            assert len(table) == 2 and all(len(r) == 28 for r in table)
            row = dict(zip(table[0], table[1]))
            assert row['Inst-Id'] == '31'
            assert row['Exptime'] == '100.5'  # no truncation
            assert row['Slit'] == '1.0'
            assert row['Obs-UT [HH:MM:SS]'] == '02:34:56.789000'
            assert row['Grating'] == 'NULL'  # Free filter is not a grating
            assert row['Redshift'] == row['Obj-type-Id'] == 'NULL'
            access = json.loads(zipped.read('access.json'))
            assert access['visibility'] == visibility
            assert len(access['spectra']) == 1
            ascii_data = np.loadtxt(io.BytesIO(zipped.read(row['Ascii-filename'])))
            assert ascii_data.shape == (4, 2)
            np.testing.assert_array_equal(ascii_data[:, 0], [4000, 4011, 4016.5, 4022])
            assert ascii_data[1, 1] == -2e-17
            with fits.open(io.BytesIO(zipped.read(row['FITS-filename'])), checksum=True) as hdus:
                for hdu in hdus:
                    assert hdu.verify_checksum() == hdu.verify_datasum() == 1
                np.testing.assert_array_equal(hdus[0].data, fits.getdata(manifest.parent / row['FITS-filename']))
                assert hdus[0].header['WAVEMED'] == 'air'
                assert hdus[0].header['EPSTATUS'] == 'EXPERIMENTAL'
                assert hdus[0].header['OBSERVER'] == 'Test Observer'
                assert hdus[0].header['REDUCER'] == 'Test Reducer'
                assert hdus[0].header['DATE-RED'] == '2026-11-12T13:00:00'
                if visibility == 'private':
                    assert hdus[0].header['WISEREP PROPRIETARY UNTIL'] == '2099-01-01T00:00:00'
            if visibility == 'public':
                for name in zipped.namelist():
                    assert b'AT2026private' not in zipped.read(name)
                    assert b'Restricted team' not in zipped.read(name)
            for line in zipped.read('SHA256SUMS').decode().splitlines():
                from hashlib import sha256
                checksum, filename = line.split('  ', 1)
                assert sha256(zipped.read(filename)).hexdigest() == checksum
    assert (output / 'efospec_2026-11-10_upload_private.zip').stat().st_mode & 0o777 == 0o600
    assert all(digest(path) == before for path, before in sources.items())


@pytest.mark.parametrize('changes', [
    {'visibility': None}, {'release_authorized': False}, {'flux_reviewed': False},
    {'quality': 'Final'}, {'observers': 'Name\tother'}, {'review_notes': 'a\nb'},
    {'sha256': 'bad'}, {'redshift': float('nan')}, {'object_type_id': True},
    {'visibility': 'private', 'associated_groups': []},
    {'visibility': 'private', 'associated_groups': ['team'], 'proprietary_until': '2020-01-01T00:00:00'},
    {'visibility': 'public', 'associated_groups': ['Restricted team']},
    {'object': 'DifferentObject'},
])
def test_invalid_review_is_atomic(reviewed, changes):
    manifest, rows = reviewed
    rows[0].update(changes)
    rewrite(manifest, rows)
    with pytest.raises(ValueError):
        zip_package(manifest, manifest.parent / 'out')
    assert not (manifest.parent / 'out').exists()
    assert not list(manifest.parent.glob('.wiserep-*'))


def test_content_cannot_cross_access_classes(reviewed):
    manifest, rows = reviewed
    copied = manifest.parent / 'renamed.fits'
    copied.write_bytes((manifest.parent / rows[0]['product']).read_bytes())
    rows[1].update(product=copied.name, sha256=digest(copied))
    rewrite(manifest, rows)
    with pytest.raises(ValueError, match='across public/private'):
        zip_package(manifest, manifest.parent / 'out')


def test_product_cannot_overwrite_package_metadata(reviewed):
    manifest, rows = reviewed
    source = manifest.parent / 'access.json'
    source.write_bytes((manifest.parent / rows[0]['product']).read_bytes())
    rows[0].update(product=source.name, sha256=digest(source))
    rewrite(manifest, rows)
    with pytest.raises(ValueError, match='.fits filenames'):
        zip_package(manifest, manifest.parent / 'out')


def test_related_files_are_explicit_and_hashed(reviewed):
    manifest, rows = reviewed
    plot = manifest.parent / 'classification.png'
    plot.write_bytes(b'fixture attachment')
    rows[1]['related_files'] = [dict(path=plot.name, role='plot', sha256=digest(plot))]
    rewrite(manifest, rows)
    output = zip_package(manifest, manifest.parent / 'out')
    with ZipFile(output / 'efospec_2026-11-10_upload_private.zip') as z:
        assert z.read(plot.name) == plot.read_bytes()
        assert plot.name in z.read('pesstowise-metadata.tsv').decode()
    with ZipFile(output / 'efospec_2026-11-10_upload_public.zip') as z:
        assert plot.name not in z.namelist()
    plot.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        zip_package(manifest, manifest.parent / 'second')


def test_init_requires_review_and_never_overwrites(reviewed):
    manifest, rows = reviewed
    output = init_manifest('2026-11-10', [manifest.parent / rows[0]['product']], manifest.parent / 'review.json')
    cfg = json.loads(output.read_text())
    assert cfg['spectra'][0]['source_group'] == 'ePESSTO+'
    assert cfg['private_defaults']['associated_groups'] == ['ePESSTO+']
    assert cfg['spectra'][0]['associated_groups'] == []
    assert cfg['spectra'][0]['visibility'] is None
    assert cfg['spectra'][0]['release_authorized'] is False
    with pytest.raises(ValueError):
        zip_package(output, manifest.parent / 'out')
    with pytest.raises(FileExistsError):
        init_manifest('2026-11-10', [manifest.parent / rows[0]['product']], output)


def test_manifest_group_defaults_apply_only_to_private_spectra(reviewed):
    manifest, rows = reviewed
    output = init_manifest('2026-11-10', [manifest.parent / r['product'] for r in rows],
                           manifest.parent / 'defaults.json')
    config = json.loads(output.read_text())
    for initialized, reviewed_row in zip(config['spectra'], rows):
        initialized.update({k: v for k, v in reviewed_row.items()
                            if k not in {'source_group', 'associated_groups'}})
    # Retain the generated private default, with no per-spectrum override.
    for groups, expected in [(None, 'ePESSTO+'), (['Other collaboration'], 'Other collaboration')]:
        config['spectra'][1]['associated_groups'] = groups or []
        output.write_text(json.dumps(config))
        destination = package(output, manifest.parent / expected)
        for access in ('public', 'private'):
            row = next(r for r in rows if r['visibility'] == access)
            header = fits.getheader(destination / access / row['product'])
            assert header['WISEREP SOURCE GROUP'] == 'ePESSTO+'
            if access == 'private':
                assert header['WISEREP ASSOCIATED GROUPS'] == expected
            else:
                assert 'WISEREP ASSOCIATED GROUPS' not in header
    config['spectra'][1]['associated_groups'] = ''
    output.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='Invalid associated_groups'):
        package(output, manifest.parent / 'invalid-groups')


def test_single_class_no_empty_archive_and_no_overwrite(reviewed):
    manifest, rows = reviewed
    rewrite(manifest, rows[:1])
    output = zip_package(manifest, manifest.parent / 'out')
    assert len(list(output.glob('*.zip'))) == 1
    with pytest.raises(ValueError, match='exists'):
        zip_package(manifest, output)


def test_wrong_night_rejected(reviewed):
    manifest, rows = reviewed
    manifest.write_text(json.dumps(dict(observing_night='2026-10-28', spectra=rows)))
    with pytest.raises(ValueError, match='outside'):
        zip_package(manifest, manifest.parent / 'out')


def test_cli_failure_has_no_traceback(reviewed, capsys):
    manifest, rows = reviewed
    rows[0]['visibility'] = None
    rewrite(manifest, rows)
    with pytest.raises(SystemExit) as exc:
        main(['build', str(manifest), str(manifest.parent / 'out')])
    assert exc.value.code == 2
    assert 'Packaging failed' in capsys.readouterr().err


def test_public_copy_replaces_old_private_delivery_headers(reviewed):
    manifest, rows = reviewed
    source = manifest.parent / rows[0]['product']
    with fits.open(source, mode='update', checksum=True) as hdus:
        hdus[0].header['HIERARCH WISEREP ASSOCIATED GROUPS'] = 'Old secret group'
        hdus[0].header['HIERARCH WISEREP PROPRIETARY UNTIL'] = '2099-01-01T00:00:00'
    rows[0]['sha256'] = digest(source)
    rewrite(manifest, rows)
    out = zip_package(manifest, manifest.parent / 'out')
    h = fits.getheader(out / 'public' / source.name)
    assert 'WISEREP ASSOCIATED GROUPS' not in h
    assert 'WISEREP PROPRIETARY UNTIL' not in h
    assert h['PESSTO ACCESS'] == 'public'
    assert 'WISEREP ASSOCIATED GROUPS' in fits.getheader(source)


@pytest.mark.parametrize('key,value', [
    ('WAVEVAL', False), ('FLXVALID', False), ('EPSTATUS', 'PROVISIONAL'),
    ('BUNIT', 'count'), ('WAVEMED', 'vacuum'), ('MJD-OBS', 0.),
])
def test_unusable_products_are_not_silently_packaged(reviewed, key, value):
    manifest, rows = reviewed
    source = manifest.parent / rows[0]['product']
    with fits.open(source, mode='update', checksum=True) as hdus:
        hdus[0].header[key] = value
    rows[0]['sha256'] = digest(source)
    rewrite(manifest, rows)
    with pytest.raises(ValueError):
        zip_package(manifest, manifest.parent / 'out')
    assert not (manifest.parent / 'out').exists()


def test_tgz_matches_supplied_preamble_and_minimal_members(reviewed):
    import tarfile
    from efospec.wiserep_tar import validate_tar
    manifest, rows = reviewed
    before = {row['product']: digest(manifest.parent / row['product']) for row in rows}
    out = package(manifest, manifest.parent / 'tgz', timestamp='2026-11-18T14:03:00')
    preamble = (Path(__file__).parent / 'fixtures/pesstowise-upload-preamble.txt').read_bytes()
    for visibility, other in [('public', 'private'), ('private', 'public')]:
        archive = out / f'pessto_20261118_14_03_Rapid_upload_{visibility}.tgz'
        assert validate_tar(archive)['spectra'] == 1
        with tarfile.open(archive) as tar:
            assert len(tar.getmembers()) == 3
            assert all(m.isfile() and '/' not in m.name and not m.name.startswith('._') for m in tar)
            table = tar.extractfile('pessto_20261118_14_03_Rapid_upload.txt').read()
            assert table.startswith(preamble)
            row = table.decode().splitlines()[2].split('\t')
            assert len(row) == 28
            assert row[7] == '100'  # legacy table seconds; FITS retains 100.5
            assert row[19] == 'Free' and row[23] == '0'
            assert row[4] == '02:34:56.789' and row[10] == '2026-11-12'
            assert row[26:] == ['NULL', 'NULL']
            ascii_bytes = tar.extractfile(row[1]).read()
            assert all(len(line.split(b'\t')) == 2 for line in ascii_bytes.splitlines())
            with fits.open(io.BytesIO(tar.extractfile(row[2]).read())) as hdus:
                assert len(hdus) == 1
                assert hdus[0].header['EXPTIME'] == 100.5
                assert hdus[0].header['CD1_1'] == hdus[0].header['CDELT1'] == 5.5
                assert hdus[0].header['WAT0_001'] == 'system=equispec'
                assert hdus[0].verify_checksum() == 1
                np.testing.assert_array_equal(hdus[0].data, fits.getdata(manifest.parent / row[2]))
            if visibility == 'public':
                for member in tar:
                    assert b'AT2026private' not in tar.extractfile(member).read()
        with fits.open(out / visibility / row[2]) as audit:
            assert 'VALID' in audit
    assert not list(out.glob('*.zip'))
    assert all(digest(manifest.parent / path) == old for path, old in before.items())


def test_tgz_related_role_columns_and_validation(reviewed):
    import tarfile
    from efospec.wiserep_tar import validate_tar
    manifest, rows = reviewed
    image = manifest.parent / 'target_2df.fits'
    fits.PrimaryHDU(np.ones((3, 4)), fits.Header({'BUNIT': 'erg / (s cm2 Angstrom)'})).writeto(image)
    rows[0]['related_files'] = [dict(path=image.name, role='2d', sha256=digest(image))]
    rewrite(manifest, rows)
    out = package(manifest, manifest.parent / 'tgz')
    archive = next(out.glob('*public.tgz'))
    assert validate_tar(archive)['files'] == 4
    with tarfile.open(archive) as tar:
        table = next(m for m in tar if m.name.endswith('.txt'))
        row = tar.extractfile(table).read().decode().splitlines()[2].split('\t')
        assert row[26:] == ['NULL', image.name]
        assert tar.extractfile(image.name).read() == image.read_bytes()
    # Native PypeIt spec2d is not an already calibrated primary image.
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((3, 4)))]).writeto(image, overwrite=True)
    rows[0]['related_files'][0]['sha256'] = digest(image)
    rewrite(manifest, rows)
    with pytest.raises(ValueError, match='not native PypeIt'):
        package(manifest, manifest.parent / 'bad')


def test_tgz_validator_rejects_broken_file_reference(reviewed):
    import tarfile
    from efospec.wiserep_tar import validate_tar
    manifest, _ = reviewed
    out = package(manifest, manifest.parent / 'tgz')
    broken = manifest.parent / 'broken.tgz'
    with tarfile.open(next(out.glob('*public.tgz'))) as source, tarfile.open(broken, 'w:gz') as dest:
        for member in source:
            if not member.name.endswith('.asci'):
                dest.addfile(member, source.extractfile(member))
    with pytest.raises(ValueError, match='missing'):
        validate_tar(broken)


def test_tgz_failure_keeps_destination_absent(reviewed, monkeypatch):
    import efospec.wiserep as exporter
    manifest, _ = reviewed
    def fail(*args, **kwargs):
        raise ValueError('failed final tar validation')
    monkeypatch.setattr(exporter, 'write_tar', fail)
    with pytest.raises(ValueError, match='final tar validation'):
        package(manifest, manifest.parent / 'tgz')
    assert not (manifest.parent / 'tgz').exists()
    assert not list(manifest.parent.glob('.wiserep-*'))
