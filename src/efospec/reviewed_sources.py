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
        if (identity.get('method') != 'operator_visual' or not identity.get('evidence')
                or type(identity.get('candidate')) is not int or identity['candidate'] < 1):
            raise ValueError('reviewed source needs explicit visual identification evidence')
        recipe_path = Path(item['recipe_path'])
        if not recipe_path.is_absolute() or not Path(item['parent_run']).is_absolute():
            raise ValueError('reviewed-source references must be absolute')
        if sha256(recipe_path) != item['recipe_sha256']:
            raise ValueError('reviewed-source recipe changed')
        selected[raw] = deepcopy(item)
    return selected


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
    identity = dict(association='operator_selected', identity=selection['identity'],
                    reviewed_source=provenance, requested=obj)
    return arguments, identity, background
