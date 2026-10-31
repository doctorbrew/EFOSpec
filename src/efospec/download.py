"""Date-selected ESO raw downloads; credentials exist only in request headers."""
from datetime import date, timedelta
import gzip
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlsplit

import requests
from astropy.io import fits
from astropy.io.votable import parse_single_table
from astropy.time import Time

from .inventory import sha256

TAP = 'https://archive.eso.org/tap_obs/sync'
DATALINK = 'https://archive.eso.org/datalink/links'
CALSELECTOR = 'https://archive.eso.org/calselector/v1/associations'
FILES = 'https://dataportal.eso.org/dataPortal/file/'


class DownloadError(ValueError):
    """Safe-to-display error; never includes server bodies or credentials."""


def night_bounds(night):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', night):
        raise DownloadError('Use an observing-night date in YYYY-MM-DD format.')
    day = date.fromisoformat(night)
    return (day.isoformat()+'T12:00:00', (day+timedelta(days=1)).isoformat()+'T12:00:00')


def file_url(identifier):
    if not re.fullmatch(r'EFOSC\.\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3,6}', identifier):
        raise DownloadError('Invalid EFOSC archive identifier.')
    return FILES+identifier


def table_rows(payload):
    try:
        xml = ET.fromstring(payload)
        for element in xml.iter():
            if element.tag.split('}')[-1] == 'INFO' and element.get('name') == 'QUERY_STATUS':
                if element.get('value', '').upper() in {'ERROR', 'OVERFLOW'}:
                    raise DownloadError('ESO query failed or was truncated; narrow the selection.')
        table = parse_single_table(io.BytesIO(payload)).to_table()
        return [{key: '' if str(row[key]) == '--' else str(row[key]) for key in table.colnames}
                for row in table]
    except DownloadError:
        raise
    except Exception:
        raise DownloadError('ESO returned an invalid table response.') from None


class ESOClient:
    def __init__(self, *, public_only=False, environ=None):
        env = os.environ if environ is None else environ
        self.session = requests.Session()
        # Do not pick up unrelated .netrc credentials or implicitly authenticate queries.
        self.session.trust_env = False
        self.token = None if public_only else env.get('ESO_TOKEN')
        username, password = (None, None) if public_only else (env.get('ESO_USERNAME'), env.get('ESO_PASSWORD'))
        if not self.token and bool(username) != bool(password):
            raise DownloadError('Set both ESO_USERNAME and ESO_PASSWORD, or neither.')
        self.auth = (username, password) if username and password else None
        self.auth_mode = 'token' if self.token else 'username_password' if self.auth else 'anonymous'

    def close(self):
        self.session.close()

    def get(self, url, *, params=None, stream=False):
        # Allow only fixed ESO service URLs. Never forward secrets through redirects.
        if url not in (TAP, DATALINK, CALSELECTOR):
            if not url.startswith(FILES) or file_url(url[len(FILES):]) != url:
                raise DownloadError('Refusing an unrecognized download destination.')
        headers = {'Authorization': 'Bearer '+self.token} if self.token else {}
        auth = self.auth if url.startswith(FILES) and not self.token else None
        try:
            response = self.session.get(url, params=params, headers=headers, auth=auth,
                                        stream=stream, timeout=(15, 90), allow_redirects=False)
        except requests.RequestException:
            raise DownloadError('ESO connection failed; rerun to resume completed files.') from None
        if url == DATALINK and response.status_code == 303:
            # DataLink's documented raw-association redirect stays on archive.eso.org.
            location = urlsplit(response.headers.get('Location', ''))
            response.close()
            values = parse_qs(location.query)
            identifier = (params or {}).get('ID', '').removeprefix('ivo://eso.org/ID?')
            expected = {'dp_id': [identifier], 'mode': ['Raw2Raw'], 'responseformat': ['votable']}
            if (location.scheme+'://'+location.netloc+location.path != CALSELECTOR
                    or values != expected or location.fragment):
                raise DownloadError('Refusing an unexpected ESO association redirect.')
            file_url(identifier)
            return self.get(CALSELECTOR, params={key: value[0] for key, value in expected.items()})
        if response.status_code != 200:
            code = response.status_code
            response.close()
            if code in (401, 403):
                raise DownloadError('ESO access denied: check credentials and Data Access delegation.')
            raise DownloadError(f'ESO returned HTTP {code}; no file was accepted.')
        return response

    def query(self, night, programme=None, spectra_only=False):
        start, end = night_bounds(night)
        if programme is not None and not re.fullmatch(r'[A-Za-z0-9().+\-]{1,40}', programme):
            raise DownloadError('Invalid ESO programme identifier.')
        query = ("SELECT dp_id,date_obs,dp_cat,dp_type,dp_tech,prog_id,object,release_date "
                 "FROM dbo.raw WHERE instrument='EFOSC' "
                 f"AND mjd_obs >= {Time(start).mjd} AND mjd_obs < {Time(end).mjd}")
        if programme:
            query += f" AND prog_id='{programme}'"
        if spectra_only:
            query += " AND dp_tech='SPECTRUM'"
        with self.get(TAP, params={'REQUEST': 'doQuery', 'LANG': 'ADQL',
                                  'FORMAT': 'votable', 'MAXREC': 20000,
                                  'QUERY': query+' ORDER BY date_obs'}) as response:
            rows = table_rows(response.content)
        for row in rows:
            file_url(row['dp_id'])
            if not Time(start).mjd <= Time(row['date_obs']).mjd < Time(end).mjd:
                raise DownloadError('ESO returned an exposure outside the requested night.')
        return rows

    def associations(self, identifier):
        file_url(identifier)
        with self.get(DATALINK, params={'ID': 'ivo://eso.org/ID?'+identifier,
                                       'eso_download': 'calSelector_raw2raw'}) as response:
            return table_rows(response.content)


def validate_fits(path, identifier, night=None):
    try:
        with fits.open(path, memmap=False) as hdus:
            hdus.verify('exception')
            header = hdus[0].header
            if header.get('INSTRUME') != 'EFOSC' or header.get('ARCFILE') != identifier+'.fits':
                raise DownloadError('Downloaded FITS instrument or archive identity does not match.')
            if any(key in header for key in ('FILETYPE', 'PRODCATG', 'PROV1', 'TRACE1')):
                raise DownloadError('Downloaded FITS is a processed product, not a raw exposure.')
            observed = header['DATE-OBS']
            if night:
                lo, hi = map(lambda t: Time(t).mjd, night_bounds(night))
                if not lo <= Time(observed).mjd < hi:
                    raise DownloadError('Downloaded exposure is outside the requested night.')
            size = Path(path).stat().st_size
            for hdu in hdus:
                info = hdu.fileinfo()
                if info['datLoc']+info['datSpan'] > size:
                    raise DownloadError('Downloaded FITS is truncated.')
                if hdu.verify_checksum() == 0 or hdu.verify_datasum() == 0:
                    raise DownloadError('Downloaded FITS checksum failed.')
                _ = hdu.data  # Detect truncated arrays before accepting the file.
            return {'date_obs': observed, 'dpr_type': header.get('ESO DPR TYPE'),
                    'grism': header.get('ESO INS GRIS1 NAME')}
    except DownloadError:
        raise
    except Exception:
        raise DownloadError('Downloaded file is not a valid complete raw EFOSC FITS.') from None


def fetch_file(client, entry, root, previous=None, night=None):
    identifier = entry['dp_id']
    url = file_url(identifier)
    relative = Path('calibrations') if entry['relation'] == 'associated' else Path('.')
    target = root/relative/(identifier+'.fits')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.is_symlink():
        raise DownloadError('Refusing a symbolic-link download destination.')
    if target.exists():
        digest = sha256(target)
        if previous and previous.get('sha256') and previous['sha256'] != digest:
            raise DownloadError('Existing FITS changed since download; preserve it and use a fresh output root.')
        info = validate_fits(target, identifier, night)
        return dict(info, status='complete', action='reused', path=str(target.relative_to(root)), sha256=digest)
    # Temporary files and final FITS are private; only complete verified files become visible.
    with tempfile.TemporaryDirectory(prefix='.download-', dir=target.parent) as directory:
        transport, unpacked = Path(directory)/'response', Path(directory)/'unpacked.fits'
        try:
            with client.get(url, stream=True) as response, transport.open('xb') as output:
                os.chmod(transport, 0o600)
                for block in response.iter_content(1024*1024):
                    output.write(block)
        except requests.RequestException:
            raise DownloadError('Download interrupted; rerun to resume completed files.') from None
        with transport.open('rb') as source:
            magic = source.read(8)
        with unpacked.open('xb') as output:
            os.chmod(unpacked, 0o600)
            if magic.startswith(b'\x1f\x9d'):
                if not shutil.which('gzip'):
                    raise DownloadError('Install gzip to unpack ESO .fits.Z downloads.')
                result = subprocess.run(['gzip', '-dc', str(transport)], stdout=output, stderr=subprocess.DEVNULL)
                if result.returncode:
                    raise DownloadError('ESO compressed download is corrupt or incomplete.')
            elif magic.startswith(b'\x1f\x8b'):
                try:
                    with gzip.open(transport, 'rb') as source:
                        shutil.copyfileobj(source, output)
                except (OSError, EOFError):
                    raise DownloadError('ESO compressed download is corrupt or incomplete.') from None
            else:
                with transport.open('rb') as source:
                    shutil.copyfileobj(source, output)
        info = validate_fits(unpacked, identifier, night)
        digest = sha256(unpacked)
        os.link(unpacked, target)  # Atomic creation; never overwrite an existing file.
        return dict(info, status='complete', action='downloaded', path=str(target.relative_to(root)),
                    sha256=digest, transport_sha256=sha256(transport))


def save_manifest(path, value):
    fd, name = tempfile.mkstemp(prefix='.manifest-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def download_night(night, *, output_root='data', programme=None, spectra_only=False,
                   with_calibrations=False, dry_run=False, public_only=False, client=None, progress=None):
    start, end = night_bounds(night)
    owned = client is None
    client = client or ESOClient(public_only=public_only)
    root = Path(output_root).resolve()/night
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = root/'.download.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if owned:
            client.close()
        raise DownloadError('Another download owns this folder; check .download.lock before retrying.') from None
    os.close(fd)
    try:
        manifest_path = root/('download-plan.json' if dry_run else 'download-manifest.json')
        prior = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        previous = {row['dp_id']: row for row in prior.get('files', [])}
        rows = client.query(night, programme, spectra_only)
        entries = {r['dp_id']: dict(r, relation='night', status='pending') for r in rows}
        association_status, errors = [], []
        if with_calibrations:
            for row in rows:
                if row['dp_cat'] != 'SCIENCE' or row['dp_tech'] != 'SPECTRUM':
                    continue
                try:
                    associated = client.associations(row['dp_id'])
                    main = [a for a in associated if a.get('semantics') == '#this']
                    if not main or any(a.get('error_message') for a in associated):
                        raise DownloadError('ESO did not return a usable raw calibration association.')
                    description = main[0].get('description', '')
                    association_status.append({'dp_id': row['dp_id'], 'description': description})
                    if 'complete="true"' not in description or 'mode="Raw2Raw"' not in description:
                        errors.append({'dp_id': row['dp_id'], 'error': 'ESO raw association is incomplete.'})
                    for item in associated:
                        if item.get('semantics') != '#calibration':
                            continue
                        url = item.get('access_url', '')
                        if not url.startswith(FILES+'EFOSC.'):
                            continue  # Static reference tables are not raw EFOSC exposures.
                        identifier = url[len(FILES):]
                        file_url(identifier)
                        entries.setdefault(identifier, {'dp_id': identifier, 'relation': 'associated',
                                           'eso_category': item.get('eso_category'), 'status': 'pending'})
                except DownloadError as exc:
                    errors.append({'dp_id': row['dp_id'], 'error': str(exc)})
        # Keep integrity evidence even if this invocation is interrupted before reuse checks.
        for identifier, entry in entries.items():
            if previous.get(identifier, {}).get('sha256'):
                entry['sha256'] = previous[identifier]['sha256']
        report = {'schema_version': 1, 'night': night, 'utc_interval': [start, end],
                  'programme': programme, 'spectra_only': spectra_only, 'with_calibrations': with_calibrations,
                  'auth_mode': client.auth_mode, 'output_dir': str(root), 'status': 'planned' if dry_run else 'running',
                  'associations': association_status, 'errors': errors, 'files': list(entries.values())}
        save_manifest(manifest_path, report)
        if not dry_run:
            for index, entry in enumerate(report['files'], 1):
                try:
                    entry.update(fetch_file(client, entry, root, previous.get(entry['dp_id']),
                                            night if entry['relation'] == 'night' else None))
                except (DownloadError, OSError) as exc:
                    entry.update(status='failed', error=str(exc) if isinstance(exc, DownloadError)
                                 else 'Local file operation failed; check space and permissions.')
                save_manifest(manifest_path, report)
                if progress and (index % 10 == 0 or index == len(entries) or entry['status'] == 'failed'):
                    progress(f"{index}/{len(entries)}: {entry['dp_id']} — {entry['status']}")
        report['status'] = ('empty' if not entries else 'incomplete' if errors or any(
            e['status'] == 'failed' for e in report['files']) else 'planned' if dry_run else 'complete')
        save_manifest(manifest_path, report)
        return {'status': report['status'], 'output_dir': str(root), 'manifest': str(manifest_path),
                'selected': len(entries), 'complete': sum(e['status'] == 'complete' for e in report['files']),
                'failed': sum(e['status'] == 'failed' for e in report['files']), 'association_errors': len(errors)}
    finally:
        lock.unlink()
        if owned:
            client.close()
