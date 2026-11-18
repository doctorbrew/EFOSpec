"""Cross-language checks of the actual offline exporter against PESSTOWISE TGZs."""
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

import numpy as np
import pytest
from astropy.io import fits

from efospec.delivery import digest
from efospec.delivery_report import render_delivery
from efospec.epoch_report import EpochPage
from efospec.wiserep_tar import validate_tar
from test_wiserep import reviewed


@pytest.fixture
def delivery_page(reviewed):
    manifest, rows = reviewed
    root = manifest.parent
    revision = root / 'nightly/revision-1'
    products = revision / 'reduction/products'
    products.mkdir(parents=True)
    frames, results = [], []
    for row in rows:
        source = root / row['product']
        shutil.copyfile(source, products / source.name)
        raw = row['object'] + '.fits'
        frames.append(dict(path=raw, role='science', metadata={'OBJECT': row['object']}))
        results.append(dict(raw=raw, object=row['object'], product=str(products / source.name)))
    frames.append(dict(path='standard.fits', role='standard_candidate', metadata={'OBJECT': 'Standard'}))
    results.append(dict(raw='standard.fits', object='Standard', product=str(products / rows[0]['product'])))
    (revision / 'observing-log.json').write_text(json.dumps({'frames': frames}))
    page = EpochPage(root); page.night = '2026-11-10'
    html = render_delivery(page, revision, dict(results=results))
    payload = json.loads(re.search(r'id="delivery-payload">(.*?)</script>', html, re.S)[1])
    return root, payload, html, rows


def node_export(root, payload, attribution, choices=None):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to test the standalone browser JavaScript')
    config = root / 'browser-payload.json'; config.write_text(json.dumps(payload))
    settings = root / 'browser-settings.json'
    choices = choices or {g['id']: ('private' if g['object'].endswith('private') else 'public') for g in payload['groups']}
    settings.write_text(json.dumps(dict(choices=choices, attribution=attribution)))
    script = Path(__file__).parents[1] / 'src/efospec/web/delivery.js'
    harness = root / 'run-export.cjs'
    harness.write_text('''const fs = require('fs');
eval(fs.readFileSync(process.argv[2], 'utf8'));
const config = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const settings = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
try {
 const results = EFOSpecDelivery.build(config, settings.choices, settings.attribution, new Date('2026-11-18T14:03:00Z'));
 for (const result of results) fs.writeFileSync(process.argv[5] + '/' + result.name, result.bytes);
 console.log(JSON.stringify(results.map(r => ({name:r.name,count:r.count}))));
} catch (error) {console.error(error.message); process.exit(2);}
''')
    return subprocess.run([node, str(harness), str(script), str(config), str(settings), str(root)], capture_output=True, text=True)


def attribution():
    return dict(observers="Observer O'Neil, " + ', '.join('Observer ' + str(i) for i in range(12)),
                reducers='Test Reducer', date='2026-11-12', group='Test source group',
                privateGroups=("Group O'Neil, " + 'Restricted group ' * 8).strip(),
                embargo='2027-11-18T00:00:00', reviewed=True)


def test_browser_tars_match_reference_and_preserve_science(delivery_page):
    root, config, html, rows = delivery_page
    assert len(config['groups']) == 2
    assert 'Standard' not in html
    assert 'selected' not in re.search(r'<select.*?</select>', html, re.S)[0]
    before = {r['product']: digest(root / r['product']) for r in rows}
    names = attribution()
    names['types'] = {g['id']: 'Host' if g['object'].endswith('private') else 'Object' for g in config['groups']}
    completed = node_export(root, config, names)
    assert completed.returncode == 0, completed.stderr
    assert len(json.loads(completed.stdout)) == 2
    preamble = (Path(__file__).parent / 'fixtures/pesstowise-upload-preamble.txt').read_bytes()
    for access in ('public', 'private'):
        archive = root / f'pessto_20261118_14_03_Rapid_upload_{access}.tgz'
        assert validate_tar(archive)['spectra'] == 1
        with tarfile.open(archive) as tar:
            table = tar.extractfile('pessto_20261118_14_03_Rapid_upload.txt').read()
            assert table.startswith(preamble)
            row = table.decode().splitlines()[2].split('\t')
            assert row[6] == names['observers'] and row[9] == names['reducers']
            assert row[10] == names['date'] and row[26:] == ['NULL', 'NULL']
            assert row[12] == ('Host' if access == 'private' else 'Object')
            with fits.open(io.BytesIO(tar.extractfile(row[2]).read()), checksum=True) as hdus:
                assert len(hdus) == 1
                assert hdus[0].verify_checksum() == hdus[0].verify_datasum() == 1
                np.testing.assert_array_equal(hdus[0].data, fits.getdata(root / row[2]))
                h = hdus[0].header
                assert h['OBSERVER'] == names['observers']
                assert h['REDUCER'] == names['reducers'] and h['DATE-RED'] == names['date']
                assert h['PESSTO ACCESS'] == access
                assert h['WISEREP SPECTRUM TYPE'] == row[12]
                if access == 'private':
                    assert h['WISEREP ASSOCIATED GROUPS'] == names['privateGroups']
                    assert h['WISEREP PROPRIETARY UNTIL'] == names['embargo']
                else:
                    assert 'WISEREP ASSOCIATED GROUPS' not in h
                    assert b'Restricted group' not in table
            assert len(tar.getmembers()) == 3
    assert all(digest(root / p) == value for p, value in before.items())


@pytest.mark.parametrize('change,message', [
    ({'reviewed': False}, 'Confirm'), ({'observers': ''}, 'observer'),
    ({'observers': 'Bad\tName'}, 'tabs'), ({'reducers': 'René'}, 'ASCII'),
    ({'privateGroups': ''}, 'private associated'), ({'date': '2026-02-30'}, 'valid UTC'),
    ({'embargo': '2020-01-01T00:00:00'}, 'future UTC'),
    ({'embargo': '2027-02-30T00:00:00'}, 'future UTC'),
])
def test_browser_rejects_incomplete_delivery(delivery_page, change, message):
    root, config, _, _ = delivery_page
    settings = attribution(); settings.update(change)
    result = node_export(root, config, settings)
    assert result.returncode == 2 and message in result.stderr
    assert not list(root.glob('*.tgz'))


def test_browser_single_access_class_and_corrupt_payload(delivery_page):
    root, config, _, _ = delivery_page
    selected = {g['id']: 'public' for g in config['groups']}
    settings = attribution(); settings.update(privateGroups='', embargo='')
    result = node_export(root, config, settings, selected)
    assert result.returncode == 0, result.stderr
    assert len(list(root.glob('*.tgz'))) == 1
    assert validate_tar(next(root.glob('*.tgz')))['spectra'] == 2
    # Embedded bytes must pass their original checksum before any header editing.
    import base64
    product = config['groups'][0]['products'][0]
    damaged = bytearray(base64.b64decode(product['fits_base64'])); damaged[-1] ^= 1
    product['fits_base64'] = base64.b64encode(damaged).decode()
    result = node_export(root, config, settings, selected)
    assert result.returncode == 2 and 'checksum failed' in result.stderr
