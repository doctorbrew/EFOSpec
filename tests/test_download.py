"""Downloader contracts; no real credentials or external downloads in CI."""
from contextlib import redirect_stdout
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
import requests

from epessto_plus.download import (DownloadError, ESOClient, TAP, DATALINK, FILES,
    download_night, fetch_file, file_url, night_bounds, table_rows)

ID = 'EFOSC.2026-10-30T02:42:46.563'
CAL = 'EFOSC.2026-10-25T09:00:00.000'


def row(identifier=ID):
    return dict(dp_id=identifier, date_obs='2026-10-30T02:42:46.562',
                dp_cat='SCIENCE', dp_type='OBJECT', dp_tech='SPECTRUM', prog_id='117.29T8.002')


def raw(identifier=ID, observed='2026-10-30T02:42:46.562'):
    stream = io.BytesIO()
    fits.PrimaryHDU(np.ones((10, 10), dtype=np.int16), fits.Header({
        'INSTRUME': 'EFOSC', 'ARCFILE': identifier+'.fits', 'DATE-OBS': observed})).writeto(stream)
    return stream.getvalue()


def response(payload, status=200):
    result = MagicMock(status_code=status, content=payload)
    result.__enter__.return_value = result
    result.iter_content.return_value = [payload]
    return result


def table_bytes(rows):
    stream = io.BytesIO()
    Table(rows=rows).write(stream, format='votable')
    return stream.getvalue()


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.client = MagicMock(auth_mode='anonymous')
        self.client.query.return_value = [row()]
        self.client.get.return_value = response(raw())

    def test_date_validation_and_year_rollover(self):
        self.assertEqual(night_bounds('2026-12-31'), ('2026-12-31T12:00:00', '2027-01-01T12:00:00'))
        for night in ('../escape', '2026-02-30', '2026-1-01', '2026-10-29T00:00:00'):
            with self.subTest(night=night), self.assertRaises(ValueError):
                night_bounds(night)

    def test_query_selects_half_open_noon_interval_and_optional_programme(self):
        with ESOClientForTest() as client:
            client.session.get.return_value = response(table_bytes([row()]))
            self.assertEqual(len(client.query('2026-10-29', '117.29T8.002', True)), 1)
            query = client.session.get.call_args.kwargs['params']['QUERY']
            self.assertIn(f"mjd_obs >= {Time('2026-10-29T12:00:00').mjd}", query)
            self.assertIn(f"mjd_obs < {Time('2026-10-30T12:00:00').mjd}", query)
            self.assertIn("prog_id='117.29T8.002'", query)
            self.assertIn("dp_tech='SPECTRUM'", query)
            with self.assertRaises(DownloadError):client.query('2026-10-29', "x' OR 1=1")

    def test_query_rejects_offnight_metadata(self):
        with ESOClientForTest() as client:
            client.session.get.return_value = response(table_bytes([dict(row(), date_obs='2026-10-30T12:00:00')]))
            with self.assertRaisesRegex(DownloadError, 'outside'):client.query('2026-10-29')

    def test_password_auth_is_only_sent_to_file_service_and_redirects_are_refused(self):
        with ESOClientForTest({'ESO_USERNAME': 'testuser', 'ESO_PASSWORD': 'private-test-value'}) as client:
            client.session.get.return_value = response(b'')
            client.get(TAP)
            self.assertIsNone(client.session.get.call_args.kwargs['auth'])
            client.get(file_url(ID))
            kwargs = client.session.get.call_args.kwargs
            self.assertEqual(kwargs['auth'], ('testuser', 'private-test-value'))
            self.assertFalse(kwargs['allow_redirects'])
            self.assertIsNone(kwargs['params'])
            for url in ('http://dataportal.eso.org/dataPortal/file/'+ID,
                        'https://example.org/'+ID, FILES+'../escape'):
                with self.assertRaises(DownloadError):client.get(url)
            client.session.get.return_value = response(b'private-test-value', 302)
            with self.assertRaises(DownloadError) as caught:client.get(file_url(ID))
            self.assertNotIn('private-test-value', str(caught.exception))

    def test_token_and_public_only_modes(self):
        with ESOClientForTest({'ESO_TOKEN': 'test-token'}) as client:
            client.session.get.return_value = response(b'')
            client.get(DATALINK)
            self.assertEqual(client.session.get.call_args.kwargs['headers'], {'Authorization': 'Bearer test-token'})
        client = ESOClient(public_only=True, environ={'ESO_USERNAME': 'user', 'ESO_PASSWORD': 'secret', 'ESO_TOKEN': 'token'})
        self.addCleanup(client.close)
        self.assertEqual(client.auth_mode, 'anonymous')
        self.assertIsNone(client.auth)
        self.assertIsNone(client.token)
        with self.assertRaises(DownloadError):ESOClient(environ={'ESO_USERNAME': 'user'})

    def test_only_the_expected_eso_raw_association_redirect_is_followed(self):
        from epessto_plus.download import CALSELECTOR
        params = {'ID': 'ivo://eso.org/ID?'+ID, 'eso_download': 'calSelector_raw2raw'}
        redirect = response(b'', 303)
        redirect.headers = {'Location': CALSELECTOR+f'?dp_id={ID}&mode=Raw2Raw&responseformat=votable'}
        with ESOClientForTest({'ESO_TOKEN': 'test-token'}) as client:
            client.session.get.side_effect = [redirect, response(b'ok')]
            self.assertEqual(client.get(DATALINK, params=params).content, b'ok')
            self.assertEqual(client.session.get.call_args.args[0], CALSELECTOR)
            client.session.get.side_effect = None
            for location in ('https://example.org/', CALSELECTOR+f'?dp_id={CAL}&mode=Raw2Raw&responseformat=votable'):
                redirect.headers = {'Location': location}
                client.session.get.return_value = redirect
                with self.assertRaisesRegex(DownloadError, 'unexpected'):
                    client.get(DATALINK, params=params)

    def test_denial_and_network_errors_never_echo_server_body_or_request_secret(self):
        with ESOClientForTest() as client:
            client.session.get.return_value = response(b'pretend-secret-in-body', 401)
            with self.assertRaisesRegex(DownloadError, 'Data Access') as caught:client.get(file_url(ID))
            self.assertNotIn('pretend-secret', str(caught.exception))
            client.session.get.side_effect = requests.ConnectionError('pretend-secret-in-error')
            with self.assertRaises(DownloadError) as caught:client.get(file_url(ID))
            self.assertNotIn('pretend-secret', str(caught.exception))

    def test_truncated_query_and_invalid_table_fail(self):
        for value in ('ERROR', 'OVERFLOW'):
            with self.assertRaisesRegex(DownloadError, 'truncated'):
                table_rows(f'<VOTABLE><INFO name="QUERY_STATUS" value="{value}"/></VOTABLE>'.encode())
        with self.assertRaises(DownloadError):table_rows(b'<html>Login</html>')

    def test_dry_run_writes_dated_plan_without_downloading(self):
        result = download_night('2026-10-29', output_root=self.root, dry_run=True, client=self.client)
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(Path(result['output_dir']), self.root/'2026-10-29')
        self.client.get.assert_not_called()
        self.assertFalse(list(self.root.rglob('*.fits')))

    def test_gzip_download_resume_and_changed_file_detection(self):
        self.client.get.return_value = response(gzip.compress(raw()))
        first = download_night('2026-10-29', output_root=self.root, client=self.client)
        self.assertEqual(first['status'], 'complete')
        target = self.root/'2026-10-29'/(ID+'.fits')
        self.assertEqual(target.read_bytes(), raw())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.client.get.reset_mock()
        second = download_night('2026-10-29', output_root=self.root, client=self.client)
        self.assertEqual(second['complete'], 1)
        self.client.get.assert_not_called()
        target.write_bytes(b'changed')
        third = download_night('2026-10-29', output_root=self.root, client=self.client)
        self.assertEqual(third['status'], 'incomplete')
        self.assertEqual(target.read_bytes(), b'changed')

    def test_invalid_or_wrong_identity_fits_never_reaches_final_path(self):
        for payload in (b'<html>Login</html>', raw(CAL), raw()[:-2880]):
            self.client.get.return_value = response(payload)
            with self.subTest(payload_size=len(payload)), self.assertRaises(DownloadError):
                fetch_file(self.client, {'dp_id': ID, 'relation': 'night'}, self.root, night='2026-10-29')
            self.assertFalse(list(self.root.glob('*.fits')))
            self.assertFalse(list(self.root.glob('.download-*')))

    def test_interrupted_resume_keeps_previous_integrity_evidence(self):
        first = download_night('2026-10-29', output_root=self.root, client=self.client)
        manifest = Path(first['manifest'])
        digest = json.loads(manifest.read_text())['files'][0]['sha256']
        with patch('epessto_plus.download.fetch_file', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            download_night('2026-10-29', output_root=self.root, client=self.client)
        self.assertEqual(json.loads(manifest.read_text())['files'][0]['sha256'], digest)
        self.assertFalse((manifest.parent/'.download.lock').exists())
        (manifest.parent/(ID+'.fits')).write_bytes(raw()+b' '*2880)
        result = download_night('2026-10-29', output_root=self.root, client=self.client)
        self.assertEqual(result['failed'], 1)

    def test_offnight_file_is_only_allowed_as_explicit_associated_calibration(self):
        self.client.get.return_value = response(raw(CAL, '2026-10-25T09:00:00'))
        with self.assertRaisesRegex(DownloadError, 'outside'):
            fetch_file(self.client, {'dp_id': CAL, 'relation': 'night'}, self.root, night='2026-10-29')
        result = fetch_file(self.client, {'dp_id': CAL, 'relation': 'associated'}, self.root)
        self.assertTrue(result['path'].startswith('calibrations/'))

    def test_association_deduplication_and_partial_access_failure(self):
        self.client.associations.return_value = [
            {'semantics': '#this', 'description': 'complete="true" certified="false" mode="Raw2Raw"'},
            {'semantics': '#calibration', 'access_url': file_url(CAL), 'eso_category': 'BIAS'},
            {'semantics': '#calibration', 'access_url': file_url(CAL), 'eso_category': 'BIAS'}]
        self.client.get.side_effect = [DownloadError('ESO access denied'), response(raw(CAL, '2026-10-25T09:00:00'))]
        result = download_night('2026-10-29', output_root=self.root, with_calibrations=True, client=self.client)
        self.assertEqual((result['status'], result['selected'], result['complete'], result['failed']),
                         ('incomplete', 2, 1, 1))
        manifest = json.loads(Path(result['manifest']).read_text())
        self.assertIn('certified="false"', manifest['associations'][0]['description'])

    def test_incomplete_associations_and_empty_night_are_not_success(self):
        self.client.associations.return_value = [{'semantics': '#this', 'description': 'complete="false" mode="Raw2Raw"'}]
        result = download_night('2026-10-29', output_root=self.root, dry_run=True, with_calibrations=True, client=self.client)
        self.assertEqual(result['status'], 'incomplete')
        self.client.query.return_value = []
        self.assertEqual(download_night('2026-10-29', output_root=self.root, client=self.client)['status'], 'empty')

    def test_concurrent_writer_is_refused(self):
        directory = self.root/'2026-10-29'
        directory.mkdir()
        (directory/'.download.lock').touch()
        with self.assertRaisesRegex(DownloadError, 'Another download'):
            download_night('2026-10-29', output_root=self.root, client=self.client)
        self.client.query.assert_not_called()

    def test_cli_passes_flags_and_returns_failure_for_incomplete_download(self):
        from epessto_plus.__main__ import main
        with patch('epessto_plus.download.download_night', return_value={'status': 'incomplete'}) as download, redirect_stdout(io.StringIO()):
            status = main(['download', '2026-10-29', '--programme', '117.29T8.002', '--with-calibrations'])
        self.assertEqual(status, 1)
        self.assertTrue(download.call_args.kwargs['with_calibrations'])
        self.assertEqual(download.call_args.kwargs['programme'], '117.29T8.002')


class ESOClientForTest:
    def __init__(self, env=None):self.env = env or {}
    def __enter__(self):
        self.client = ESOClient(environ=self.env)
        self.client.session.close()
        self.client.session = MagicMock()
        return self.client
    def __exit__(self, *args):self.client.close()
