"""Target-only reports must continue to show the night's unchanged reductions."""
import json
from pathlib import Path

import pytest
from PIL import Image

from efospec.epoch_report import build_epoch_page
from efospec.inventory import sha256


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def night(tmp_path):
    root = tmp_path/'runs/2026-11-25/efospec'
    raw = tmp_path/'old.fits'; raw.write_bytes(b'raw detector data')
    frame = dict(path=str(raw), sha256=sha256(raw), role='science',
                 metadata={'OBJECT':'Old target', 'DATE-OBS':'2026-11-26T01:00:00', 'EXPTIME':60},
                 setup=dict(grism='Gr13', filter='Free', slit='slit1.0'))
    old = root/'nightly/20261126T010000Z-old'
    new = root/'nightly/20261126T020000Z-new'
    product = old/'reduction/products/old.fits'
    product.parent.mkdir(parents=True); product.write_bytes(b'saved spectrum')
    product.with_suffix('.asci').write_text('4000 1\n5000 2\n')
    images = []
    for prefix in ('FitSpectrum_', 'FitTrace_', 'FitSpatialProfile_'):
        image = old/'reduction/style-preview'/f'{prefix}old.jpg'
        image.parent.mkdir(exist_ok=True)
        Image.new('RGB', (20, 20), 'red').save(image); images.append(str(image))
    save(old/'reduction/style-preview/FitSpectrum_old.json',
         dict(outputs=images, input_sha256={str(product):sha256(product)}))
    result = dict(raw=str(raw), raw_sha256=sha256(raw), object='Old target', role='science',
                  product=str(product), grism='Gr13', status='EXPERIMENTAL')
    for folder in (old, new):
        save(folder/'night.json', dict(night='2026-11-25', status='partial', targets=['New target'] if folder == new else None))
        save(folder/'observing-log.json', dict(frames=[frame]))
        save(folder/'reduction/run.json', dict(results=[result] if folder == old else [], errors=[], skipped=[]))
    save(root/'nightly/current.json', dict(night='2026-11-25', revision=new.name))
    return tmp_path, root, old, new, raw, product


def test_unchanged_spectrum_stays_visible_across_successive_reports(night):
    project, root, old, new, raw, product = night
    before = {p:sha256(p) for p in (raw, product, product.with_suffix('.asci'), old/'reduction/run.json')}
    report = build_epoch_page('2026-11-25', project)
    html = Path(report['path']).read_text()
    assert 'href="#retained-0-spectrum-0"' in html and 'id="retained-0-spectrum-0"' in html
    assert 'download="old.fits"' in html and 'download="old.asci"' in html
    assert report['embedded_figures'] == 3
    assert 'Outside selected targets' not in html
    assert 'Unchanged spectra and status from nightly/'+old.name in html
    assert not report['warnings']
    third = root/'nightly/20261126T030000Z-next'
    for name in ('night.json', 'observing-log.json', 'reduction/run.json'):
        save(third/name, json.loads((new/name).read_text()))
    save(root/'nightly/current.json', dict(night='2026-11-25', revision=third.name))
    report = build_epoch_page('2026-11-25', project)
    html = Path(report['path']).read_text()
    assert html.count('id="retained-0-spectrum-0"') == 1
    assert report['embedded_figures'] == 3
    assert all(sha256(p) == h for p, h in before.items())


@pytest.mark.parametrize('change', ['raw', 'product', 'inventory', 'target', 'failure'])
def test_changed_or_retried_exposure_does_not_reuse_older_success(night, change):
    project, root, old, new, raw, product = night
    if change in ('raw', 'product'):
        (raw if change == 'raw' else product).write_bytes(b'changed')
    elif change == 'inventory':
        inventory = json.loads((new/'observing-log.json').read_text())
        inventory['frames'][0]['sha256'] = 'new raw digest'
        save(new/'observing-log.json', inventory)
    elif change == 'target':
        save(new/'night.json', dict(night='2026-11-25', targets=['Old target']))
    else:
        save(new/'reduction/run.json', dict(results=[], skipped=[], errors=[
            dict(path=str(raw), object='Old target', code='wavelength_validation_failed')]))
    report = build_epoch_page('2026-11-25', project)
    html = Path(report['path']).read_text()
    assert 'id="retained-0-spectrum-0"' not in html
    if change == 'failure':
        assert 'id="spectrum-errors-0"' in html
    if change in ('raw', 'product', 'inventory'):
        assert report['warnings']


def test_count_only_products_keep_review_status(night):
    project, root, old, new, raw, product = night
    record = dict(raw=str(raw), raw_sha256=sha256(raw), object='Old target', role='science',
                  product=str(product), ascii=str(product.with_suffix('.asci')),
                  setup=dict(grism='Gr13', filter='Free', slit='slit1.0'),
                  product_sha256={str(product):sha256(product)},
                  delivery_status='Counts extracted; flux calibration pending',
                  pending_checks=['No flux response'])
    save(old/'reduction/run.json', dict(results=[], errors=[], skipped=[], review_counts=[record]))
    report = build_epoch_page('2026-11-25', project)
    html = Path(report['path']).read_text()
    assert 'href="#retained-0-spectrum-counts-0"' in html
    assert 'id="retained-0-spectrum-counts-0"' in html
    assert 'Counts extracted; flux calibration pending' in html
    assert '1 count spectra need review' in html


def test_historical_view_excludes_later_products(night):
    project, root, old, new, raw, product = night
    report = build_epoch_page('2026-11-25', project, revision_dir=old)
    assert report['embedded_figures'] == 3
    assert 'retained-0-spectrum' not in Path(report['path']).read_text()


def test_selected_provisional_product_survives_pointer_change(night):
    from efospec.epoch_report import EpochPage
    from efospec.retained_reductions import save_report_products
    project, root, old, new, raw, product = night
    rescue = root/'rescue/selected'
    rescued = rescue/'products/provisional.fits'
    rescued.parent.mkdir(parents=True); rescued.write_bytes(b'provisional spectrum')
    row = dict(raw=str(raw), raw_sha256=sha256(raw), object='Old target', role='science',
               product=str(rescued), status='PROVISIONAL', product_sha256={str(rescued):sha256(rescued)})
    manifest = dict(results=[row], errors=[], skipped=[])
    save(rescue/'run.json', manifest)
    save_report_products(EpochPage(root), old, [(rescue, manifest)])
    report = build_epoch_page('2026-11-25', project)
    html = Path(report['path']).read_text()
    assert 'download="provisional.fits"' in html
    assert 'Provisional flux; wavelength unvalidated' in html
    assert 'download="old.fits"' not in html
