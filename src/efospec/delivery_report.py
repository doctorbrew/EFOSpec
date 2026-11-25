"""Offline delivery controls for saved, eligible science products in an epoch log."""
import base64
from datetime import date, timedelta
from html import escape
from io import BytesIO, StringIO
import json
from pathlib import Path

import numpy as np

from .delivery import digest, inspect_product
from .naming import source_order
from .delivery_identity import delivery_filename
from .wiserep import _legacy_row, _safe_name, DEFAULT_SOURCE_GROUP, DEFAULT_PRIVATE_GROUPS
from .wiserep_tar import HEADER, DEFAULTS, primary_copy


def product_payload(path, result, night):
    """Use the same science validation and primary FITS conversion as CLI delivery."""
    before = digest(path)
    hdus, wave, flux, sigma, good, meta = inspect_product(path, object_name=result['object'])
    header = hdus[0].header
    if date.fromisoformat(header['DATE-OBS'][:10]) not in {
            date.fromisoformat(night), date.fromisoformat(night) + timedelta(days=1)}:
        raise ValueError('Product belongs to another observing night')
    if header.get('QUALITY') not in {'Rapid', 'Final', 'Low', 'Med', 'High'}:
        raise ValueError('Spectrum quality has not been recorded')
    filename = delivery_filename(path, header, header['OBJECT'])
    _safe_name(filename)
    if len(filename) > 100:
        raise ValueError('Filename exceeds the upload tar format limit')
    binary = BytesIO()
    primary_copy(path, binary)
    text = StringIO()
    np.savetxt(text, np.column_stack([wave[good], flux[good]]), fmt='%.17e', delimiter='\t')
    record = dict(object=header['OBJECT'], observers='', reducers='', reduction_date='',
                  quality=header['QUALITY'], spectrum_type='Object',
                  review_notes='EFOSpec/PypeIt; ' + str(header.get('EPSTATUS', '')))
    names = dict(fits=filename, ascii=Path(filename).stem + '.asci')
    row = _legacy_row(record, header, names, [None, None], tgz=True)
    if digest(path) != before:
        raise ValueError('Science product changed while building the report')
    return dict(filename=filename, ascii_name=names['ascii'], source_sha256=before,
                fits_base64=base64.b64encode(binary.getvalue()).decode('ascii'),
                ascii=text.getvalue(), row=row, quality=header['QUALITY'],
                setup=' / '.join(str(header[k]) for k in ('GRISM', 'FILTER', 'SLIT')),
                samples=int(good.sum()), omitted=int((~good).sum()))


def render_delivery(page, revision, run, manuals=()):
    frames = page.read(revision / 'observing-log.json').get('frames', [])
    science = {Path(f['path']).name: f for f in frames if f.get('role') == 'science'}
    groups = {}
    for frame in science.values():
        name = frame.get('metadata', {}).get('OBJECT', 'Unknown')
        groups.setdefault(name, dict(object=name, observed=0, products=[], issues=[]))['observed'] += 1
    selected = {}
    for folder, manifest in [(revision / 'reduction', run), *manuals]:
        for result in manifest.get('results', []):
            raw = Path(result.get('raw', '')).name
            if raw in science:
                selected[raw] = (folder, result)
    for raw, (folder, result) in selected.items():
        target = science[raw].get('metadata', {}).get('OBJECT', 'Unknown')
        group = groups[target]
        path = folder / 'products' / Path(result.get('product', '')).name
        try:
            path.resolve().relative_to(page.root)
            group['products'].append(product_payload(path, result, page.night))
        except (OSError, ValueError, KeyError, TypeError) as error:
            group['issues'].append(str(error).replace(str(page.root), 'this night'))
    ordered = sorted(groups.values(), key=source_order)
    for i, group in enumerate(ordered):
        group['id'] = str(i)
    config = dict(night=page.night, revision=revision.name, header=HEADER, defaults=DEFAULTS,
                  groups=ordered)
    rows = []
    for group in ordered:
        products = group['products']
        description = '; '.join(p['setup'] for p in products) or 'No eligible flux product'
        missing = group['observed'] - len(products)
        if missing:
            description += f'; {missing} exposure(s) unavailable for export'
        options = ('<option value="">Do not export</option><option value="public">Public</option>'
                   '<option value="private">Private</option>')
        disabled = '' if products else ' disabled'
        rows.append(f'<tr><th scope="row">{escape(group["object"])}</th><td>{len(products)}</td>'
                    f'<td>{escape(description)}</td><td><select data-delivery-type="{group["id"]}"'
                    f' aria-label="Spectrum type for {escape(group["object"], quote=True)}"{disabled}>'
                    '<option value="Object">Object</option><option value="Host">Host</option></select></td>'
                    f'<td><select data-delivery-target="{group["id"]}"'
                    f' aria-label="Access for {escape(group["object"], quote=True)}"{disabled}>{options}</select></td></tr>')
    payload = json.dumps(config, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    assets = Path(__file__).parent / 'web'
    return ('<style>' + (assets / 'delivery.css').read_text() + '</style>' +
        '<div id="delivery-export"><p>Choose which science targets to include. Each choice applies to all '
        'eligible setups listed for that target. Exports use the saved original flux products; standards, '
        'count-only and failed products are excluded.</p>'
        '<div class="table-wrap"><table><thead><tr><th>Target</th><th>Spectra</th><th>Available setups</th>'
        '<th>Spectrum type</th><th>Delivery</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
        '<details class="delivery-attribution" open><summary>Observer / reducer names and delivery details</summary>'
        '<div class="delivery-fields">'
        '<label>Observer names<input name="delivery-observers" autocomplete="off" placeholder="Full names, comma separated"></label>'
        '<label>Reducer names<input name="delivery-reducers" autocomplete="off" placeholder="Full names, comma separated"></label>'
        '<label>Reduction date (UTC)<input name="delivery-date" type="date"></label>'
        '<label>WISeREP source group<input name="delivery-group" autocomplete="off"'
        f' value="{escape(DEFAULT_SOURCE_GROUP, quote=True)}"></label>'
        '<label>Private associated groups<input name="delivery-private-groups" autocomplete="off"'
        f' value="{escape(", ".join(DEFAULT_PRIVATE_GROUPS), quote=True)}"></label>'
        '<label>Private embargo ends (UTC)<input name="delivery-embargo" type="datetime-local" step="1"></label>'
        '</div><p class="caption">Both groups default to ePESSTO+ for this programme. '
        'Change them only for a different collaboration; private groups apply only to private exports.</p></details>'
        '<label class="delivery-confirm"><input name="delivery-reviewed" type="checkbox"> '
        'I have reviewed the selected spectra and their public/private settings.</label>'
        '<div class="delivery-actions"><button type="button" id="delivery-build">Prepare public / private tarballs</button>'
        '<button type="button" id="delivery-clear">Clear choices and names</button></div>'
        '<p id="delivery-status" role="status" aria-live="polite">No spectra selected.</p>'
        '<div id="delivery-downloads"></div>'
        '<p class="caption">Names are written into FITS headers and the upload table. Files are prepared locally; '
        'nothing is uploaded. Download each populated tarball below. No calibrated 2D attachment is added automatically. '
        'Keep the original masked products for science. Private refers to the requested archive access; '
        'it does not make a published observing log private.</p>'
        '<noscript>JavaScript is required to prepare delivery tarballs. The observing log remains readable.</noscript>'
        '</div><script type="application/json" id="delivery-payload">' + payload + '</script>'
        '<script>' + (assets / 'delivery.js').read_text() + '</script>')
