"""Replay an explicit visual identification only on its unchanged exposure."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from .inventory import sha256
from .recipes import validate_recipe


def load_reviewed_sources(path, frames):
    if path is None:
        return {}
    document = json.loads(Path(path).read_text())
    if document.get('schema_version') != 1 or not isinstance(document.get('sources'), list):
        raise ValueError('invalid reviewed-source document')
    by_raw = {Path(f['path']).name: f for f in frames}
    selected = {}
    for item in document['sources']:
        raw = item['raw_name']
        frame = by_raw.get(raw)
        if raw in selected or frame is None:
            raise ValueError('reviewed source must uniquely match a selected raw exposure')
        if item['raw_sha256'] != frame['sha256'] or item['object'] != frame['metadata']['OBJECT']:
            raise ValueError('reviewed-source identity or raw hash does not match')
        identity = item['identity']
        if (identity.get('method') not in {'operator_visual', 'operator_background'} or not identity.get('evidence')
                or type(identity.get('candidate')) is not int or identity['candidate'] < 1):
            raise ValueError('reviewed source needs explicit identification or background-review evidence')
        recipe_path = Path(item['recipe_path'])
        if not recipe_path.is_absolute() or not Path(item['parent_run']).is_absolute():
            raise ValueError('reviewed-source references must be absolute')
        if sha256(recipe_path) != item['recipe_sha256']:
            raise ValueError('reviewed-source recipe changed')
        selected[raw] = deepcopy(item)
    return selected


def native_review_arguments(selection, frame, shape, origin, output):
    """Reselect verified raw-detector geometry on freshly calibrated pixels.

    This is a new native extraction, not replay of the old image/background.
    The source identification remains tied to the unchanged raw exposure.
    Fresh background support and the fitted trace must pass native gates.
    """
    from .local_sky import validate_bounded_mask
    recipe_path=Path(selection['recipe_path'])
    if (sha256(recipe_path)!=selection['recipe_sha256'] or
            sha256(Path(frame['path']))!=selection['raw_sha256']):
        raise ValueError('reviewed raw exposure or geometry changed')
    recipe=json.loads(recipe_path.read_text())
    if (recipe.get('coordinates')!='raw_detector_pixels_zero_based' or
            recipe.get('source_mode')!='manual' or len(recipe.get('objects',[]))!=1 or
            recipe['sky'].get('mode')!='pypeit_local' or recipe.get('spatial_padding_pixels',0)):
        raise ValueError('native reselection requires one source in unchanged raw detector coordinates')
    obj=deepcopy(recipe['objects'][0]); ny,nx=shape; ylo,xlo=origin
    if not (ylo<=obj['spec']<ylo+ny and xlo<=obj['spat']<xlo+nx):
        raise ValueError('reviewed source anchor is outside native calibrated support')
    obj.update(id='primary',label=frame['metadata']['OBJECT'],spec=obj['spec']-ylo,spat=obj['spat']-xlo)
    if not np.isfinite([obj[k] for k in ('spec','spat','radius','fwhm')]).all() or min(obj['radius'],obj['fwhm'])<=0:
        raise ValueError('reviewed source geometry is invalid')
    x=np.arange(nx)+xlo; band=np.zeros(nx,bool)
    for lo,hi in recipe['sky']['include']:band |= (x>=lo)&(x<hi)
    for lo,hi in recipe['sky'].get('exclude',[]):band &= ~((x>=lo)&(x<hi))
    mask=np.broadcast_to(band,shape).copy();trace=np.full(ny,obj['spat'])
    explicit_bands=bool(recipe['sky']['include'])
    proximity=None
    if recipe['sky'].get('placement')=='nearest_to_aperture':
        from .local_sky import closest_mask
        reference=recipe['sky']['trace_reference'];p=Path(reference['path'])
        if sha256(p)!=reference['sha256'] or reference['raw_sha256']!=frame['sha256']:
            raise ValueError('background trace reference changed or belongs to another exposure')
        with np.load(p) as saved:
            if tuple(saved['data'].shape)!=tuple(shape) or int(saved['raw_y_origin'])!=ylo or int(saved['spatial_origin'])+99!=xlo:
                raise ValueError('background trace reference geometry mismatch')
            trace=saved['trace'].copy()
        if abs(trace[int(round(obj['spec']))]-obj['spat'])>obj['radius']:
            raise ValueError('background reference is not the selected source')
        # Explicit neighbour traces are tied to the same immutable image file.
        neighbours=[]
        with np.load(p) as saved:
            for name in recipe['sky'].get('neighbour_names',[]):
                index=list(saved['found_names']).index(name)
                neighbours.append((saved['found_traces'][index],recipe['sky'].get('neighbour_fwhm_pixels',7.),obj['radius']))
        mask,bounds,proximity=closest_mask(shape,trace,radius=obj['radius'],
            fwhm=recipe['sky']['core_fwhm_pixels'],neighbours=neighbours,
            aperture_padding=recipe['sky'].get('aperture_padding_pixels',.5),
            width_pixels=recipe['sky'].get('width_pixels',30),
            minimum_width=recipe['sky'].get('minimum_width_pixels',15))
        Path(output).mkdir(parents=True,exist_ok=True)
        np.savez_compressed(Path(output)/'background-placement.npz',mask=mask,trace=trace,
                            raw_bounds=bounds+xlo)
        explicit_bands=True
    if explicit_bands:validate_bounded_mask(mask,trace,obj['radius'])
    evidence=dict(selection,method='raw_coordinate_reselection_on_native_calibration',
        raw_origin_yx=list(origin),native_shape_yx=list(shape),
        comparison='same hash-verified raw detector coordinates; background refitted on fresh native pixels',
        original_background_reused=False)
    if proximity is not None:evidence['proximity']=proximity
    if not explicit_bands:evidence['background_geometry']='fresh automatic bounded bands around the reviewed source'
    Path(output).mkdir(parents=True,exist_ok=True)
    (Path(output)/'source-reselection.json').write_text(json.dumps(evidence,indent=2)+'\n')
    if not explicit_bands:
        return dict(manual=[obj],bounded_background=True),evidence
    return dict(manual=[obj],sky_input_mask=mask,sky_trace=trace,
                sky_model={k:recipe['sky'][k] for k in ('degree','sigma_clip')}),evidence


def prepare_reviewed_extraction(selection, frame, data, wave, origin, output):
    """Recompute the fit from fresh pixels; reuse only verified recipe geometry.

    The original recipe remains bound to its parent manifest and calibrations.
    Exact comparison with the newly prepared image prevents silent transfer to
    a different crop, exposure, wavelength calibration or flexure correction.
    """
    from .revisions import FailedExposure
    from .local_sky import exposure_sky_inputs
    recipe_path = Path(selection['recipe_path'])
    if (sha256(recipe_path) != selection['recipe_sha256']
            or frame['sha256'] != selection['raw_sha256']
            or frame['metadata']['OBJECT'] != selection['object']):
        raise ValueError('reviewed-source inputs changed')
    exposure = FailedExposure(selection['parent_run'], selection['raw_name'])
    recipe = validate_recipe(json.loads(recipe_path.read_text()), exposure.window, exposure.hashes)
    if (recipe['source_mode'] != 'manual' or len(recipe['objects']) != 1
            or recipe['sky']['mode'] != 'pypeit_local' or recipe.get('spatial_padding_pixels', 0)):
        raise ValueError('reviewed source requires one bounded PypeIt recipe in the original window')
    if (exposure.hashes['raw'] != frame['sha256'] or tuple(origin) != exposure.window.origin
            or not np.array_equal(data, exposure.context.data, equal_nan=True)
            or not np.array_equal(wave, exposure.context.waveair, equal_nan=True)):
        raise ValueError('fresh pixels, window or wavelength calibration differ from reviewed inputs')
    obj = recipe['objects'][0]
    traces = np.asarray(exposure.images['found_traces'])
    row, x = exposure.window.to_local(obj['spec'], obj['spat'])
    anchors = np.array([np.interp(row, np.arange(len(t)), t) for t in traces])
    candidate = int(np.argmin(abs(anchors-x)))+1
    if candidate != selection['identity']['candidate'] or abs(anchors[candidate-1]-x) > obj['radius']:
        raise ValueError('recipe anchor does not match the visually identified candidate')
    obj['label'] = selection['object']
    mask, trace, background = exposure_sky_inputs(exposure, recipe)
    folder = Path(output)/'reviewed-sources';folder.mkdir(exist_ok=True)
    stem = Path(selection['raw_name']).stem
    executed = folder/(stem+'-recipe.json')
    executed.write_text(json.dumps(recipe, indent=2)+'\n')
    provenance = dict(selection, applied_recipe=str(executed), applied_recipe_sha256=sha256(executed),
                      comparison='fresh raw electrons, window and wavelength map match reviewed parent exactly')
    (folder/(stem+'.json')).write_text(json.dumps(provenance, indent=2)+'\n')
    manual = [dict(obj, spec=row, spat=x)]
    arguments = dict(manual=manual, sky_input_mask=mask, sky_trace=trace,
                     sky_model={key:recipe['sky'][key] for key in ('degree','sigma_clip')})
    identity = dict(association=('operator_selected' if selection['identity']['method']=='operator_visual'
                                 else 'UNVERIFIED_target_association'), identity=selection['identity'],
                    reviewed_source=provenance, requested=obj)
    return arguments, identity, background
