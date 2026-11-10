"""One night's raw-calibrated spectra with contemporary, setup-matched responses."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
import sys
import traceback

import numpy as np

from .inventory import inventory, sha256
from .native_calibration import calibration_key, save_json
from .native_calibrations import validate_associations
from .native_readiness import assess_native_readiness
from .native_reduction import prepare
from .filtered_reduction import export_counts, fit_standard_response
from .products import PreparedExposure, export_spectrum

SETUP_KEYS = ('grism', 'filter', 'slit', 'binx', 'biny', 'readout')


def matches(frame, standard):
    return (frame['night'] == standard['night'] and
            all(frame['setup'][k] == standard['setup'][k] for k in SETUP_KEYS))


def select_response(frame, standards):
    """Nearest successful same-night response; ties and stale files fail closed."""
    candidates = [s for s in standards if matches(frame, s['frame'])
                  and s['fit']['status'] == 'response_built_unvalidated']
    candidates.sort(key=lambda s: abs(s['frame']['metadata']['MJD-OBS']-frame['metadata']['MJD-OBS']))
    if not candidates:
        raise ValueError('no successful same-night response with identical grism/filter/slit/binning/readout')
    distance = lambda s: abs(s['frame']['metadata']['MJD-OBS']-frame['metadata']['MJD-OBS'])
    if len(candidates)>1 and np.isclose(distance(candidates[0]), distance(candidates[1]), rtol=0., atol=1e-9):
        raise ValueError('tied same-night responses require an explicit association decision')
    selected = candidates[0]
    response = selected['fit']['response']
    for path, digest in [(response['path'], response['sha256']),
                         (response['standard_raw'], response['standard_sha256']),
                         (response['extinction']['path'], response['extinction']['sha256'])]:
        if sha256(Path(path)) != digest:
            raise ValueError('selected contemporary response or input changed')
    return selected


def supported(frame):
    s = frame['setup']
    return (s['grism'] in {'Gr11','Gr13'} and s['filter'] == 'Free'
            and s['binx'] == s['biny'] == 2 and s['slit'] in {'slit1.0','slit1.5'})


def reduce_daily(input_dir, output, *, night, targets=None, reviewed_sources=None, calibration_groups=()):
    """Standards first, then science; no archived sensitivity or geometry fallback."""
    compact = date.fromisoformat(night).strftime('%Y%m%d')
    if date.fromisoformat(night).isoformat() != night:
        raise ValueError('observing date must be YYYY-MM-DD')
    inv = inventory([str(Path(input_dir).resolve())])
    readiness = assess_native_readiness(inv)
    if inv['errors'] or inv['identity_conflicts'] or readiness['invalid_inputs']:
        raise ValueError('resolve invalid raw inventory before daily reduction')
    frames = [f for f in inv['frames'] if f['role'] in {'science','standard_candidate'}
              and 'duplicate_of' not in f]
    requested = [f for f in frames if not targets or f['metadata']['OBJECT'] in targets]
    if not requested or (targets and set(targets)-{f['metadata']['OBJECT'] for f in requested}):
        raise ValueError('no matching requested exposures')
    # Target filters must never suppress standards needed to calibrate the targets.
    standards = [f for f in frames if f['role']=='standard_candidate' and
                 any(matches(t, f) for t in requested if supported(t))]
    selected = {f['path']: f for f in requested+standards}
    if any(f['night'] != compact or f['issues'] for f in selected.values()):
        raise ValueError('selected exposures must have valid metadata and belong to the requested night')
    from .reviewed_sources import load_reviewed_sources
    reviews = load_reviewed_sources(reviewed_sources, requested)
    associations = {e['path']:e for e in readiness['exposures']}
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    for sub in ('products','native','qa','errors'):
        (output/sub).mkdir()
    from .run_record import snapshot_sources
    import pypeit
    run = dict(schema_version=1, night=night, status='EXPERIMENTAL', execution_status='running',
        method='native_raw_calibration_daily_standards', flux_calibration='same-night',
        input_dir=str(Path(input_dir).resolve()), output_dir=str(output), targets=targets,
        python=sys.executable, pypeit_version=pypeit.__version__, source_sha256=snapshot_sources(output),
        results=[], errors=[], skipped=[], standards=[], held_out=[], held_out_errors=[],
        review_counts=[], review_counts_errors=[],
        independent_flux_validation=False,
        limitations=['Same-night responses are experimental; absolute flux accuracy is unvalidated.',
            'Short standards retain arc-only wavelengths; no science sky shift is transferred to them.',
            'Source position is an acquisition hypothesis, not a confirmed astrophysical identity.',
            'No slit-loss, telluric or second-order correction; response uncertainty and resampling covariance are omitted.',
            'Only Gr11/Gr13 Free, 2x2, slit1.0/slit1.5 are enabled for nightly flux delivery.'])
    save_json(output/'inputs.json', inv); save_json(output/'setup-checks.json', readiness)
    save_json(output/'run.json', run)
    cache = {}; fitted = []; objects = {}
    import json
    for group in calibration_groups:
        group=Path(group).resolve()
        record=json.loads((group/'calibration.json').read_text())
        if record.get('status')!='experimental_complete' or record.get('mode')!='native_raw_only':
            raise ValueError('reused calibrations must be completed native raw groups')
        key=calibration_key(dict(setup=record['setup'],raw_calibrations=record['associations']))
        if key in cache:raise ValueError('duplicate cached native calibration group')
        cache[key]=group
    required_keys={calibration_key(associations[f['path']]) for f in selected.values() if supported(f)}
    if set(cache)-required_keys:
        raise ValueError('cached native group does not match a selected daily exposure')

    def failure(frame, stage, exc, directory):
        log = directory/'error.log'; log.write_text(traceback.format_exc())
        run['errors'].append(dict(path=frame['path'], object=frame['metadata']['OBJECT'],
            setup=frame['setup'], stage=stage, error=str(exc), traceback=str(log),
            code=getattr(exc, 'code', 'daily_calibration_failed'),
            diagnostics=getattr(exc, 'diagnostics', {}),
            action='Inspect the exposure log and same-night standards; no archive fallback was applied.'))

    def extract(frame, directory):
        association = associations[frame['path']]
        validate_associations(frame, association['raw_calibrations'])
        key = calibration_key(association)
        prepared = prepare(frame, association['raw_calibrations'], directory, 548.,
                           cached=cache.get(key), arc_supported_only=True,
                           reviewed_source=reviews.get(Path(frame['path']).name))
        cache[key] = prepared['bundle']['directory']
        return prepared

    def deliver(frame, prepared, chosen):
        response = dict(chosen['fit']['response'],
            selection='nearest successful same-night response; exact grism/filter/slit/binning/readout',
            setup=chosen['frame']['setup'], night=night,
            standard_wavelength_status=chosen['counts']['sky_flexure'],
            independent_flux_validation=False)
        bundle = prepared['bundle']
        std_bundle = chosen['calibration']
        calibration = dict(mode='native_raw_only', sensitivity=response, extinction=response['extinction'],
            raw_inputs={**std_bundle['raw_inputs'], **bundle['record']['raw_inputs']},
            groups=list(dict.fromkeys([chosen['counts']['calibration_directory'],str(bundle['directory'])])))
        selection=prepared['engine'].get('source_selection',{})
        identity={'association':('operator_selected' if selection.get('identity_confirmed') else
                                 'UNVERIFIED_nominal_acquisition_position'),**selection}
        context = PreparedExposure(frame, output, prepared['detector'], prepared['data'],
            prepared['waveair'], prepared['xlo']-99, prepared['ylo'], 548.-99,
            identity, prepared['arc'],
            Path(response['path']), prepared['shift'], prepared['sky'], calibration, prepared['processed'])
        from astropy.io import fits
        from .naming import science_stem, product_name
        h, setup = frame['metadata'], frame['setup']
        registry = {p.name:fits.getheader(p).get('DATE-OBS') for p in (output/'products').glob('*_f.fits')}
        stem = science_stem(h['OBJECT'],h['DATE-OBS'],setup['grism'],setup['filter'],setup['slit'])
        basename = product_name(stem,h['DATE-OBS'],registry,'_f')[:-7]
        row = export_spectrum(context, prepared['engine'], 'primary', output, basename)
        if row['valid_flux_fraction'] <= 0:
            raise ValueError('response and extraction have no supported flux bins')
        run['results'].append(row)

    for frame in sorted(selected.values(), key=lambda f:(f['role']!='standard_candidate',f['metadata']['MJD-OBS'])):
        if not supported(frame):
            run['skipped'].append(dict(path=frame['path'], object=frame['metadata']['OBJECT'],
                setup=frame['setup'], code='unsupported_setup',
                reason='Nightly contemporary flux delivery requires Gr11/Gr13 Free, 2x2, slit1.0/slit1.5; use separate filtered/red diagnostics.'))
            save_json(output/'run.json', run)
            continue
        directory = output/'exposures'/Path(frame['path']).stem; directory.mkdir(parents=True)
        stage = 'response_selection'
        with (directory/'execution.log').open('w') as stream, redirect_stdout(stream), redirect_stderr(stream):
            try:
                chosen = select_response(frame, fitted) if frame['role']=='science' else None
                stage = 'native_extraction'
                prepared = extract(frame, directory)
                if frame['role']=='standard_candidate':
                    stage = 'standard_counts'
                    counts, spectra = export_counts(prepared, directory)
                    prepared['engine']['objects']['primary'] = spectra
                    stage = 'response_fit'
                    fit = fit_standard_response(frame, spectra, directory)
                    entry = dict(frame=frame, counts=counts, fit=fit, calibration=prepared['bundle']['record'])
                    run['standards'].append(entry)
                    if fit['status'] != 'response_built_unvalidated':
                        raise ValueError(fit.get('error',fit['status']))
                    fitted.append(entry); objects[frame['path']] = spectra[0]
                    chosen = select_response(frame, fitted)
                stage = 'flux_export'
                deliver(frame, prepared, chosen)
            except Exception as exc:
                failure(frame, stage, exc, directory)
                if getattr(exc,'code',None)=='wavelength_validation_failed':
                    # Preserve a useful extraction without promoting a failed
                    # wavelength solution to science flux delivery.
                    review_root=output/'wavelength-review'
                    review_dir=review_root/'exposures'/Path(frame['path']).stem
                    review_dir.mkdir(parents=True)
                    try:
                        association=associations[frame['path']];key=calibration_key(association)
                        cached=cache.get(key) or directory/'calibration'
                        review=prepare(frame,association['raw_calibrations'],review_dir,548.,
                            cached=cached,arc_supported_only=True,arc_only_review=True,
                            reviewed_source=reviews.get(Path(frame['path']).name))
                        counts,_=export_counts(review,review_dir)
                        counts.update(wavelength_validation_error=str(exc),
                                      flux_response={'status':'not_applied','independent_flux_validation':False})
                        run['review_counts'].append(counts)
                        run['errors'][-1]['counts_review']=counts['product']
                    except Exception as review_exc:
                        (review_dir/'error.log').write_text(traceback.format_exc())
                        run['review_counts_errors'].append(dict(raw=frame['path'],object=frame['metadata']['OBJECT'],
                            error=str(review_exc),log=str(review_dir/'error.log'),
                            diagnostics=getattr(review_exc,'diagnostics',{})))
        save_json(output/'run.json', run)

    # Distinct exposures only. These diagnostics do not certify the absolute scale.
    from .native_acceptance import standard_recovery
    from .standard_reference import standard_reference
    for train in fitted:
        for test in fitted:
            a,b = train['frame'],test['frame']
            if a['sha256']==b['sha256'] or not matches(a,b):
                continue
            try:
                reference = standard_reference(b, output/'physical-references')
                qa,_ = standard_recovery(b, objects[b['path']], train['fit']['response']['path'], reference)
                run['held_out'].append(dict(qa, training_raw=a['path'], setup=b['setup']))
            except Exception as exc:
                run['held_out_errors'].append(dict(training_raw=a['path'], test_raw=b['path'], error=str(exc)))
    run['execution_status'] = ('partial' if run['results'] else 'failed') if (run['errors'] or run['skipped'] or run['held_out_errors']) else 'complete'
    if run['review_counts'] or run['review_counts_errors']:
        root=output/'wavelength-review'
        save_json(root/'inputs.json',inv)
        save_json(root/'run.json',dict(night=night,method='native_optical_counts_diagnostic',
            status='partial' if run['review_counts_errors'] else 'complete',
            results=run['review_counts'],errors=run['review_counts_errors'],
            scientific_status='EXPERIMENTAL',limitations=[
                'Science wavelength validation failed; these are review counts with unshifted arc wavelengths.',
                'No flux calibration or accepted exposure-specific flexure; target identity may remain unverified.']))
        run['review_counts_run']=str(root)
    save_json(output/'run.json', run)
    return run
