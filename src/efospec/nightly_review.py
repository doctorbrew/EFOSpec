"""Replay reviewed local-background searches on fresh native detector pixels."""
import json
from pathlib import Path
import numpy as np
from .inventory import sha256


def validation_policy(selection):
    policy=(selection or {}).get('validation_policy','three-line')
    if policy not in {'three-line','two-anchor','full-spectrum'}:
        raise ValueError('Unknown reviewed wavelength policy')
    return policy


def search_review(selection, frame, data, wave, processed, origin, arguments, output):
    from .revisions import FailedExposure
    from .background_search import search
    from .recipes import DetectorWindow, sky_mask, validate_recipe
    from .native_calibration import save_json
    if not selection.get('dynamic_background',False):return arguments,None
    exposure=FailedExposure(selection['parent_run'],selection['raw_name'])
    path=Path(selection['recipe_path'])
    if sha256(path)!=selection['recipe_sha256'] or exposure.hashes['raw']!=frame['sha256']:
        raise ValueError('Reviewed background inputs changed')
    recipe=validate_recipe(json.loads(path.read_text()),exposure.window,exposure.hashes)
    obj=recipe['objects'][0];old_y,old_x=exposure.window.origin
    traces=exposure.images['found_traces']+old_x;row=int(obj['spec']-old_y)
    seed=traces[np.argmin(abs(traces[:,row]-obj['spat']))].copy();seed+=obj['spat']-seed[row]
    yy=np.arange(len(data))+origin[0];old_yy=np.arange(len(seed))+old_y
    if yy.min()<old_yy.min() or yy.max()>old_yy.max():
        raise ValueError('Fresh window exceeds reviewed trace coverage; no extrapolation')
    trace=np.interp(yy,old_yy,seed)
    ivar=np.where(processed['bad_pixels'],0.,processed['ivar'])
    selected,fit,record=search(data,ivar,wave,trace,recipe,origin[1])
    directory=Path(output)/'dynamic-background';directory.mkdir(exist_ok=False)
    save_json(directory/'recipe.json',selected)
    np.savez_compressed(directory/'search-model.npz',**{k:v for k,v in fit.items() if k!='summary'})
    record.update(parent_run=str(exposure.run),raw_sha256=frame['sha256'],reviewed_recipe_sha256=sha256(path),
                  input_sha256=exposure.hashes,raw_origin_yx=list(origin),final_background=fit['summary'])
    save_json(directory/'search.json',record)
    # Preserve finite geometry separately from detector/cosmic-ray masks.
    mask=sky_mask(selected,DetectorWindow(data.shape,origin))
    x=np.arange(data.shape[1])+origin[1]
    mask &= abs(x[None,:]-trace[:,None])>max(obj['radius']+.5,1.5*obj['fwhm'])
    arguments=dict(arguments,sky_input_mask=mask,sky_trace=trace-origin[1],
                   sky_model={k:selected['sky'][k] for k in ('degree','sigma_clip')})
    return arguments,dict(record=str(directory/'search.json'),sha256=sha256(directory/'search.json'))
