"""Re-extract saved detector windows into immutable, reproducible revisions."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from astropy.io import fits

from .inventory import inspect_file, sha256
from .products import PreparedExposure, export_spectrum
from .recipes import DetectorWindow, sky_mask, validate_recipe
from .run_paths import resolve_result_paths


def reference_directory():
    return Path(__file__).resolve().parents[2]/'trunk/src/ntt'


class Exposure:
    """Verified inputs for a single saved exposure, independent of browser state."""
    def __init__(self, run, product, reference_root=None):
        from pypeit.specobjs import SpecObjs
        from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
        self.run = Path(run).resolve()
        manifest_path = self.run/'run.json'
        self.manifest = json.loads(manifest_path.read_text())
        matches = [r for r in self.manifest['results'] if Path(r['product']).name == product]
        if len(matches) != 1 or Path(product).name != product:
            raise ValueError('unknown or ambiguous exposure')
        self.result = resolve_result_paths(matches[0], self.run)
        self.basename = product[:-7]
        self.images_path = self.run/'native'/(self.basename+'_images.npz')
        raw = Path(self.result['raw'])
        if sha256(raw) != self.result['raw_sha256']:
            raise ValueError('raw input changed since the saved reduction')
        self.frame = inspect_file(raw)
        if self.frame['issues'] or self.frame['role'] not in ('science','standard_candidate'):
            raise ValueError('saved exposure requires valid raw EFOSC2 spectroscopy')
        root = Path(reference_root or reference_directory()).resolve()
        calibration = self.result.get('calibration')
        sens_record = self.result['sensitivity']
        if calibration:
            sens = Path(sens_record['path'])
            extinction = Path(self.result['extinction']['path'])
            for path, digest in calibration['raw_inputs'].items():
                if sha256(Path(path)) != digest:
                    raise ValueError('raw calibration input changed')
            if sha256(self.images_path) != self.result['images_sha256']:
                raise ValueError('native processed image changed')
        else:
            sens = root/'archive/efosc/sens'/self.result['grism']/self.frame['setup']['filter']/Path(sens_record['path']).name
            extinction = root/'standard/extinction/extinction_lasilla.dat'
        for path, record in ((sens,sens_record), (extinction,self.result['extinction'])):
            if sha256(path) != record['sha256']:
                raise ValueError(f'calibration input changed: {path.name}')
        self.hashes = {'raw':sha256(raw), 'images':sha256(self.images_path),
            'manifest':sha256(manifest_path), 'native':sha256(Path(self.result['native_spec1d'])),
            'sensitivity':sha256(sens), 'extinction':sha256(extinction)}
        with np.load(self.images_path, allow_pickle=False) as images:
            self.images = {key:images[key] for key in images.files}
        data, wave = self.images['data'], self.images['waveair']
        xlo, ymin = int(self.images['spatial_origin']), int(self.images['raw_y_origin'])
        self.window = DetectorWindow(tuple(data.shape), (ymin, 99+xlo))
        if data.shape != wave.shape:
            raise ValueError('saved science and wavelength geometry disagree')
        with fits.open(raw) as hdus:
            detector = EFOSpecEFOSC2Spectrograph().get_detector_par(1, hdus)
            expected = hdus[0].data[ymin:ymin+data.shape[0],99+xlo:99+xlo+data.shape[1]].astype(float)
        if not calibration and not np.array_equal(data, expected*self.frame['metadata']['ESO DET OUT1 GAIN'], equal_nan=True):
            raise ValueError('saved electrons do not match the recorded raw detector window')
        self.native = SpecObjs.from_fitsfile(self.result['native_spec1d'])[0]
        target = self.result['target']
        self.context = PreparedExposure(self.frame, root, detector, data, wave, xlo, ymin,
            target['hint_trimmed_pixel'], target, self.result['arc'], sens,
            self.result['sky_flexure']['shift_angstrom'], self.result['sky_flexure'], calibration,
            {k.removeprefix('processed_'):v for k,v in self.images.items() if k.startswith('processed_')} or None)

    def default_recipe(self):
        mode='bounded' if self.result.get('processing',{}).get('sky_policy')=='bounded_two_sided_pypeit' else 'automatic'
        return dict(schema_version=1, engine_version='3.0.0',
            coordinates='raw_detector_pixels_zero_based', input_sha256=dict(self.hashes),
            source_mode='automatic', objects=[], sky={'mode':mode,'include':[],'exclude':[]})

    def primary_object(self):
        row = self.window.shape[0]//2
        spec, spat = self.window.to_raw(row, self.native.TRACE_SPAT[row])
        return dict(id='primary', label=self.result['object'], kind='point', spec=spec, spat=spat,
                    fwhm=float(np.nanmedian(self.native.FWHM)), radius=float(self.native.BOX_R_PIX))


def expand_archive_window(exposure, padding):
    """Explicit, hash-bound expansion using the same archived wavelength map.

    Existing calibrated pixels must reproduce exactly. Processed/raw-only runs
    require their own calibrated window preparation and cannot use this bridge.
    """
    import hashlib
    from .archive_calibration import fit_arc
    if type(padding) is not int or not 0<=padding<=100:
        raise ValueError('spatial padding must be an integer from 0 to 100 pixels')
    if not padding:return exposure
    c=exposure.context
    if c.calibration or c.processed:
        raise ValueError('expanding a processed exposure requires recalibration of the larger window')
    setup=c.frame['setup']
    arc=Path(c.reference_root)/'archive/efosc/arc'/setup['grism']/setup['filter']/setup['slit']/Path(c.arc_qa['arc']).name
    if sha256(arc)!=c.arc_qa['arc_sha256']:raise ValueError('archive arc changed before crop expansion')
    wave,qa=fit_arc(arc)
    if qa['identifications_sha256']!=c.arc_qa['identifications_sha256']:
        raise ValueError('archive line identifications changed before crop expansion')
    old=c.spatial_origin;nx=c.data.shape[1]
    lo=max(0,old-padding);hi=min(wave.shape[1],old+nx+padding)
    with fits.open(c.frame['path']) as hdus:
        data=hdus[0].data[c.raw_y_origin:c.raw_y_origin+c.data.shape[0],99+lo:99+hi].astype(float)*c.frame['metadata']['ESO DET OUT1 GAIN']
    wave=wave[:,lo:hi]+c.shift
    sl=slice(old-lo,old-lo+nx)
    if not np.array_equal(data[:,sl],c.data,equal_nan=True) or not np.array_equal(wave[:,sl],c.waveair):
        raise ValueError('expanded pixels do not reproduce the saved calibrated window')
    exposure.context=replace(c,data=data,waveair=wave,spatial_origin=lo)
    exposure.window=DetectorWindow(tuple(data.shape),(c.raw_y_origin,99+lo))
    exposure.images=dict(exposure.images,data=data,waveair=wave)
    # Outside the original crop there is no previous model. Preserve that fact.
    previous=np.full(data.shape,np.nan);previous[:,sl]=exposure.images['sky']
    exposure.images['sky']=previous
    for key in ('trace','found_traces'):
        if key in exposure.images:exposure.images[key]=exposure.images[key]+old-lo
    exposure.hashes=dict(exposure.hashes,expanded_window=hashlib.sha256(
        data.tobytes()+wave.tobytes()+str(exposure.window).encode()).hexdigest())
    # Native trace coordinates belong to the parent window; primary_object is
    # obtained by callers before expansion. Candidate images are shifted above.
    return exposure


def reextract(run, product, recipe, output, reference_root=None, *, render_report=True, failed=False):
    """Run the same PypeIt engine as rapid reduction; never reuse an output folder."""
    import pypeit
    from .extraction import extract_spectra
    exposure_type = FailedExposure if failed else Exposure
    exposure = exposure_type(run, product, reference_root)
    exposure=expand_archive_window(exposure,recipe.get('spatial_padding_pixels',0))
    recipe = validate_recipe(recipe, exposure.window, exposure.hashes)
    if recipe['sky']['mode']=='polynomial':
        raise ValueError('Use background-extract for polynomial boxcar extraction; it is not a PypeIt optimal-extraction recipe.')
    if failed and recipe['source_mode'] != 'manual':
        raise ValueError('failed exposure recovery requires an explicit manual source recipe')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    for sub in ('products','native','qa','QA/PNGs','source'):
        (output/sub).mkdir(parents=True)
    (output/'recipe.json').write_text(json.dumps(recipe, indent=2, allow_nan=False)+'\n')
    hashes = {}
    for path in sorted(Path(__file__).parent.glob('*.py')):
        shutil.copyfile(path, output/'source'/path.name)
        hashes[path.name] = sha256(path)
    manifest = dict(schema_version=1, status='EXPERIMENTAL',
        method='archive_calibration_bridge_with_native_PypeIt_extraction',
        input_dir=exposure.manifest['input_dir'], output_dir=str(output),
        parent_run=str(exposure.run), parent_product=product, input_sha256=exposure.hashes,
        recipe_sha256=sha256(output/'recipe.json'), pypeit_version=pypeit.__version__,
        detector_window={'shape':list(exposure.window.shape),'origin':list(exposure.window.origin),
                         'padding_pixels':recipe.get('spatial_padding_pixels',0)},
        python=sys.executable, python_version=sys.version.split()[0], numpy_version=np.__version__,
        source_sha256=hashes, limitations=exposure.manifest.get('limitations', [])+[
            ('Explicitly expands the archive-calibrated window; original pixels reproduce exactly.'
             if recipe.get('spatial_padding_pixels',0) else 'Reuses the saved detector window and calibration; no new raw calibration fit.'),
            'Manual anchors seed PypeIt tracing; the fitted trace/profile may move.',
            'Separated sources only; no host subtraction or validated extended-source optimal model.',
            'Shared sky fitting may correlate source errors.'], results=[], errors=[], skipped=[])
    if exposure.context.calibration:
        manifest['method'] = 'native_raw_calibration_with_PypeIt_extraction'
    try:
        context = exposure.context
        manual = None
        if recipe['source_mode'] == 'manual':
            manual = [dict(obj, spec=exposure.window.to_local(obj['spec'],obj['spat'])[0],
                           spat=exposure.window.to_local(obj['spec'],obj['spat'])[1]) for obj in recipe['objects']]
        selected_sky = sky_mask(recipe, exposure.window)
        sky_model = sky_trace = None
        background_selection = None
        if recipe['sky']['mode']=='pypeit_local':
            from .local_sky import exposure_sky_inputs
            selected_sky,sky_trace,background_selection=exposure_sky_inputs(exposure,recipe)
            sky_model={key:recipe['sky'][key] for key in ('degree','sigma_clip')}
        engine = extract_spectra(context.data, context.waveair, context.detector,
            exposure_time=context.frame['metadata']['EXPTIME'],
            read_noise=context.frame['metadata']['ESO DET OUT1 RON'], output=output,
            basename=exposure.basename, target_position=context.hint-context.spatial_origin,
            manual=manual, sky_input_mask=selected_sky, processed=context.processed,
            sky_model=sky_model, sky_trace=sky_trace,bounded_background=recipe['sky']['mode']=='bounded')
        if background_selection is not None:
            engine['background_fit']['selection']=background_selection
        sources = recipe['objects'] if manual else [dict(id='primary',label=exposure.result['object'])]
        for obj in sources:
            identity = obj['id']
            basename = exposure.basename if identity == 'primary' else exposure.basename+'_obj_'+identity
            selected = context
            if manual:
                selected = replace(context, hint=obj['spat']-99,
                    hint_info={'association':('recipe_selected_unverified' if recipe['sky']['mode']=='pypeit_local' else 'operator_selected'), 'object_id':identity,
                               'requested':obj, 'recipe_sha256':manifest['recipe_sha256']})
            result = export_spectrum(selected, engine, identity, output, basename,
                                     label=obj['label'] if manual else None)
            result['object_id'] = identity
            manifest['results'].append(result)
        # Detect edits made to any immutable input during extraction.
        refreshed = exposure_type(run, product, reference_root)
        refreshed=expand_archive_window(refreshed,recipe.get('spatial_padding_pixels',0))
        if refreshed.hashes != exposure.hashes:
            raise ValueError('input files changed during extraction')
    except Exception as exc:
        manifest['errors'].append({'object':exposure.result['object'], 'error':str(exc),
            'code':getattr(exc,'code',type(exc).__name__), 'diagnostics':getattr(exc,'diagnostics',{})})
        raise
    finally:
        (output/'run.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    if render_report:
        from .report import build_report
        manifest['report'] = build_report(output)
        (output/'run.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    return manifest


class FailedExposure(Exposure):
    """Verified recovery of a source-selection failure, before any product exists."""
    def __init__(self, run, raw_name, reference_root=None):
        from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
        from .archive_calibration import fit_arc
        from .naming import science_stem
        self.run = Path(run).resolve()
        manifest_path = self.run/'run.json'
        self.manifest = json.loads(manifest_path.read_text())
        if self.manifest.get('flux_calibration')=='same-night':
            from .native_recovery import load_failed
            load_failed(self,raw_name)
            return
        errors = [e for e in self.manifest['errors'] if Path(e['path']).name == raw_name
                  and e.get('code') in {'source_selection_required','background_support_required'}]
        if len(errors) != 1 or Path(raw_name).name != raw_name:
            raise ValueError('unknown or ambiguous failed exposure')
        error = errors[0]; info = error['diagnostics']
        if not {'raw_sha256','arc','sensitivity','extinction_sha256'} <= info.keys():
            raise ValueError('failed exposure lacks calibration records; rerun with the current reducer')
        raw = Path(error['path'])
        if sha256(raw) != info['raw_sha256']: raise ValueError('raw input changed since source failure')
        self.frame = inspect_file(raw)
        if self.frame['issues']:raise ValueError('invalid failed-exposure metadata')
        self.images_path = self.run/'native'/Path(info['diagnostic_file']).name
        with np.load(self.images_path,allow_pickle=False) as saved:
            self.images = {key:saved[key] for key in saved.files}
        data,wave = self.images['data'],self.images['waveair']
        y0,x0 = info['spectral_origin_in_raw_image'],info['spatial_origin_in_raw_image']
        self.window = DetectorWindow(tuple(data.shape),(y0,x0))
        with fits.open(raw) as hdus:
            detector = EFOSpecEFOSC2Spectrograph().get_detector_par(1,hdus)
            expected = hdus[0].data[y0:y0+data.shape[0],x0:x0+data.shape[1]].astype(float)*self.frame['metadata']['ESO DET OUT1 GAIN']
        if not np.array_equal(data,expected,equal_nan=True):
            raise ValueError('failed diagnostic pixels do not match raw exposure')
        root = Path(reference_root or reference_directory()).resolve()
        setup,h = self.frame['setup'],self.frame['metadata']
        arc = root/'archive/efosc/arc'/setup['grism']/setup['filter']/setup['slit']/Path(info['arc']['arc']).name
        sens = root/'archive/efosc/sens'/setup['grism']/setup['filter']/Path(info['sensitivity']['path']).name
        extinction = root/'standard/extinction/extinction_lasilla.dat'
        for path,digest in [(arc,info['arc']['arc_sha256']),(sens,info['sensitivity']['sha256']),
                             (extinction,info['extinction_sha256'])]:
            if sha256(path) != digest:raise ValueError(f'calibration input changed: {path.name}')
        arcwave,arcqa = fit_arc(arc)
        if arcqa['identifications_sha256'] != info['arc']['identifications_sha256']:
            raise ValueError('archive line identifications changed since source failure')
        shift = info['sky_flexure']['shift_angstrom'];xlo=x0-99
        if not np.array_equal(wave,arcwave[:,xlo:xlo+data.shape[1]]+shift):
            raise ValueError('failed diagnostic wavelength map does not match calibration')
        self.hashes = {'raw':sha256(raw),'images':sha256(self.images_path),
            'manifest':sha256(manifest_path),'arc':sha256(arc),
            'identifications':arcqa['identifications_sha256'], 'sensitivity':sha256(sens),'extinction':sha256(extinction)}
        self.basename=science_stem(h['OBJECT'],h['DATE-OBS'],setup['grism'],setup['filter'],setup['slit'])+'_1'
        hint=float(info['expected_spatial_pixel'])+xlo
        self.context=PreparedExposure(self.frame,root,detector,data,wave,xlo,y0,hint,
            info['target_association'],arcqa,sens,shift,info['sky_flexure'])
        self.result={'object':h['OBJECT']}
        self.candidates=[]
        for candidate in info['candidates']:
            self.candidates.append(dict(candidate,raw_spatial_pixel=candidate['spatial_pixel']+x0))

    def primary_object(self):
        raise ValueError('failed exposure has no verified primary object; select a candidate explicitly')


def prepare_recovery(run, raw_name, output, reference_root=None):
    """Write candidate recipes for review, without assigning an astrophysical identity."""
    exposure=FailedExposure(run,raw_name,reference_root)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    review={'raw':raw_name,'status':'TARGET_IDENTITY_REQUIRES_REVIEW','candidates':[]}
    for index,candidate in enumerate(exposure.candidates):
        recipe=exposure.default_recipe();recipe['source_mode']='manual'
        recipe['objects']=[dict(id='primary',label=exposure.result['object'],kind='point',
            spec=float(exposure.window.origin[0]+exposure.window.shape[0]//2),
            spat=candidate['raw_spatial_pixel'],fwhm=4.,radius=7.)]
        recipe=validate_recipe(recipe,exposure.window,exposure.hashes)
        path=output/f'candidate-{index+1}.json'
        path.write_text(json.dumps(recipe,indent=2,allow_nan=False)+'\n')
        review['candidates'].append(dict(candidate,recipe=str(path),
            warning='Position hypothesis only; inspect acquisition data, trace width, and sky regions before replay.'))
    (output/'review.json').write_text(json.dumps(review,indent=2,allow_nan=False)+'\n')
    return review
