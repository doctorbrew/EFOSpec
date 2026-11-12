"""Explicit, hash-bound before/after telluric products for read-only reports."""
import json
from pathlib import Path

from .inventory import sha256


def _pairs(run, manifest, expected_digest=None):
    run=Path(run).resolve();manifest=Path(manifest).resolve()
    if expected_digest is not None and sha256(manifest)!=expected_digest:
        raise ValueError('selected telluric manifest changed')
    source=json.loads((run/'run.json').read_text());record=json.loads(manifest.read_text())
    if (record.get('status')!='complete' or record.get('night')!=source.get('night') or
            record.get('source_run_sha256')!=sha256(run/'run.json') or
            Path(record['source_run']).resolve()!=(run/'run.json').resolve()):
        raise ValueError('telluric products belong to a different reduction revision')
    dated=next((p for p in run.parents if p.name==source['night'] and p.parent.name=='runs'),None)
    if dated is None or not manifest.is_relative_to(dated):
        raise ValueError('telluric products must belong to this dated run directory')
    results={Path(r['product']).name:r for r in source['results'] if r.get('role')=='science'}
    pairs={}
    for row in record['products']:
        name=Path(row['source_product']).name
        if name in pairs or name not in results:raise ValueError('ambiguous or non-science telluric association')
        result=results[name];product=run/'products'/name
        if (Path(row['source_product']).resolve()!=product.resolve() or sha256(product)!=row['source_sha256'] or
                row['raw_sha256']!=result['raw_sha256'] or row['raw']!=result['raw']):
            raise ValueError('telluric pair does not match the original transient spectrum')
        for key,digest_key in [('product','sha256'),('ascii','ascii_sha256'),
                               ('uncorrected_product','uncorrected_sha256'),('uncorrected_ascii','uncorrected_ascii_sha256')]:
            path=Path(row[key]).resolve()
            if not path.is_relative_to(manifest.parent) or sha256(path)!=row[digest_key]:
                raise ValueError('telluric pair file changed or is outside its revision')
        if row['uncorrected_sha256']!=row['source_sha256']:
            raise ValueError('retained original differs from source spectrum')
        pairs[name]={**row,'manifest':str(manifest),'manifest_sha256':sha256(manifest),
                     'plots_dir':str(manifest.parent/'style-preview')}
    return pairs


def select_for_report(run, manifest):
    """Change only the presentation selection; retain both scientific reductions."""
    run=Path(run).resolve();manifest=Path(manifest).resolve()
    _pairs(run,manifest)
    from .native_calibration import save_json
    selection=run/'telluric-selection.json'
    if selection.exists():
        archive=run/'telluric-selections';archive.mkdir(exist_ok=True)
        (archive/(sha256(selection)+'.json')).write_bytes(selection.read_bytes())
    save_json(selection,dict(schema_version=1,manifest=str(manifest),manifest_sha256=sha256(manifest)))
    return selection


def selected_pairs(run):
    selection=Path(run)/'telluric-selection.json'
    if not selection.exists():return {}
    pointer=json.loads(selection.read_text())
    if pointer.get('schema_version')!=1:raise ValueError('unsupported telluric presentation selection')
    return _pairs(run,pointer['manifest'],pointer['manifest_sha256'])


def overlay_record(pair):
    """Never use a previous correction's plot merely because its name matches."""
    matches=[]
    for path in sorted(Path(pair['plots_dir']).glob('FitSpectrum_*.json')):
        record=json.loads(path.read_text())
        if record.get('telluric_pair',{}).get('sha256')!=pair['sha256']:continue
        expected={pair['source_product']:pair['source_sha256'],pair['product']:pair['sha256'],
                  pair['manifest']:pair['manifest_sha256']}
        if any(record.get('input_sha256',{}).get(k)!=v for k,v in expected.items()):
            raise ValueError('telluric comparison plot has stale inputs')
        for name,digest in record['output_sha256'].items():
            path=Path(name).resolve()
            if not path.is_relative_to(Path(pair['plots_dir']).resolve()) or sha256(path)!=digest:
                raise ValueError('telluric comparison figure changed')
        matches.append(record)
    if len(matches)>1:raise ValueError('ambiguous telluric comparison figures')
    return matches[0] if matches else None


def read_overlay(pair):
    import numpy as np
    from astropy.io import fits
    from .qa import read_flux
    wave,bands,header=read_flux(Path(pair['product']))
    before,original,old_header=read_flux(Path(pair['source_product']))
    if (not np.array_equal(wave,before) or header.get('WAVEMED')!='air' or
            header.get('BUNIT')!=old_header.get('BUNIT') or bands.shape!=original.shape):
        raise ValueError('telluric pair wavelength grid or flux units differ')
    with fits.open(pair['product']) as hdus, fits.open(pair['source_product']) as source:
        if not np.array_equal(hdus['UNCORRECTED'].data,source[0].data,equal_nan=True):
            raise ValueError('telluric provenance does not preserve the original data')
        valid=hdus['VALID'].data[0].astype(bool);original_valid=source['VALID'].data[0].astype(bool)
        table=hdus['TELLURIC'].data;applied=table['APPLIED'].copy()
        if not np.array_equal(table['ORIGINAL_VALID'],original_valid) or np.any(applied&~(valid&original_valid)):
            raise ValueError('inconsistent telluric validity masks')
        if header.get('TELVALID') not in {'REVIEW','TRANSFER'}:raise ValueError('unknown telluric validation status')
    bands=bands.copy();bands[:,~valid]=np.nan
    return dict(wave=wave,bands=bands,applied=applied,original_valid=original_valid,review=header['TELVALID']=='REVIEW',
                review_reasons=pair.get('review_reasons',[]),qualified_bands=pair['bands'])


def status_text(pair):
    if pair.get('review_reasons'):
        return 'Telluric correction: review required — '+'; '.join(pair['review_reasons'])+'.'
    return 'Partial telluric correction: standard transfer checked; absolute flux remains unvalidated.'


def render_selected(run, *, render_plots=True):
    """Build the existing final reports; preserve the selected reduction itself."""
    import subprocess
    import sys
    run=Path(run).resolve();pairs=selected_pairs(run)
    source=json.loads((run/'run.json').read_text())
    dated=next(p for p in run.parents if p.name==source['night'] and p.parent.name=='runs')
    if pairs:
        folder=Path(next(iter(pairs.values()))['manifest']).parent
        archive=folder/'previous-report';archive.mkdir(exist_ok=True)
        for page in (dated/'index.html',run/'index.html'):
            if page.exists():
                saved=archive/(sha256(page)+'.html')
                if not saved.exists():saved.write_bytes(page.read_bytes())
        if render_plots:
            script=Path(__file__).resolve().parents[2]/'scripts/preview_spectrum_style.py'
            with (folder/'presentation.log').open('w') as log:
                subprocess.run([sys.executable,str(script),'--run',str(run),'--telluric-only','--no-legacy'],
                    stdout=log,stderr=subprocess.STDOUT,check=True)
    from .report import write_report
    write_report(run)
    from .epoch_report import build_epoch_page
    pointer=json.loads((dated/'nightly/current.json').read_text())
    current=(dated/'nightly'/pointer['revision']).resolve()
    return build_epoch_page(source['night'],dated.parent.parent,
        revision_dir=None if current==run.parent else run.parent)
