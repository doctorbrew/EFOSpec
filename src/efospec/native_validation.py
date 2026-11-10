"""Apply native masters for diagnostic sky checks; never publish science spectra."""
import json
from pathlib import Path
import traceback
from contextlib import redirect_stdout,redirect_stderr
import numpy as np
from astropy import units as u
from .inventory import sha256
from .native_calibration import save_json


def validate_native_run(run_dir, output):
    import pypeit
    from pypeit.images.buildimage import BiasImage,buildimage_fromlist
    from pypeit.flatfield import FlatImages
    from pypeit.slittrace import SlitTraceSet
    from pypeit.wavetilts import WaveTilts
    from pypeit.wavecalib import WaveCalib
    from pypeit.core.wave import vactoair
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
    from .reduction_checks import check_flexure, check_red_sky
    from .native_wavelength import validate_solution
    run_dir=Path(run_dir).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    manifest_path=run_dir/'run.json';manifest=json.loads(manifest_path.read_text())
    if manifest['status']=='running':raise ValueError('native calibration is still running')
    if manifest.get('pypeit_version') != pypeit.__version__:
        raise ValueError('incompatible PypeIt calibration run; rebuild from raw inputs')
    inputs=json.loads((run_dir/'inputs.json').read_text())
    frames={f['path']:f for f in inputs['frames']}
    report={'method':'native_master_processing_and_sky_diagnostic','calibration_run':str(run_dir),
        'calibration_manifest_sha256':sha256(manifest_path),'status':'running',
        'science_reduction_ready':False,'pypeit_version':pypeit.__version__,'results':[],'errors':[],'skipped':[]}
    report['source_sha256']={p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')}
    save_json(output/'validation.json',report)
    inst=EFOSpecEFOSC2Spectrograph();par=inst.profile_parameters('full')
    for group in manifest['groups']:
        if group['status']!='calibrations_built':
            report['skipped'].append({'group':group['id'],'reason':'calibration group failed'})
            continue
        try:
            directory=run_dir/group['id']
            for name,digest in group['products'].items():
                if sha256(directory/name)!=digest:raise ValueError('native calibration product changed')
            bias=BiasImage.from_file(next((directory/'Calibrations').glob('Bias_*.fits')))
            flats=FlatImages.from_file(next((directory/'Calibrations').glob('Flat_*.fits')))
            slits=SlitTraceSet.from_file(next((directory/'Calibrations').glob('Slits_*.fits.gz')))
            # Rebuild from hash-verified masters; do not trust an unhashed sidecar.
            tilts=WaveTilts.from_file(next((directory/'Calibrations').glob('Tilts_*.fits')))
            wave=WaveCalib.from_file(next((directory/'Calibrations').glob('WaveCalib_*.fits')))
            # Reapply current scientific gates, even to older successful runs.
            for fit in wave.wv_fits:
                validate_solution(fit,group['setup']['grism'],filter_name=group['setup']['filter'])
            slitmask=slits.slit_img()
            vacuum=wave.build_waveimg(tilts.fit2tiltimg(slitmask),slits)
            waveair=vactoair(vacuum*u.AA).value
            valid=(slitmask>=0)&np.isfinite(vacuum)&(vacuum>0)
            columns=np.flatnonzero(valid.all(axis=0))
            if len(columns)<45:raise ValueError('native map has insufficient common slit coverage')
            x0,x1=int(columns[0])+5,int(columns[-1])-4
        except Exception as exc:
            report['errors'].append({'group':group['id'], 'stage':'load_calibrations',
                'error':str(exc), 'exception_type':type(exc).__name__,
                'associated_exposures':group['associated_exposures']})
            (output/(group['id']+'-calibration-error.log')).write_text(traceback.format_exc())
            save_json(output/'validation.json',report)
            continue
        for raw in group['associated_exposures']:
            entry={'raw':raw,'raw_sha256':frames[raw]['sha256'],'group':group['id'],
                'setup':group['setup'],'role':frames[raw]['role']}
            with (output/(Path(raw).stem+'.log')).open('w') as log,redirect_stdout(log),redirect_stderr(log):
                try:
                    if sha256(Path(raw))!=entry['raw_sha256']:raise ValueError('raw input changed')
                    science=buildimage_fromlist(inst,1,par['scienceframe'],[raw],bias=bias,
                                               flatimages=flats,slits=slits,ignore_saturation=False)
                    good=science.select_flag(invert=True)&np.isfinite(science.ivar)&(science.ivar>0)
                    if not good.any():raise ValueError('native processed science has no valid pixels')
                    entry.update(processing={'bias':True,'pixel_flat':True,'illumination_flat':True,
                        'overscan':False,'dark':False,'cosmic_ray_premask':False},
                        unmasked_fraction=float(good.mean()),units='electrons')
                    data=np.where(good,science.image,np.nan)[:,x0:x1]
                    directory=output/'checks'/Path(raw).stem
                    metadata={'raw':raw,'raw_sha256':entry['raw_sha256'],
                        'object':frames[raw]['metadata']['OBJECT'],'setup':group['setup'],
                        'data_unit':'electrons','calibration_group':group['id'],
                        'calibration_manifest_sha256':report['calibration_manifest_sha256']}
                    if group['setup']['grism']=='Gr16':
                        red=check_red_sky(data,waveair[:,x0:x1],directory,metadata)
                        entry.update(status='processed_unvalidated',
                            red_sky_comparison=red['correlation'],review_file=str(directory/'check.json'),
                            reason='5577 A outside Gr16 coverage; no validated independent red-sky diagnostic yet')
                    else:
                        shift,qa=check_flexure(data,waveair[:,x0:x1],directory,metadata)
                        entry.update(status='sky_measured',sky_flexure=qa,
                            note='Measured native arc-to-science offset; not applied or accepted as final wavelength calibration.')
                    if sha256(Path(raw))!=entry['raw_sha256']:raise ValueError('raw input changed during processing')
                    report['results'].append(entry)
                except Exception as exc:
                    traceback.print_exc();entry.update(error=str(exc),diagnostics=getattr(exc,'diagnostics',{}))
                    report['errors'].append(entry)
            save_json(output/'validation.json',report)
    report['status']='complete' if not report['errors'] and not report['skipped'] else 'incomplete'
    save_json(output/'validation.json',report)
    return report
