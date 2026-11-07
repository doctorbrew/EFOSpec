"""One-night catalogue QC, separate from spectral extraction and host selection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path

from astropy.io import fits

from .acquisition_astrometry import solve_acquisition
from .field_catalogues import CATALOGUES, fetch_catalogue, project_sources
from .inventory import sha256
from .native_calibration import save_json


def acquisition_fields(night, project_root, targets=()):
    if date.fromisoformat(night).isoformat() != night: raise ValueError('use YYYY-MM-DD')
    root = Path(project_root).resolve()/'runs'/night
    pointer = json.loads((root/'nightly/current.json').read_text())
    revision = (root/'nightly'/pointer['revision']).resolve()
    if pointer['night'] != night or revision.parent != root/'nightly': raise ValueError('invalid night pointer')
    inv = json.loads((revision/'observing-log.json').read_text())
    groups = {}
    for frame in inv['frames']:
        name = frame['metadata'].get('OBJECT', '')
        if frame['role'] != 'science' or not name.upper().startswith(('AT', 'SN')) or (targets and name not in targets):
            continue
        raw = Path(frame['path'])
        if sha256(raw) != frame['sha256']: raise ValueError('science raw changed since observing log')
        h = fits.getheader(raw); key = h.get('ESO OBS ID')
        if key is None: continue
        group = groups.setdefault(key, {'object':name, 'science_raws':[], 'directory':raw.parent})
        if group['object'] != name: raise ValueError('ambiguous target names in one observing block')
        group['science_raws'].append({'path':str(raw), 'sha256':frame['sha256']})
    fields = []
    for obsid, group in groups.items():
        for path in sorted(group['directory'].glob('*.fits')):
            h = fits.getheader(path)
            if h.get('ESO OBS ID') == obsid and h.get('ESO TPL ID') == 'EFOSC_img_acq_MoveToSlit' and h.get('NAXIS') == 2:
                fields.append({'raw':str(path.resolve()), 'raw_sha256':sha256(path),
                    'object':group['object'], 'science_raws':group['science_raws'], 'observing_block':obsid})
    if not fields: raise ValueError('no matching transient acquisition images in this night')
    if targets and set(targets)-{f['object'] for f in fields}: raise ValueError('requested target lacks acquisition frames')
    return root, fields


def check_acquisition_catalogues(night, output, *, project_root='.', targets=(),
                                catalogues=CATALOGUES, timeout=20, solver='solve-field'):
    from .catalogue_plots import plot_catalogue_field
    root, fields = acquisition_fields(night, project_root, targets)
    output = Path(output).resolve(); output.relative_to(root/'QC')
    if not catalogues or set(catalogues)-set(CATALOGUES): raise ValueError('choose NED, SDSS and/or AllWISE')
    if timeout <= 0: raise ValueError('timeout must be positive')
    output.mkdir(parents=True, exist_ok=False)
    record = {'schema_version':1, 'night':night, 'method':'acquisition_catalogue_qc',
        'status':'running', 'catalogues':list(catalogues), 'fields':[], 'host_identification':'not_assigned',
        'cross_match_radius_arcsec':2., 'spectral_registration':'not_performed',
        'source_sha256':{name:sha256(Path(__file__).parent/name) for name in
            ('acquisition_catalogues.py','acquisition_astrometry.py','field_catalogues.py','catalogue_plots.py')}}
    save_json(output/'catalogues.json', record)
    for field in fields:
        directory = output/Path(field['raw']).stem; directory.mkdir()
        try:
            wcs, astrometry = solve_acquisition(field['raw'], directory/'astrometry', executable=solver)
            field['astrometry'] = astrometry
            # Three independent, bounded public queries; report rendering is offline.
            with ThreadPoolExecutor(max_workers=len(catalogues)) as pool:
                queries = list(pool.map(lambda c: fetch_catalogue(c, astrometry['centre_icrs_deg'],
                    astrometry['radius_arcmin'], directory/'catalogues', timeout=timeout), catalogues))
            field['queries'] = queries
            data = fits.getdata(field['raw'])
            field['sources'] = project_sources(queries, wcs, data.shape)
            field['status'] = 'partial' if any(q['status'] in ('unavailable','truncated') for q in queries) else 'complete'
            plot_catalogue_field(data, field, directory)
            field['figures_sha256'] = {str(p):sha256(p) for p in directory.glob('FitQC_*') if p.suffix in ('.pdf','.jpg')}
            field['preview'] = str(directory/'catalogues.png')
            field['preview_sha256'] = sha256(Path(field['preview']))
        except Exception as exc:
            field.update(status='failed', error=str(exc))
        if sha256(Path(field['raw'])) != field['raw_sha256']: raise ValueError('raw acquisition changed')
        save_json(directory/'field.json', field)
        record['fields'].append(field)
        save_json(output/'catalogues.json', record)
    record['status'] = 'complete' if all(f['status']=='complete' for f in record['fields']) else 'partial'
    save_json(output/'catalogues.json', record)
    # Replace only matching acquisitions in the report pointer; retain other targets.
    pointer = root/'QC/catalogue-current.json'
    current = json.loads(pointer.read_text()) if pointer.exists() else {'night':night,'fields':{}}
    if current['night'] != night: raise ValueError('catalogue pointer belongs to another night')
    for field in record['fields']:
        path = output/Path(field['raw']).stem/'field.json'
        current['fields'][field['raw']] = {'path':str(path.relative_to(root)), 'sha256':sha256(path)}
    temp = pointer.with_suffix('.json.tmp'); save_json(temp, current); temp.replace(pointer)
    return record
