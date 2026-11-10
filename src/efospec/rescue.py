"""Explicit provisional flux delivery from audited native review counts.

This route never accepts a failed flexure correction. It preserves the raw arc
wavelengths, unchanged counts and successful two-sided background model, and
applies an exact-setup same-night response in a new, clearly marked revision.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .daily_reduction import select_response, supported
from .inventory import inspect_file, sha256
from .native_calibration import save_json


def validate_counts(record, frame):
    if (record['raw']!=frame['path'] or record['raw_sha256']!=frame['sha256']
            or record['setup']!=frame['setup'] or record['object']!=frame['metadata']['OBJECT']):
        raise ValueError('review counts do not match the unchanged science exposure/setup')
    if (record.get('flux_calibrated') is not False or record.get('science_validated') is not False
            or record['sky_flexure'].get('held_out_6363_pass') is not False
            or record['sky_flexure'].get('shift_angstrom')!=0):
        raise ValueError('rescue requires explicitly unvalidated, unshifted native counts')
    background=record['background']
    if background.get('pypeit_exit_status')!=0 or background.get('minimum_side_samples',0)<5:
        raise ValueError('rescue cannot bypass failed two-sided background support')
    required={record[k] for k in ('native_spec1d','product','images','native_spec2d','ascii')}
    if not required.issubset(record['product_sha256']):
        raise ValueError('review counts lack required product hashes')
    for path,digest in record['product_sha256'].items():
        if sha256(Path(path))!=digest:raise ValueError('review count product changed: '+path)
    if sha256(Path(record['calibration_directory'])/'calibration.json')!=record['calibration_manifest_sha256']:
        raise ValueError('review-count calibration manifest changed')


def rescue_daily(parent, output, *, night, counts_runs=(), targets=None, boxcar_targets=(), replace_review_counts=False):
    """Rescue only recorded wavelength failures, without modifying their parent."""
    from astropy import units as u
    from pypeit.core.wave import vactoair
    from pypeit.specobjs import SpecObjs
    import pypeit
    from .native_calibrations import load_calibrations, validate_associations
    from .products import PreparedExposure, export_spectrum
    from .run_record import snapshot_sources

    parent=Path(parent).resolve();old=json.loads((parent/'run.json').read_text())
    if old.get('night')!=night or old.get('flux_calibration')!='same-night' or old.get('execution_status')=='running':
        raise ValueError('rescue requires a completed same-night parent for the explicitly selected night')
    failures={e['path']:e for e in old['errors'] if e.get('code')=='wavelength_validation_failed'}
    selected={p:e for p,e in failures.items() if not targets or e['object'] in targets}
    if not selected or (targets and set(targets)-{e['object'] for e in selected.values()}):
        raise ValueError('select recorded science wavelength failures from the parent')
    if set(boxcar_targets)-{e['object'] for e in selected.values()}:
        raise ValueError('boxcar target is not among selected failures')
    sources={r['raw']:(r,str(parent/'run.json'),sha256(parent/'run.json')) for r in old.get('review_counts',[])}
    supplied=set()
    for directory in counts_runs:
        path=Path(directory).resolve()/'run.json';extra=json.loads(path.read_text())
        if extra.get('night')!=night or extra.get('method')!='native_optical_counts_diagnostic':
            raise ValueError('additional counts must be optical review counts from this night')
        for r in extra['results']:
            if r['raw'] not in selected:raise ValueError('additional counts include an unrequested exposure')
            if r['raw'] in supplied or (r['raw'] in sources and not replace_review_counts):
                raise ValueError('ambiguous duplicate review-count sources')
            supplied.add(r['raw'])
            sources[r['raw']]=(r,str(path),sha256(path))
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    for directory in ('products','native','qa','errors'):(output/directory).mkdir()
    run=dict(night=night,method='native_raw_calibration_provisional_rescue',
        wavelength_policy='provisional_arc_only',flux_calibration='same-night',
        status='PROVISIONAL',execution_status='running',input_dir=old['input_dir'],output_dir=str(output),
        parent_run=str(parent),parent_sha256=sha256(parent/'run.json'),
        replaced_parent_review_counts=bool(replace_review_counts),
        pypeit_version=pypeit.__version__,source_sha256=snapshot_sources(output),
        independent_flux_validation=False,results=[],errors=[],skipped=[],
        limitations=['Science wavelength validation failed: all products retain unshifted arc wavelengths.',
            'These products are provisional, not replacements for wavelength-validated nightly products.',
            'Source identity, slit losses, tellurics, second order, host contamination and absolute flux remain unvalidated.',
            'Statistical errors omit response, wavelength, background-model and resampling covariance uncertainties.'])
    save_json(output/'run.json',run)
    for path,failure in selected.items():
        try:
            if path not in sources:raise ValueError('no successful background-validated counts; re-extract with documented clean geometry first')
            record,source,source_hash=sources[path]
            frame=inspect_file(Path(path))
            if frame['role']!='science' or not supported(frame) or frame['night']!=night.replace('-',''):
                raise ValueError('unsupported science exposure for provisional rescue')
            validate_counts(record,frame)
            standard=select_response(frame,old['standards'])
            bundle=load_calibrations(record['calibration_directory'])
            validate_associations(frame,bundle['record']['associations'])
            if bundle['record']['setup']!=frame['setup']:raise ValueError('science master setup mismatch')
            # Check the standard's masters as well as the response/raw/extinction
            # files already checked by select_response.
            standard_bundle=load_calibrations(standard['counts']['calibration_directory'])
            if standard_bundle['record']['setup']!=standard['frame']['setup']:
                raise ValueError('standard master setup mismatch')
            validate_associations(standard['frame'],standard_bundle['record']['associations'])
            with np.load(record['images']) as saved:arrays={k:saved[k] for k in saved.files}
            objects=SpecObjs.from_fitsfile(record['native_spec1d'])
            if len(objects)!=1:raise ValueError('review file must contain one explicitly selected source')
            s=objects[0]
            engine=dict(objects={'primary':objects},found=objects,
                arrays=[arrays['sky'],arrays['object_model'],arrays['ivar'],SimpleNamespace(mask=arrays['mask'])],
                selection={k:arrays[k] for k in ('sky_input_mask','found_traces','found_names','sky_mask_stage',
                            'sky_accepted_mask','sky_valid_rows','sky_side_counts','sky_spatial_degree')},
                sky_policy='bounded_two_sided_pypeit',background_fit=record['background'],
                source_selection=record['selection'])
            response=deepcopy(standard['fit']['response'])
            response.update(selection='nearest successful same-night exact-setup response; provisional science wavelengths',
                night=night,setup=standard['frame']['setup'],independent_flux_validation=False)
            calibration=dict(mode='native_raw_only',wavelength_policy='provisional_arc_only',
                sensitivity=response,extinction=response['extinction'],
                groups=[str(bundle['directory']),str(standard_bundle['directory'])],
                raw_inputs={**bundle['record']['raw_inputs'],**standard_bundle['record']['raw_inputs']})
            sky=dict(record['sky_flexure'],status='unvalidated',policy='provisional raw arc wavelengths; no flexure correction applied',
                     original_failure=failure,shift_angstrom=0.,applied_shift_angstrom=None)
            selection=deepcopy(record['selection'])
            selection['association']='operator_selected' if selection.get('identity_confirmed') else 'UNVERIFIED_target_association'
            arc=dict(bundle['record']['wavelength'],arc=bundle['record']['associations']['arc']['files'][0],
                reference_lines=vactoair(np.asarray(bundle['record']['wavelength']['reference_lines_vacuum'])*u.AA).value.tolist())
            context=PreparedExposure(frame,output,s.DETECTOR,arrays['data'],arrays['waveair'],
                record['raw_spatial_origin']-99,record['raw_spectral_origin'],548.-99,
                selection,arc,Path(response['path']),0.,sky,calibration)
            basename=Path(record['product']).name.removesuffix('_counts.fits')+'_provisional'
            primary='boxcar' if record['object'] in boxcar_targets else 'optimal'
            result=export_spectrum(context,engine,'primary',output,basename,primary_extraction=primary)
            if result['valid_flux_fraction']<=0:raise ValueError('no supported provisional flux samples')
            result.update(counts_source=source,counts_source_sha256=source_hash,
                counts_product=record['product'],counts_product_sha256=record['product_sha256'][record['product']],
                native_spec2d=record['native_spec2d'],native_spec2d_sha256=record['product_sha256'][record['native_spec2d']],
                interpretation=('Finite boxcar aperture includes source and extended emission; no host deblending.'
                                if primary=='boxcar' else 'Selected trace; astrophysical identity and host contamination remain unvalidated.'))
            result['product_sha256']={str(p):sha256(p) for p in
                (Path(result['product']),Path(result['product']).with_suffix('.asci'),Path(result['native_spec1d']))}
            save_json(output/'qa'/(basename+'.json'),result);run['results'].append(result)
        except Exception as exc:
            import traceback
            log=output/'errors'/(Path(path).stem+'.log');log.write_text(traceback.format_exc())
            run['errors'].append(dict(path=path,object=failure['object'],error=str(exc),log=str(log)))
        save_json(output/'run.json',run)
    run['execution_status']='partial' if run['errors'] else 'complete'
    if sha256(parent/'run.json')!=run['parent_sha256']:raise ValueError('parent changed during rescue')
    save_json(output/'run.json',run)
    return run


def build_rescue_report(output, *, render_plots=True):
    from html import escape
    from .report import build_report, CSS
    from .epoch_report import EpochPage, EPOCH_CSS, SCRIPT
    output=Path(output).resolve();run=json.loads((output/'run.json').read_text())
    if run.get('wavelength_policy')!='provisional_arc_only':raise ValueError('not a provisional rescue run')
    rendered=build_report(output,render_plots=render_plots)
    if rendered['status']!='complete':return rendered
    page=EpochPage(output)
    body=page.spectra(output,run)
    errors=''.join('<li>'+escape(e['object']+': '+e['error'])+'</li>' for e in run['errors'])
    methods=('Native raw calibrations and exact-setup same-night standard responses. '
        'No flexure correction applied. Statistical errors exclude wavelength, response and background-model systematics. '
        'Target identities and absolute flux remain unvalidated. Boxcar products retain extended emission within their apertures.')
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EFOSpec / {escape(run['night'])} / Provisional rescue</title><style>{CSS}{EPOCH_CSS}</style></head><body><main>
<header class="masthead"><span class="brand">ePESSTO+ / EFOSpec</span><span>Provisional rescue</span></header>
<h1>{escape(run['night'])}</h1><p class="qc-status-bad">PROVISIONAL FLUX: science wavelength validation failed. Unshifted arc wavelengths; no validated flexure correction.</p>
<p>{len(run['results'])} provisional spectra; {len(run['errors'])} extraction/export failures. The accepted nightly revision is unchanged.</p>
{body}<h2>Unresolved exposures</h2><ul>{errors}</ul><h2>Calibration and limitations</h2><p>{methods}</p>
<p>{page.download(output/'run.json','Provenance and original failures')}</p></main>
<dialog aria-label="Enlarged figure"><button type="button">Close</button><img alt=""></dialog><script>{SCRIPT}</script></body></html>'''
    (output/'index.html').write_text(html)
    rendered.update(portable=True,scientific_status='PROVISIONAL',warnings=page.warnings)
    save_json(output/'report.json',rendered)
    return rendered
