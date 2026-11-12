"""Separate filtered standards and red review spectra: native counts and responses.

No science/standard pair, legacy calibration, second-order correction or claim
of independent flux validation is required to retain a standard's extraction.
"""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import json
from pathlib import Path
import traceback

import numpy as np
from astropy import units as u
from astropy.io import fits

from .inventory import inventory, sha256
from .native_calibration import calibration_key, save_json
from .native_calibrations import validate_associations
from .native_readiness import assess_native_readiness
from .native_reduction import prepare


def supported_counts(objects, limits):
    """Retain measured counts, but never certify wavelengths outside arc IDs."""
    if len(objects) != 1:
        raise ValueError('native counts delivery requires exactly one selected source')
    low, high = np.asarray(limits, float)
    if not np.isfinite([low, high]).all() or low >= high:
        raise ValueError('invalid arc reference bracket')
    # SpecObjs implements its own copying protocol; deepcopy recurses through
    # its attribute forwarding in PypeIt 1.14.
    result = objects.copy()
    spectrum = result[0]
    for kind in ('OPT', 'BOX'):
        wave, counts, ivar = (np.asarray(getattr(spectrum, kind+'_'+key))
                              for key in ('WAVE', 'COUNTS', 'COUNTS_IVAR'))
        valid = (getattr(spectrum, kind+'_MASK') & np.isfinite(wave)
                 & (wave >= low) & (wave <= high) & np.isfinite(counts)
                 & np.isfinite(ivar) & (ivar > 0))
        if valid.sum() < 100 or np.any(np.diff(wave[valid]) <= 0):
            raise ValueError('insufficient increasing, arc-supported extracted counts')
        setattr(spectrum, kind+'_MASK', valid)
    return result


def free_comparisons(frame, frames):
    """Retain comparison candidates; do not silently select/apply a correction."""
    h, setup = frame['metadata'], frame['setup']
    candidates = []
    for other in frames:
        s, oh = other['setup'], other['metadata']
        if (other['role'] != 'standard_candidate' or 'duplicate_of' in other
                or other['night'] != frame['night'] or s['filter'] != 'Free'
                or oh['OBJECT'].casefold() != h['OBJECT'].casefold()
                or any(s[k] != setup[k] for k in ('grism', 'slit', 'binx', 'biny', 'readout'))):
            continue
        candidates.append({'path': other['path'], 'sha256': other['sha256'],
                           'separation_seconds': abs(oh['MJD-OBS']-h['MJD-OBS'])*86400.,
                           'identity_verified': False})
    return sorted(candidates, key=lambda row: (row['separation_seconds'], row['path']))


def export_counts(prepared, directory):
    from pypeit.core.wave import airtovac
    from pypeit.specobjs import SpecObjs
    from .pypeit_diagnostics import write_spec2d
    frame, engine = prepared['frame'], prepared['engine']
    h, setup = frame['metadata'], frame['setup']
    qa = prepared['arc']['shared_acceptance']
    objects = supported_counts(engine['objects']['primary'], qa['valid_wave_vacuum_angstrom'])
    spectrum = objects[0]
    spectrum.DETECTOR = prepared['detector']
    stem = prepared['basename']
    header = {key: h[key] for key in ('RA', 'DEC', 'EXPTIME', 'DATE-OBS', 'INSTRUME', 'MJD-OBS')}
    header.update(TARGET=h['OBJECT'], PYP_SPEC='ntt_efosc2_epessto', PYPELINE='MultiSlit',
                  WAVEMED='vacuum', SPECSYS='TOPOCENT', EPSTATUS='EXPERIMENTAL',
                  FLUXCAL='NONE', FLEXURE=('VALIDATED' if prepared['sky'].get('held_out_6363_pass')
                                          else 'UNMEASURED'), BUNIT='electron',
                  GRISM=setup['grism'], FILTER=setup['filter'], SLIT=setup['slit'])
    native = directory/'native'/('spec1d_'+stem+'.fits')
    objects.write_to_fits(header, str(native), overwrite=False)
    loaded = SpecObjs.from_fitsfile(str(native))[0]
    if not np.array_equal(loaded.OPT_MASK, spectrum.OPT_MASK) or not np.array_equal(
            loaded.OPT_COUNTS, spectrum.OPT_COUNTS, equal_nan=True):
        raise ValueError('filtered native counts did not round-trip')
    columns = []
    for kind in ('OPT', 'BOX'):
        for suffix, unit in (('WAVE', 'Angstrom'), ('COUNTS', 'electron'), ('COUNTS_IVAR', 'electron-2')):
            columns.append(fits.Column(name=kind+'_'+suffix, format='D', unit=unit,
                                       array=getattr(spectrum, kind+'_'+suffix)))
        columns.append(fits.Column(name=kind+'_VALID', format='L', array=getattr(spectrum, kind+'_MASK')))
    table = directory/'products'/(stem+'_counts.fits')
    fits.HDUList([fits.PrimaryHDU(header=fits.Header(header)),
                  fits.BinTableHDU.from_columns(columns, name='COUNTS')]).writeto(table, checksum=True)
    sigma = np.full(len(spectrum.OPT_WAVE), np.nan)
    np.divide(1., np.sqrt(spectrum.OPT_COUNTS_IVAR), out=sigma, where=spectrum.OPT_COUNTS_IVAR > 0)
    ascii_path = table.with_suffix('.asci')
    np.savetxt(ascii_path, np.column_stack([spectrum.OPT_WAVE, spectrum.OPT_COUNTS,
               sigma, spectrum.OPT_MASK.astype(int)]), fmt=['%.8f', '%.8e', '%.8e', '%d'],
               header='vacuum_wavelength_A optimal_electrons statistical_sigma_electrons valid')
    diagnostics, arrays = engine['diagnostic_context'], engine['arrays']
    two_d = write_spec2d(directory/'native'/('spec2d_'+stem+'.fits'),
        diagnostics['science'], diagnostics['slits'], airtovac(prepared['waveair']*u.AA).value,
        diagnostics['tilts'], arrays[0], arrays=arrays, raw_origin=(prepared['ylo'], prepared['xlo']),
        stage='native_counts_validated_sky' if prepared['sky'].get('held_out_6363_pass')
              else 'native_counts_arc_only')
    image = directory/'native'/(stem+'_images.npz')
    np.savez_compressed(image, data=prepared['data'], sky=arrays[0], object_model=arrays[1],
        ivar=arrays[2], mask=arrays[3].mask, waveair=prepared['waveair'],
        trace=spectrum.TRACE_SPAT, raw_x_origin=prepared['xlo'], raw_y_origin=prepared['ylo'],
        **engine['selection'])
    files = [native, table, ascii_path, Path(two_d), image]
    record = {'raw': frame['path'], 'raw_sha256': frame['sha256'], 'object': h['OBJECT'],
        'date_obs': h['DATE-OBS'], 'setup': setup, 'status': 'counts_extracted',
        'native_spec1d': str(native), 'native_spec2d': two_d, 'product': str(table),
        'ascii': str(ascii_path), 'images': str(image),
        'product_sha256': {str(p): sha256(p) for p in files},
        'wavelength': qa, 'wavelength_medium': 'vacuum', 'reference_frame': 'topocentric',
        'counts_unit': 'electrons per spectral pixel', 'flux_calibrated': False,
        'science_validated': False, 'sky_flexure': prepared['sky'],
        'selection': engine['source_selection'], 'background': engine['background_fit'],
        'valid_samples': int(spectrum.OPT_MASK.sum()),
        'calibration_directory': str(prepared['bundle']['directory']),
        'calibration_manifest_sha256': sha256(prepared['bundle']['directory']/'calibration.json'),
        'raw_spatial_origin': prepared['xlo'], 'raw_spectral_origin': prepared['ylo'],
        'median_trace_raw_pixel': float(np.median(spectrum.TRACE_SPAT)+prepared['xlo'])}
    return record, objects


def fit_standard_response(frame, objects, directory):
    """A missing reference or failed response must not discard extracted counts."""
    from .standard_reference import standard_reference
    from .native_flux import build_response
    from .native_acceptance import standard_recovery
    stage = 'physical_reference'
    try:
        reference = standard_reference(frame, directory/'physical-references')
        stage = 'response_fit'
        response = build_response(frame, objects[0], directory/'response.fits', reference)
        closure, _ = standard_recovery(frame, objects[0], response['path'], reference)
        return {'status': 'response_built_unvalidated', 'response': response,
                'training_closure': closure, 'independent_flux_validation': False}
    except Exception as exc:
        (directory/'response-error.log').write_text(traceback.format_exc())
        return {'status': 'reference_unavailable' if stage == 'physical_reference' else 'response_failed',
                'stage': stage, 'error': str(exc), 'exception_type': type(exc).__name__,
                'independent_flux_validation': False}


def reduce_filtered_night(input_dir, output, *, night, position=548., spatial_half_width=100,
                          calibration_groups=(), background_reviews=None, render_report=True):
    """Separate Gr13/GG495 standards; retain the established public interface."""
    return _reduce_counts_night(input_dir, output, night=night, position=position,
        spatial_half_width=spatial_half_width, calibration_groups=calibration_groups,
        background_reviews=background_reviews, render_report=render_report)


def reduce_red_night(input_dir, output, *, night, position=548., spatial_half_width=100,
                     calibration_groups=(), targets=None):
    """Gr16/OG530 review counts, explicitly without accepted flexure or flux."""
    return _reduce_counts_night(input_dir, output, night=night, position=position,
        spatial_half_width=spatial_half_width, calibration_groups=calibration_groups,
        render_report=False, red_counts_only=True, targets=targets)


def _reduce_counts_night(input_dir, output, *, night, position=548., spatial_half_width=100,
                         calibration_groups=(), background_reviews=None, render_report=True,
                         red_counts_only=False, targets=None):
    """One explicitly named night, a fresh revision, and standalone standards."""
    import pypeit
    from .run_record import snapshot_sources
    compact = datetime.strptime(night, '%Y-%m-%d').strftime('%Y%m%d')
    if datetime.strptime(night, '%Y-%m-%d').strftime('%Y-%m-%d') != night:
        raise ValueError('observing date must be YYYY-MM-DD')
    inv = inventory([str(Path(input_dir).resolve())])
    readiness = assess_native_readiness(inv)
    if inv['errors'] or inv['identity_conflicts'] or readiness['invalid_inputs']:
        raise ValueError('resolve invalid raw inventory before filtered reduction')
    grism, filter_name = ('Gr16','OG530') if red_counts_only else ('Gr13','GG495')
    roles = {'science','standard_candidate'} if red_counts_only else {'standard_candidate'}
    frames = [f for f in inv['frames'] if f['role'] in roles
              and 'duplicate_of' not in f and f['setup']['grism'] == grism
              and f['setup']['filter'] == filter_name
              and (not targets or f['metadata']['OBJECT'] in targets)]
    if not frames or any(f['night'] != compact for f in frames):
        raise ValueError('selected counts exposures must belong to the single requested observing night')
    if targets and set(targets)-{f['metadata']['OBJECT'] for f in frames}:
        raise ValueError('one or more requested targets have no matching counts exposure')
    if not np.isfinite(position) or not 100 < position < 920:
        raise ValueError('expected position must lie inside the slit')
    if type(spatial_half_width) is not int or not 50 <= spatial_half_width <= 200:
        raise ValueError('spatial half-width must be an integer from 50 to 200 pixels')
    associations = {e['path']: e for e in readiness['exposures']}
    from .filtered_background import load_background_reviews
    reviews = load_background_reviews(background_reviews, frames)
    cache = {}
    for path in calibration_groups:
        path = Path(path).resolve()
        record = json.loads((path/'calibration.json').read_text())
        if record.get('mode') != 'native_raw_only' or record.get('status') != 'experimental_complete':
            raise ValueError('cached group must be a completed paired-native raw calibration, not a diagnostic-only group')
        key = calibration_key({'setup': record['setup'], 'raw_calibrations': record['associations']})
        if key in cache:
            raise ValueError('multiple cached native groups for the same raw associations')
        cache[key] = path
    required_keys = {calibration_key(associations[f['path']]) for f in frames}
    if set(cache)-required_keys:
        raise ValueError('cached native group does not match any selected filtered exposure')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    run = {'schema_version': 1, 'night': night, 'method': 'native_filtered_standard_extraction',
           'status': 'running', 'scientific_status': 'EXPERIMENTAL', 'pypeit_version': pypeit.__version__,
           'input_dir': str(Path(input_dir).resolve()), 'output_dir': str(output),
           'source_sha256': snapshot_sources(output), 'second_order_correction_applied': False,
           'configuration': {'expected_raw_spatial_pixel': position, 'spatial_half_width_pixels': spatial_half_width,
                             'arc_supported_rows_only': True},
           'background_reviews': reviews,
           'additional_validation_data': False, 'results': [], 'errors': [],
           'limitations': ['Arc-calibrated standard counts; exposure-specific flexure is unmeasured.',
               'Source geometry is selected automatically; identity is not astrometrically verified.',
               'Responses remain experimental; training closure is not independent flux validation.',
               'No second-order, telluric or slit-loss correction; response uncertainty is not propagated.']}
    if red_counts_only:
        run.update(method='native_red_counts_diagnostic', targets=targets,
                   science_validated=False, accepted_science_delivery=False)
        run['limitations'][0] = 'Arc-calibrated review counts; red-sky flexure is diagnostic only and no shift is applied.'
    save_json(output/'inputs.json', inv); save_json(output/'setup-checks.json', readiness)
    save_json(output/'run.json', run)
    for frame in sorted(frames, key=lambda f: f['metadata']['MJD-OBS']):
        directory = output/'exposures'/Path(frame['path']).stem
        directory.mkdir(parents=True)
        with (directory/'execution.log').open('w') as stream, redirect_stdout(stream), redirect_stderr(stream):
            try:
                association = associations[frame['path']]
                selected = association['raw_calibrations']
                validate_associations(frame, selected)
                key = calibration_key(association)
                prepared = prepare(frame, selected, directory, position, cached=cache.get(key),
                                   arc_supported_only=True, spatial_half_width=spatial_half_width,
                                   background_review=reviews.get(Path(frame['path']).name),
                                   **({'red_counts_only':True} if red_counts_only else {}))
                cache[key] = prepared['bundle']['directory']
                record, objects = export_counts(prepared, directory)
                record['free_comparison_candidates'] = free_comparisons(frame, inv['frames'])
                record['flux_response'] = (fit_standard_response(frame, objects, directory)
                    if frame['role']=='standard_candidate' else
                    {'status':'not_applied', 'independent_flux_validation':False})
                if sha256(Path(frame['path'])) != frame['sha256']:
                    raise ValueError('raw standard changed during reduction')
                save_json(directory/'extraction.json', record)
                run['results'].append(record)
            except Exception as exc:
                traceback.print_exc()
                run['errors'].append({'raw': frame['path'], 'object': frame['metadata']['OBJECT'],
                    'error': str(exc), 'exception_type': type(exc).__name__,
                    'diagnostics': getattr(exc, 'diagnostics', {}), 'log': str(directory/'execution.log')})
        save_json(output/'run.json', run)
    run['status'] = 'partial' if run['errors'] else 'complete'
    if not run['results']: run['status'] = 'failed'
    save_json(output/'run.json', run)
    if render_report:
        from .filtered_plots import plot_filtered_run
        from .epoch_report import build_filtered_page
        try:
            plot_filtered_run(output)
            from . import epoch_report
            run['report'] = {'path': str(output/'index.html'), 'status': 'complete',
                             'renderer_source_sha256': sha256(Path(epoch_report.__file__))}
            save_json(output/'run.json', run)
            build_filtered_page(output)
        except Exception as exc:
            run['report'] = {'status': 'incomplete', 'error': str(exc)}
        save_json(output/'run.json', run)
    return run
