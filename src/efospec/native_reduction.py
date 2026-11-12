"""Experimental raw-only EFOSC2 reduction of an explicit science/standard pair."""
import json
from pathlib import Path
import sys
import numpy as np
from astropy import units as u
from .inventory import inspect_file, inventory, sha256
from .native_readiness import assess_native_readiness
from .native_calibrations import build_calibrations, process_exposure, load_calibrations
from .native_flux import build_response
from .naming import science_stem, product_name
from .products import PreparedExposure, export_spectrum


def arc_supported_rows(wavevac, limits):
    """A contiguous rectangle supported by arc IDs across every spatial column."""
    wavevac = np.asarray(wavevac, float)
    low, high = limits
    supported = np.flatnonzero(np.all(np.isfinite(wavevac) & (wavevac >= low) & (wavevac <= high), axis=1))
    if len(supported) < 100 or np.any(np.diff(supported) != 1):
        raise ValueError('insufficient contiguous arc-supported extraction rows')
    return int(supported[0]), int(supported[-1])+1


def prepare(frame, associations, directory, position, cached=None, *, arc_supported_only=False,
            spatial_half_width=100, background_review=None, red_counts_only=False,
            reviewed_source=None, arc_only_review=False, adaptive_window=False):
    """Expand only a calibrated inspection window when finite sky bands cannot fit.

    Expansion never relaxes source guards, wavelength coverage, or two-sided
    sampling. Explicit reviewed geometry always keeps its original window.
    """
    from .local_sky import BackgroundSupportError
    from .native_calibration import save_json
    directory = Path(directory)
    widths = [spatial_half_width]
    if adaptive_window and background_review is None and reviewed_source is None:
        widths += [w for w in (150, 200) if w > spatial_half_width]
    attempts = []
    for i, width in enumerate(widths):
        destination = directory if i == 0 else directory/f'window-half-{width}'
        try:
            result = _prepare_window(frame, associations, destination, position, cached,
                arc_supported_only=arc_supported_only, spatial_half_width=width,
                background_review=background_review, red_counts_only=red_counts_only,
                reviewed_source=reviewed_source, arc_only_review=arc_only_review)
            attempts.append(dict(spatial_half_width=width, directory=str(destination), status='extracted'))
            result['engine']['background_fit']['window_attempts'] = attempts
            save_json(directory/'window-attempts.json', attempts)
            return result
        except BackgroundSupportError as exc:
            attempts.append(dict(spatial_half_width=width, directory=str(destination),
                status='failed', error=str(exc), diagnostics=dict(exc.diagnostics)))
            save_json(directory/'window-attempts.json', attempts)
            trials = exc.diagnostics.get('trials', [])
            geometry_only = trials and all(t['status']=='geometry_unavailable' for t in trials)
            if not geometry_only or i == len(widths)-1:
                exc.diagnostics['window_attempts'] = attempts
                raise
            if cached is None and (destination/'calibration/calibration.json').is_file():
                cached = destination/'calibration'


def _prepare_window(frame, associations, directory, position, cached=None, *, arc_supported_only=False,
            spatial_half_width=100, background_review=None, red_counts_only=False,
            reviewed_source=None, arc_only_review=False):
    """Preserve the calibrated PypeIt noise model in a bounded raw-pixel window."""
    from pypeit.core.wave import vactoair
    from .extraction import extract_spectra
    if red_counts_only and (frame['setup']['grism'], frame['setup']['filter']) != ('Gr16','OG530'):
        raise ValueError('red counts-only diagnostics require Gr16/OG530')
    if arc_only_review and (frame['role']!='science' or frame['setup']['grism'] not in {'Gr11','Gr13'}
                            or frame['setup']['filter'] not in {'Free','GG495'}):
        raise ValueError('optical arc-only review requires a Gr11/Gr13 Free/GG495 science exposure')
    if cached is None:
        bundle=build_calibrations(frame,associations,directory/'calibration')
    else:
        bundle=load_calibrations(cached)
        record=bundle['record']
        if record['setup']!=frame['setup'] or any(
                record['associations'][role]['sha256']!=associations[role]['sha256']
                for role in ('bias','flat','arc')):
            raise ValueError('cached native group does not match the selected raw associations')
    image=process_exposure(frame,bundle)
    if not np.isfinite(position) or not 100<position<920:
        raise ValueError('source position must be a raw zero-based spatial pixel inside the slit')
    if type(spatial_half_width) is not int or not 50 <= spatial_half_width <= 200:
        raise ValueError('spatial half-width must be an integer from 50 to 200 pixels')
    xlo,xhi=int(position)-spatial_half_width,int(position)+spatial_half_width+1
    if xlo < 0 or xhi > image.image.shape[1]:
        raise ValueError('requested source window extends outside the detector')
    # Keep the optical detector region. Coordinates remain raw, binned pixels.
    ylo, yhi = 4, 1015
    if arc_supported_only:
        lower, upper = arc_supported_rows(bundle['wavevac'][ylo:yhi, xlo:xhi],
            bundle['record']['wavelength']['shared_acceptance']['valid_wave_vacuum_angstrom'])
        ylo, yhi = ylo+lower, ylo+upper
    cut=np.s_[ylo:yhi,xlo:xhi]
    if np.any(bundle['slitmask'][cut]<0):
        raise ValueError('requested source window extends outside the traced slit')
    waveair=vactoair(bundle['wavevac'][cut]*u.AA).value
    planes={k:np.broadcast_to(getattr(image,k),image.image.shape)[cut].copy()
            for k in ('ivar','rn2img','base_var','img_scale')}
    planes['bad_pixels']=image.fullmask.flagged()[cut].copy()
    data=image.image[cut].copy()
    qa=bundle['record']['wavelength']
    arc=dict(qa,arc=associations['arc']['files'][0],
             reference_lines=vactoair(np.array(qa['reference_lines_vacuum'])*u.AA).value.tolist())
    shift=0.
    # Attempt standards too; weak standard sky must not borrow a science shift.
    sky={'shift_angstrom':0.,'policy':'raw_arc_only; science sky check required',
         'held_out_6363_pass':False,'lines':[]}
    if red_counts_only:
        from .reduction_checks import check_red_sky
        diagnostic = check_red_sky(data, waveair, directory/'red-sky',
            {'raw':frame['path'], 'raw_sha256':frame['sha256'], 'setup':frame['setup'],
             'data_unit':'electron', 'raw_pixel_origin_yx':[ylo,xlo]})
        sky.update(policy='raw_arc_only; red-sky correlation is diagnostic, no correction applied',
                   status='unvalidated', applied_shift_angstrom=None,
                   review_file=str(directory/'red-sky/check.json'), correlation=diagnostic['correlation'],
                   band_consistency=diagnostic['band_consistency'])
    elif arc_only_review:
        sky.update(policy='raw_arc_only; failed science wavelength validation; review counts only',
                   status='unvalidated',applied_shift_angstrom=None)
    elif frame['role'] in {'science','standard_candidate'}:
        from .native_sky import exposure_flexure, SkyValidationError
        slit_pixels=float(frame['setup']['slit'].removeprefix('slit'))/(float(image.detector['platescale'])*frame['setup']['binx'])
        # Wavelength measurements can use the long slit without changing the
        # bounded background model used for source extraction. Exclude slit
        # edges, detector masks and the target core before spatial clipping.
        cols=np.flatnonzero(np.all(bundle['slitmask'][ylo:yhi]>=0,axis=0))
        margin=max(10,int(.1*len(cols)))
        sky_xlo,sky_xhi=int(cols[margin]),int(cols[-margin-1])+1
        sky_cut=np.s_[ylo:yhi,sky_xlo:sky_xhi]
        sky_wave=vactoair(bundle['wavevac'][sky_cut]*u.AA).value
        sky_good=~image.fullmask.flagged()[sky_cut]
        sky_good &= abs(np.arange(sky_xlo,sky_xhi)[None,:]-position)>30.
        try:
            shift,sky=exposure_flexure(image.image[sky_cut],sky_wave,
                required=frame['role']=='science',slit_width_pixels=slit_pixels,good_pixels=sky_good)
        except SkyValidationError as exc:
            from .native_calibration import save_json
            directory.mkdir(parents=True,exist_ok=True)
            check=directory/'sky-check-failed.json'
            save_json(check,dict(raw=frame['path'],raw_sha256=frame['sha256'],error=str(exc),
                measurement_raw_bounds_yx=[ylo,yhi,sky_xlo,sky_xhi],**exc.diagnostics))
            exc.diagnostics['review_file']=str(check)
            raise
        sky['measurement_raw_bounds_yx']=[ylo,yhi,sky_xlo,sky_xhi]
        sky['target_exclusion_radius_pixels']=30.
        if frame['role']=='science' and not sky['held_out_6363_pass']:
            raise ValueError('native science requires an independent 6363-A sky-line check')
        if sky['held_out_6363_pass']:
            sky['policy']='two sky lines plus independent 6363-A check'
        waveair+=shift
    directory.mkdir(parents=True,exist_ok=True)
    from .native_calibration import save_json
    save_json(directory/'sky-check.json',dict(raw=frame['path'],raw_sha256=frame['sha256'],**sky))
    for sub in ('products','native','qa','QA/PNGs'):(directory/sub).mkdir(parents=True,exist_ok=True)
    h=frame['metadata'];setup=frame['setup']
    basename=product_name(science_stem(h['OBJECT'],h['DATE-OBS'],setup['grism'],setup['filter'],setup['slit']),h['DATE-OBS'],{},'_f')[:-7]
    arguments = {'bounded_background': True}
    if reviewed_source is not None:
        if background_review is not None:raise ValueError('select one native background recipe')
        from .reviewed_sources import native_review_arguments
        arguments,source_evidence=native_review_arguments(reviewed_source,frame,data.shape,
                                                         (ylo,xlo),directory)
    if background_review is not None:
        from .filtered_background import review_arguments
        arguments, background_evidence = review_arguments(background_review, frame, data, waveair,
                                                          (ylo, xlo), bundle['directory'])
        (directory/'background-review.json').write_text(json.dumps(background_review, indent=2)+'\n')
    engine=extract_spectra(data,waveair,image.detector,exposure_time=h['EXPTIME'],
        read_noise=h['ESO DET OUT1 RON'],output=directory,basename=basename,
        target_position=position-xlo,processed=planes,**arguments)
    if reviewed_source is not None:
        requested=arguments['manual'][0]
        spectrum=engine['objects']['primary'][0]
        anchor=float(np.interp(requested['spec'],np.arange(len(spectrum.TRACE_SPAT)),spectrum.TRACE_SPAT))
        if abs(anchor-requested['spat'])>requested['radius']:
            raise ValueError('native trace does not match the reviewed raw source position')
        engine['source_selection']=dict(method='reviewed_raw_coordinate_reselection',
            identity_confirmed=reviewed_source['identity']['method']=='operator_visual',
            identity=reviewed_source['identity'],review=source_evidence,
            fitted_anchor_raw_pixel=anchor+xlo)
        engine['background_fit']['selection']=source_evidence
    if background_review is not None:
        engine['background_fit']['selection'] = background_evidence
        engine['source_selection'] = {'method': 'reviewed_background_geometry', 'identity_confirmed': False,
                                     'review': background_review}
    return dict(bundle=bundle,engine=engine,frame=frame,basename=basename,data=data,
                waveair=waveair,detector=image.detector,processed=planes,xlo=xlo,ylo=ylo,position=position,
                arc=arc,shift=shift,sky=sky)


def reduce_pair(input_dir, science, standard, output, *, science_position=548., standard_position=548.,
                render_report=True, reuse_calibrations=None):
    """No reference-root argument and no fallback to previously reduced calibration."""
    science,standard=inspect_file(Path(science).resolve()),inspect_file(Path(standard).resolve())
    if science['role']!='science' or standard['role']!='standard_candidate':
        raise ValueError('select an EFOSC2 science exposure and a raw spectrophotometric standard')
    keys=('grism','filter','binx','biny','readout')
    if any(science['setup'][k]!=standard['setup'][k] for k in keys):
        raise ValueError('science and standard configurations do not match')
    if abs(science['metadata']['MJD-OBS']-standard['metadata']['MJD-OBS'])>1:
        raise ValueError('native response requires a standard within one day')
    readiness=assess_native_readiness(inventory([str(input_dir)]))
    associations={r['path']:r['raw_calibrations'] for r in readiness['exposures']}
    if any(f['path'] not in associations for f in (science,standard)):
        raise ValueError('selected science/standard must occur in the inventoried directory')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    manifest={'schema_version':1,'status':'EXPERIMENTAL','method':'native_raw_calibration_with_PypeIt_extraction',
        'input_dir':str(Path(input_dir).resolve()),'output_dir':str(output),'python':sys.executable,
        'pypeit_version':'3.0.0','results':[],'errors':[],'skipped':[],
        'limitations':['Experimental Gr11/Gr13 raw path; no IRAF runtime or calibration products.',
                      'Source position is an operator/acquisition hypothesis, not an astrometric identification.',
                      'No telluric/slit-loss correction; flux errors exclude response uncertainty.']}
    from .run_record import snapshot_sources
    manifest['source_sha256']=snapshot_sources(output)
    try:
        from .standard_reference import standard_reference
        physical=standard_reference(standard,output/'physical-references')
        cached=Path(reuse_calibrations).resolve() if reuse_calibrations else None
        std=prepare(standard,associations[standard['path']],output/'standard',standard_position,
                    cached/'standard/calibration' if cached else None)
        response=build_response(standard,std['engine']['objects']['primary'][0],output/'response.fits',physical)
        sci=prepare(science,associations[science['path']],output/'science-calibration',science_position,
                    cached/'science-calibration/calibration' if cached else None)
        for sub in ('products','native','qa','QA/PNGs'):(output/sub).mkdir(parents=True,exist_ok=True)
        raw_inputs={**std['bundle']['record']['raw_inputs'],**sci['bundle']['record']['raw_inputs']}
        calibration={'mode':'native_raw_only','sensitivity':response,'extinction':response['extinction'],
                     'raw_inputs':raw_inputs,'groups':[str(std['bundle']['directory']),str(sci['bundle']['directory'])]}
        context=PreparedExposure(science,output,sci['detector'],sci['data'],sci['waveair'],sci['xlo']-99,4,
            science_position-99,{'association':'UNVERIFIED_operator_acquisition_position','raw_spatial_pixel':science_position},
            sci['arc'],output/'response.fits',sci['shift'],sci['sky'],calibration,sci['processed'])
        result=export_spectrum(context,sci['engine'],'primary',output,sci['basename'])
        manifest['results'].append(result)
        # Retain the standard counts separately for independent response diagnostics.
        std['engine']['objects']['primary'].write_to_fits({'PYP_SPEC':'ntt_efosc2_epessto','TARGET':standard['metadata']['OBJECT']},
            str(output/'standard'/'standard-counts.fits'),overwrite=False)
    except Exception as exc:
        manifest['errors'].append({'error':str(exc)})
        raise
    finally:
        (output/'run.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    if render_report:
        from .report import build_report
        manifest['report']=build_report(output)
        (output/'run.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    return manifest
