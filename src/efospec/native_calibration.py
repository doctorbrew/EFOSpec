"""Native PypeIt calibration execution from selected raw frames only.

This produces reviewable masters and wavelength/tilt maps, not flux-calibrated
science. No imports or reads from the legacy reference directory are needed.
"""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import json
from pathlib import Path
import shutil
import sys
import traceback
import numpy as np
from .inventory import inventory, sha256
from .native_readiness import assess_native_readiness
from .native_wavelength import fit_raw_arc_spectrum, reidentify_raw_arc, GRISMS, physical_lines


def save_json(path, value):
    pending = path.with_suffix('.json.tmp')
    pending.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    pending.replace(path)


def calibration_key(exposure):
    payload = {'setup':exposure['setup'], 'inputs':{role:sorted(zip(
        exposure['raw_calibrations'][role]['files'], exposure['raw_calibrations'][role]['sha256']))
        for role in ('bias','flat','arc')}}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]


def load_native_template(directory, setup):
    """Require an exact setup and unchanged, successfully built native group."""
    from pypeit.wavecalib import WaveCalib
    directory = Path(directory).resolve()
    status_path = directory/'calibration.json'
    association_path = directory/'association.json'
    status = json.loads(status_path.read_text())
    association = json.loads(association_path.read_text())
    if status['status'] != 'calibrations_built' or status['setup'] != setup:
        raise ValueError('native template must be a successful group with the identical setup')
    if association['exposure']['setup'] != setup:
        raise ValueError('native template association has a different setup')
    for name, digest in status['products'].items():
        if sha256(directory/name) != digest:
            raise ValueError('native template calibration product changed')
    for role in ('bias', 'flat', 'arc'):
        selected = association['exposure']['raw_calibrations'][role]
        for path, digest in zip(selected['files'], selected['sha256']):
            if sha256(Path(path)) != digest:
                raise ValueError('native template raw input changed')
    candidates = [directory/name for name in status['products']
                  if Path(name).name.startswith('WaveCalib_')]
    if len(candidates) != 1:
        raise ValueError('native template requires one hash-verified wavelength calibration')
    wave = WaveCalib.from_file(candidates[0])
    method = json.loads(wave.strpar).get('method')
    if method not in {'bounded_physical_line_consensus', 'native_template_reidentify'}:
        raise ValueError('template is not a supported native physical-line solution')
    input_record = {'directory':str(directory), 'calibration_manifest_sha256':sha256(status_path),
        'association_sha256':sha256(association_path), 'wavecalib_sha256':sha256(candidates[0])}
    return wave, input_record


def build_group(exposure, output, *, template=None):
    import pypeit
    from pypeit.metadata import PypeItMetaData
    from pypeit.calibrations import Calibrations
    from pypeit.wavecalib import BuildWaveCalib, WaveCalib
    from pypeit.core.wavecal import autoid
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
    if pypeit.__version__ != '1.14.0':
        raise ValueError('native calibration requires tested PypeIt 1.14.0')
    output = Path(output)
    setup = exposure['setup']
    if setup['grism'] not in GRISMS or setup['binx'] != 2 or setup['biny'] != 2:
        raise ValueError('native calibration supports inspected Gr11/13/16 2x2 frames only')
    inputs, types = [exposure['path']], {Path(exposure['path']).name:'science'}
    for role, kind in [('bias','bias'),('flat','trace,pixelflat,illumflat'),('arc','arc,tilt')]:
        selected = exposure['raw_calibrations'][role]
        if selected['status'] != 'selected':
            raise ValueError(f'{role}: {selected["status"]}')
        for path, digest in zip(selected['files'], selected['sha256']):
            if sha256(Path(path)) != digest: raise ValueError(f'changed raw calibration: {path}')
            inputs.append(path); types[Path(path).name] = kind
    inst = EFOSpecEFOSC2Spectrograph()
    par = inst.profile_parameters('full')
    par['rdx']['redux_path'] = str(output)
    # A lamp-derived explicit solution is supplied below; no built-in template.
    (output/'parameters.cfg').write_text('\n'.join(par.to_config())+'\n')
    lines = physical_lines(); lines.write(output/'physical-lines.ecsv',format='ascii.ecsv')
    metadata = PypeItMetaData(inst,par,files=inputs,strict=True)
    metadata.get_frame_types(user=types); metadata.set_configurations()
    # This isolated group contains exactly the planner-selected inputs.
    metadata.set_calibration_groups(default=True)
    metadata.write(str(output/'frames.txt'),overwrite=False)
    cal = Calibrations.get_instance(metadata,par['calibrations'],inst,output/'Calibrations',qadir=output,reuse_calibs=False)
    cal.set_config(list(metadata['filename']).index(Path(exposure['path']).name),1)
    status = {'status':'running','stage':'initialization','setup':setup,'wave_qa':[]}
    try:
        for step in ['bias','dark','bpm','slits','arc','tiltimg']:
            status['stage'] = step; save_json(output/'calibration.json',status)
            getattr(cal,'get_'+step)()
            if step == 'slits' and (cal.slits is None or cal.slits.nslits != 1):
                raise ValueError('expected one traced EFOSC2 long slit')
        status['stage'] = 'wavelength'; save_json(output/'calibration.json',status)
        builder = BuildWaveCalib(cal.msarc,cal.slits,inst,par['calibrations']['wavelengths'],
                                 ['HeI','ArI'],qa_path=output,msbpm=cal.msbpm)
        spectra, mask = builder.extract_arcs()
        if np.any(mask): raise ValueError('native arc extraction masked the slit')
        kwargs = dict(filter_name=setup['filter'], fwhm=4.*float(setup['slit'].replace('slit','')),
                      nonlinear_counts=float(builder.nonlinear_counts))
        if template is None:
            fit, qa = fit_raw_arc_spectrum(spectra[:,0],setup['grism'],**kwargs)
        else:
            reference, input_record = load_native_template(template, setup)
            status['template'] = input_record
            fit, qa = reidentify_raw_arc(spectra[:,0],setup['grism'],reference.wv_fits[0],
                                         reference.arc_spectra[:,0],**kwargs)
            qa['template'] = input_record
        fit.spat_id = cal.slits.spat_id[0]
        fit.fwhm = 4.*float(setup['slit'].replace('slit',''))
        status['wave_qa'] = [qa]
        wave = WaveCalib(wv_fits=np.array([fit]),arc_spectra=spectra,nslits=1,
            spat_ids=cal.slits.spat_id,PYP_SPEC=inst.name,lamps='HeI,ArI',
            strpar=json.dumps(dict(par['calibrations']['wavelengths'].data,
                                   method=qa['method'])))
        wave.copy_calib_internals(cal.msarc); wave.to_file()
        autoid.arc_fit_qa(fit,outfile=str(output/'arc-fit.png'))
        cal.wv_calib = wave
        for step in ['tilts','flats']:
            status['stage'] = step; save_json(output/'calibration.json',status)
            getattr(cal,'get_'+step)()
        if cal.wavetilts is None or cal.flatimages is None or np.any(cal.slits.mask):
            raise ValueError('native tilt/flat construction is missing or slit is masked')
        slitmask = cal.slits.slit_img()
        tilts = cal.wavetilts.fit2tiltimg(slitmask)
        waveimg = cal.wv_calib.build_waveimg(tilts, cal.slits)
        valid = (slitmask >= 0) & np.isfinite(waveimg) & (waveimg > 0)
        if not valid.any(): raise ValueError('native wavelength image has no valid slit pixels')
        np.savez_compressed(output/'calibrated_geometry.npz',wave_vacuum=waveimg,tilts=tilts,
                            slitmask=slitmask,valid=valid)
        status.update(status='calibrations_built', stage='complete',
            scientific_status='EXPERIMENTAL',science_reduction_ready=False,
            line_list_sha256=sha256(output/'physical-lines.ecsv'),
            parameters_sha256=sha256(output/'parameters.cfg'),
            products={str(p.relative_to(output)):sha256(p) for p in sorted((output/'Calibrations').glob('*')) if p.is_file()},
            limitations=['Raw-calibration execution only; no science extraction or observed-standard sensitivity.',
                         'Wavelength use is restricted to the accepted reference-line bracket.',
                         'Requires independent science-sky, flat/fringe and flux validation.'])
    except Exception as exc:
        status.update(status='failed',error=str(exc),exception_type=type(exc).__name__)
        raise
    finally:
        save_json(output/'calibration.json',status)
    return status


def calibrate_night(paths, output, *, grisms=None, templates=None, group_ids=None):
    """Keep successful raw groups and diagnostic failures in a fresh run."""
    import pypeit
    output = Path(output).resolve(); output.mkdir(parents=True,exist_ok=False)
    (output/'source').mkdir()
    for p in Path(__file__).parent.glob('*.py'):shutil.copyfile(p,output/'source'/p.name)
    report = inventory(paths); readiness = assess_native_readiness(report)
    save_json(output/'inputs.json',report);save_json(output/'readiness.json',readiness)
    if report['errors'] or report['identity_conflicts'] or readiness['invalid_inputs']:
        raise ValueError('resolve invalid raw inputs before native calibration')
    groups = {}
    for exposure in readiness['exposures']:
        if grisms and exposure['setup']['grism'] not in grisms:continue
        key = calibration_key(exposure)
        if key not in groups: groups[key] = {'exposure':exposure, 'associated_exposures':[]}
        groups[key]['associated_exposures'].append(exposure['path'])
    if not groups:raise ValueError('no selected raw calibration groups')
    templates = templates or {}
    if set(templates)-set(groups):raise ValueError('template map contains unknown calibration group IDs')
    if group_ids:
        if set(group_ids)-set(groups):raise ValueError('unknown calibration group IDs')
        groups = {key:value for key,value in groups.items() if key in group_ids}
    run = {'schema_version':1,'method':'native_raw_calibration','status':'running',
        'scientific_status':'EXPERIMENTAL','science_reduction_ready':False,
        'python':sys.executable,'pypeit_version':pypeit.__version__,'numpy_version':np.__version__,
        'source_sha256':{p.name:sha256(p) for p in (output/'source').glob('*.py')},'groups':[]}
    save_json(output/'run.json',run)
    for key, entry in groups.items():
        directory = output/key; directory.mkdir()
        save_json(directory/'association.json',entry)
        print(f'Native calibration {key}: {entry["exposure"]["setup"]}',file=sys.stderr,flush=True)
        with (directory/'execution.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
            try:result=build_group(entry['exposure'],directory,template=templates.get(key))
            except Exception as exc:
                traceback.print_exc()
                status_path=directory/'calibration.json'
                result=json.loads(status_path.read_text()) if status_path.exists() else {'stage':'initialization'}
                result.update(status='failed',error=str(exc),exception_type=type(exc).__name__,
                              traceback_path=str(directory/'execution.log'))
        run['groups'].append({'id':key, 'directory':str(directory),
            'associated_exposures':entry['associated_exposures'], 'setup':entry['exposure']['setup'],**result})
        save_json(output/'run.json',run)
    changed=[f['path'] for f in report['frames'] if sha256(Path(f['path']))!=f['sha256']]
    run['changed_inputs']=changed
    run['status']='complete' if all(g['status']=='calibrations_built' for g in run['groups']) and not changed else 'incomplete'
    save_json(output/'run.json',run)
    return run
