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
        sens_record = self.result['sensitivity']
        # A relocated reference is acceptable only with the recorded content hash.
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
        if not np.array_equal(data, expected*self.frame['metadata']['ESO DET OUT1 GAIN'], equal_nan=True):
            raise ValueError('saved electrons do not match the recorded raw detector window')
        self.native = SpecObjs.from_fitsfile(self.result['native_spec1d'])[0]
        target = self.result['target']
        self.context = PreparedExposure(self.frame, root, detector, data, wave, xlo, ymin,
            target['hint_trimmed_pixel'], target, self.result['arc'], sens,
            self.result['sky_flexure']['shift_angstrom'], self.result['sky_flexure'])

    def default_recipe(self):
        return dict(schema_version=1, engine_version='1.14.0',
            coordinates='raw_detector_pixels_zero_based', input_sha256=dict(self.hashes),
            source_mode='automatic', objects=[], sky={'mode':'automatic','include':[],'exclude':[]})

    def primary_object(self):
        row = self.window.shape[0]//2
        spec, spat = self.window.to_raw(row, self.native.TRACE_SPAT[row])
        return dict(id='primary', label=self.result['object'], kind='point', spec=spec, spat=spat,
                    fwhm=float(np.nanmedian(self.native.FWHM)), radius=float(self.native.BOX_RADIUS))


def reextract(run, product, recipe, output, reference_root=None, *, render_report=True):
    """Run the same PypeIt engine as rapid reduction; never reuse an output folder."""
    import pypeit
    from .extraction import extract_spectra
    exposure = Exposure(run, product, reference_root)
    recipe = validate_recipe(recipe, exposure.window, exposure.hashes)
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
        python=sys.executable, python_version=sys.version.split()[0], numpy_version=np.__version__,
        source_sha256=hashes, limitations=exposure.manifest.get('limitations', [])+[
            'Reuses the saved detector window and calibration; no new raw calibration fit.',
            'Manual anchors seed PypeIt tracing; the fitted trace/profile may move.',
            'Separated sources only; no host subtraction or validated extended-source optimal model.',
            'Shared sky fitting may correlate source errors.'], results=[], errors=[], skipped=[])
    try:
        context = exposure.context
        manual = None
        if recipe['source_mode'] == 'manual':
            manual = [dict(obj, spec=exposure.window.to_local(obj['spec'],obj['spat'])[0],
                           spat=exposure.window.to_local(obj['spec'],obj['spat'])[1]) for obj in recipe['objects']]
        engine = extract_spectra(context.data, context.waveair, context.detector,
            exposure_time=context.frame['metadata']['EXPTIME'],
            read_noise=context.frame['metadata']['ESO DET OUT1 RON'], output=output,
            basename=exposure.basename, target_position=context.hint-context.spatial_origin,
            manual=manual, sky_input_mask=sky_mask(recipe, exposure.window))
        sources = recipe['objects'] if manual else [dict(id='primary',label=exposure.result['object'])]
        for obj in sources:
            identity = obj['id']
            basename = exposure.basename if identity == 'primary' else exposure.basename+'_obj_'+identity
            selected = context
            if manual:
                selected = replace(context, hint=obj['spat']-99,
                    hint_info={'association':'operator_selected', 'object_id':identity,
                               'requested':obj, 'recipe_sha256':manifest['recipe_sha256']})
            result = export_spectrum(selected, engine, identity, output, basename,
                                     label=obj['label'] if manual else None)
            result['object_id'] = identity
            manifest['results'].append(result)
        # Detect edits made to any immutable input during extraction.
        refreshed = Exposure(run, product, reference_root)
        if refreshed.hashes != exposure.hashes:
            raise ValueError('input files changed during extraction')
    except Exception as exc:
        manifest['errors'].append({'object':exposure.result['object'], 'error':str(exc)})
        raise
    finally:
        (output/'run.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    if render_report:
        from .report import build_report
        manifest['report'] = build_report(output)
        (output/'run.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    return manifest
