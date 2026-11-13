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
