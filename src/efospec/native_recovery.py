"""Reconstruct a saved native review window, verifying pixels against its masters."""
import json
from pathlib import Path
import numpy as np
from astropy import units as u
from .inventory import sha256
from .recipes import DetectorWindow
from .products import PreparedExposure


def load_failed(exposure, raw_name):
    from pypeit.core.wave import vactoair
    from .native_calibrations import load_calibrations, process_exposure
    run=exposure.run
    frames=json.loads((run/'inputs.json').read_text())['frames']
    matches=[f for f in frames if Path(f['path']).name==raw_name]
    if len(matches)!=1:raise ValueError('unknown or ambiguous raw exposure')
    frame=matches[0]
    if sha256(Path(frame['path']))!=frame['sha256']:raise ValueError('raw input changed')
    errors=[e for e in exposure.manifest['errors'] if e.get('path')==frame['path']]
    diagnostics=[e['diagnostics']['diagnostic_file'] for e in errors if e.get('diagnostics',{}).get('diagnostic_file')]
    counts=[c for c in exposure.manifest.get('review_counts',[]) if c['raw']==frame['path']]
    if not errors:raise ValueError('exposure has no recorded failure')
    if diagnostics:path=Path(diagnostics[-1])
    elif len(counts)==1:path=Path(counts[0]['images'])
    else:raise ValueError('No saved native detector window; calibration recovery is required first.')
    path=path.resolve()
    if not path.is_relative_to(run):raise ValueError('diagnostic window is outside this run')
    with np.load(path,allow_pickle=False) as a:images={k:a[k] for k in a.files}
    data=images['data'];ny,nx=data.shape
    association=next(e['raw_calibrations'] for e in json.loads((run/'setup-checks.json').read_text())['exposures'] if e['path']==frame['path'])
    groups=[]
    for p in run.rglob('calibration.json'):
        rec=json.loads(p.read_text())
        if rec.get('setup')==frame['setup'] and all(rec['associations'][k]['sha256']==association[k]['sha256'] for k in ('bias','flat','arc')):groups.append(p)
    if not groups:raise ValueError('No matching saved native calibration group')
    bundle=load_calibrations(sorted(groups)[0].parent);image=process_exposure(frame,bundle)
    # Locate the exact saved crop, rather than assuming a detector origin or grid.
    positions=np.argwhere(image.image==data[ny//2,nx//2]);windows=[]
    for yy,xx in positions:
        y,x=int(yy-ny//2),int(xx-nx//2)
        if y>=0 and x>=0 and np.array_equal(image.image[y:y+ny,x:x+nx],data,equal_nan=True):windows.append((y,x))
    if len(windows)!=1:raise ValueError('Saved pixels do not identify a unique calibrated detector window')
    y,x=windows[0];cut=np.s_[y:y+ny,x:x+nx]
    sky_path=path.parent.parent/'sky-check.json';sky=json.loads(sky_path.read_text())
    if sky['raw_sha256']!=frame['sha256']:raise ValueError('sky check belongs to another raw exposure')
    shift=sky['shift_angstrom'];wave=vactoair(bundle['wavevac'][cut]*u.AA).value+shift
    if not np.array_equal(images['waveair'],wave):raise ValueError('Saved native wavelength map changed')
    planes={k:np.broadcast_to(getattr(image,k),image.image.shape)[cut].copy() for k in ('ivar','rn2img','base_var','img_scale')}
    planes['bad_pixels']=image.fullmask.flagged()[cut].copy()
    if 'found_traces' not in images:images['found_traces']=np.asarray([images['trace']])
    if not len(images['found_traces']):raise ValueError('No saved trace candidate for manual recovery')
    arc={'reference_lines':vactoair(np.array(bundle['record']['wavelength']['reference_lines_vacuum'])*u.AA).value.tolist()}
    exposure.frame=frame;exposure.images=images;exposure.images_path=path
    exposure.window=DetectorWindow(data.shape,(y,x));exposure.result={'object':frame['metadata']['OBJECT']}
    exposure.hashes={'raw':frame['sha256'],'images':sha256(path),'manifest':sha256(run/'run.json'),'calibration':sha256(sorted(groups)[0]),'sky':sha256(sky_path)}
    exposure.context=PreparedExposure(frame,run,image.detector,data,wave,x-99,y,548-99,{},arc,None,shift,sky,bundle['record'],planes)
    exposure.candidates=[{'raw_spatial_pixel':float(t[ny//2]+x)} for t in images['found_traces']]


def extract_native(run, raw_name, recipe, output):
    """Replay explicit raw geometry through bounded PypeIt and same-night response gates."""
    from .revisions import FailedExposure
    from .recipes import validate_recipe
    from .native_reduction import prepare
    from .daily_reduction import select_response
    from .native_calibration import save_json
    from .products import export_spectrum
    from .run_record import snapshot_sources
    e=FailedExposure(run,raw_name)
    if not e.context.calibration:raise ValueError('Native recovery requires native raw calibration')
    recipe=validate_recipe(recipe,e.window,e.hashes)
    if recipe['source_mode']!='manual' or len(recipe['objects'])!=1 or recipe['sky']['mode']!='polynomial':
        raise ValueError('Select one source and explicit polynomial background bands')
    if len(recipe['sky']['include'])!=2 or any(not 15<=hi-lo<=50 for lo,hi in recipe['sky']['include']):
        raise ValueError('Select two finite 15–50 pixel background bands')
    if not e.context.sky_qa.get('held_out_6363_pass'):raise ValueError('Parent wavelength check failed; flux recovery withheld')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    recipe['sky']['mode']='pypeit_local';save_json(output/'recipe.json',recipe)
    frame=e.frame;assoc=next(x['raw_calibrations'] for x in json.loads((e.run/'setup-checks.json').read_text())['exposures'] if x['path']==frame['path'])
    groups=[p for p in e.run.rglob('calibration.json') if sha256(p)==e.hashes['calibration']]
    if not groups:raise ValueError('Native calibration group changed')
    obj=recipe['objects'][0];row=int(obj['spec']-e.window.origin[0])
    candidate=int(np.argmin(abs(e.images['found_traces'][:,row]+e.window.origin[1]-obj['spat'])))+1
    position=float(e.window.origin[1]+e.window.shape[1]//2)
    selection=dict(recipe_path=str(output/'recipe.json'),recipe_sha256=sha256(output/'recipe.json'),raw_sha256=frame['sha256'],
        parent_run=str(e.run),raw_name=raw_name,object=e.result['object'],identity=dict(method='operator_background',candidate=candidate,evidence='Explicit manual raw-coordinate recipe; identity not newly inferred'))
    manifest=dict(night=e.manifest['night'],input_dir=e.manifest['input_dir'],output_dir=str(output),parent_run=str(e.run),parent_sha256=sha256(e.run/'run.json'),
        method='native_raw_calibration_manual_recovery',flux_calibration='same-night',status='EXPERIMENTAL',results=[],errors=[],skipped=[],
        standards=e.manifest['standards'],held_out=e.manifest.get('held_out',[]),source_sha256=snapshot_sources(output),
        limitations=['Explicit manual background trial; not accepted automatically.','Absolute flux and host deblending remain unvalidated.'])
    try:
        p=prepare(frame,assoc,output,position,cached=groups[0].parent,arc_supported_only=True,spatial_half_width=(e.window.shape[1]-1)//2,reviewed_source=selection)
        chosen=select_response(frame,e.manifest['standards']);response=chosen['fit']['response']
        calibration=dict(mode='native_raw_only',sensitivity=response,extinction=response['extinction'],raw_inputs={**chosen['calibration']['raw_inputs'],**p['bundle']['record']['raw_inputs']},groups=[chosen['counts']['calibration_directory'],str(groups[0].parent)])
        context=PreparedExposure(frame,e.run,p['detector'],p['data'],p['waveair'],p['xlo']-99,p['ylo'],position-99.,dict(association='UNVERIFIED_manual_background_recovery',**p['engine']['source_selection']),p['arc'],Path(response['path']),p['shift'],p['sky'],calibration,p['processed'])
        result=export_spectrum(context,p['engine'],'primary',output,p['basename'],label=e.result['object'])
        if result['valid_flux_fraction']<=0:raise ValueError('No supported calibrated flux samples')
        result['role']='science';manifest['results'].append(result)
        if FailedExposure(run,raw_name).hashes!=e.hashes:raise ValueError('Recovery inputs changed')
        manifest['execution_status']='complete'
    except Exception as exc:
        manifest['execution_status']='failed';manifest['errors'].append(dict(path=frame['path'],object=e.result['object'],error=str(exc),code=getattr(exc,'code',type(exc).__name__),diagnostics=getattr(exc,'diagnostics',{})))
        raise
    finally:save_json(output/'run.json',manifest)
    return manifest
