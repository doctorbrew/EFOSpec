"""Bounded placement search around an explicitly reviewed aperture.

Rank predictions on common withheld pixels, never aperture flux or training chi2.
This interpolates local sky+host and does not identify or deblend a transient.
"""
from copy import deepcopy
from pathlib import Path
import numpy as np
from .local_sky import fit_background, validate_bounded_mask, BackgroundSupportError


def search(data, ivar, wave, trace, recipe, x_origin, *, offsets=(-2, 0, 2), degrees=(2, 3)):
    bands=recipe['sky']['include'];obj=recipe['objects'][0]
    if len(bands)!=2 or any(not 15<=hi-lo<=50 for lo,hi in bands):
        raise ValueError('Search requires two reviewed 15–50 pixel bands')
    if not offsets or any(not np.isfinite(v) or abs(v)>5 for v in offsets):
        raise ValueError('Band search is limited to five pixels around reviewed bands')
    x=np.arange(data.shape[1])+x_origin
    candidates=[];trials=[]
    for offset in offsets:
        moved=[[bands[0][0]-offset,bands[0][1]-offset],
               [bands[1][0]+offset,bands[1][1]+offset]]
        mask=np.broadcast_to(((x>=moved[0][0])&(x<moved[0][1]))|((x>=moved[1][0])&(x<moved[1][1])),data.shape).copy()
        for lo,hi in recipe['sky']['exclude']:mask[:,(x>=lo)&(x<hi)]=False
        # Keep the narrow reviewed core protected at every trace row.
        mask &= abs(x[None,:]-trace[:,None])>max(obj['radius']+.5,1.5*obj['fwhm'])
        if moved[0][0]<x[0] or moved[1][1]>x[-1]+1:
            trials.append(dict(offset=offset,status='rejected',reason='band outside window'));continue
        try:validate_bounded_mask(mask,trace-x_origin,obj['radius'])
        except BackgroundSupportError as exc:
            trials.append(dict(offset=offset,status='rejected',reason=str(exc)));continue
        candidates.append((offset,moved,mask))
    if not candidates:raise ValueError('No legal two-sided placements')
    common=np.logical_and.reduce([c[2] for c in candidates])
    # Shared, spatially interleaved holdout. Keep full geometry and zero its weights.
    holdout=common&(np.arange(data.shape[1])[None,:]%3==0)&np.isfinite(data)&(ivar>0)
    if np.min(np.sum(holdout&(x[None,:]<trace[:,None]),axis=1))<2 or np.min(np.sum(holdout&(x[None,:]>trace[:,None]),axis=1))<2:
        raise ValueError('Insufficient common two-sided holdout for placement comparison')
    tilts=(wave-wave.min())/np.ptp(wave);fits=[]
    for offset,moved,mask in candidates:
        for degree in degrees:
            record=dict(offset=offset,degree=degree,bands=moved)
            try:
                fit=fit_background(data,np.where(holdout,0,ivar),tilts,mask,trace-x_origin,radius=obj['radius'],degree=degree,sigma_clip=recipe['sky']['sigma_clip'])
                record.update(status='fitted',background=fit['summary'])
                fits.append((record,fit,mask))
            except BackgroundSupportError as exc:record.update(status='failed',reason=str(exc))
            trials.append(record)
    if not fits:raise BackgroundSupportError('No placement/degree fit converged',trials=trials)
    rows=np.logical_and.reduce([f[1]['valid_rows'] for f in fits]);use=holdout&rows[:,None]
    if rows.mean()<.9 or use.sum()<50:raise ValueError('Insufficient common valid holdout rows')
    for record,fit,mask in fits:
        residual=(data-fit['sky'])*np.sqrt(np.maximum(ivar,0))
        record['holdout_mean_square']=float(np.mean(residual[use]**2))
        record['holdout_mean_sigma']=float(np.mean(residual[use]))
    selected=min(fits,key=lambda f:(f[0]['holdout_mean_square'],f[0]['degree'],abs(f[0]['offset'])))
    record,_,mask=selected
    final=fit_background(data,ivar,tilts,mask,trace-x_origin,radius=obj['radius'],degree=record['degree'],sigma_clip=recipe['sky']['sigma_clip'])
    revised=deepcopy(recipe);revised['sky'].update(include=record['bands'],degree=record['degree'])
    return revised,final,dict(trials=trials,selected=record,holdout_samples=int(use.sum()),
        selection='minimum common withheld-pixel mean squared standardized residual; no aperture-flux ranking',
        limitations=['Conditional on reviewed aperture and neighbour exclusions; not SN/host deblending.',
                     'Holdout measures prediction in the bands, not beneath the source.',
                     'Small score differences do not establish a unique physical background.'])


def run_search(run, raw, recipe, output):
    from .revisions import FailedExposure
    from .recipes import validate_recipe
    from .native_calibration import save_json
    from .inventory import sha256
    from .run_record import snapshot_sources
    e=FailedExposure(run,raw);recipe=validate_recipe(recipe,e.window,e.hashes)
    if recipe['source_mode']!='manual' or len(recipe['objects'])!=1:
        raise ValueError('Placement search requires one reviewed manual aperture')
    if e.context.processed is None:raise ValueError('Native calibrated pixels required')
    obj=recipe['objects'][0];row=int(obj['spec']-e.window.origin[0])
    traces=e.images['found_traces']+e.window.origin[1]
    trace=traces[np.argmin(abs(traces[:,row]-obj['spat']))].copy();trace+=obj['spat']-trace[row]
    p=e.context.processed;ivar=np.where(p['bad_pixels'],0,p['ivar'])
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    source=snapshot_sources(output)
    selected,fit,record=search(e.context.data,ivar,e.context.waveair,trace,recipe,e.window.origin[1])
    save_json(output/'selected-recipe.json',selected)
    np.savez_compressed(output/'selected-background.npz',**{k:v for k,v in fit.items() if k!='summary'})
    record.update(target=e.result['object'],parent_run=str(e.run),parent_sha256=sha256(e.run/'run.json'),
        raw_sha256=e.frame['sha256'],input_sha256=e.hashes,source_sha256=source,
        final_background=fit['summary'],status='review_only',science_validated=False)
    if FailedExposure(run,raw).hashes!=e.hashes:raise ValueError('Inputs changed during search')
    save_json(output/'search.json',record)
    return record
