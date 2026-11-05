"""Replay reviewed standard-background bands against exactly matching pixels."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .inventory import sha256
from .recipes import DetectorWindow, validate_recipe
from .local_sky import exposure_sky_inputs


def load_background_reviews(path, frames):
    if path is None: return {}
    document = json.loads(Path(path).read_text())
    if document.get('schema_version') != 1 or not isinstance(document.get('reviews'), list):
        raise ValueError('invalid filtered background reviews')
    available = {Path(f['path']).name: f for f in frames}
    reviews = {}
    for item in document['reviews']:
        raw = item['raw_name']
        if raw in reviews or raw not in available or item['raw_sha256'] != available[raw]['sha256']:
            raise ValueError('background review does not match a unique unchanged standard')
        if not item.get('evidence') or not item.get('reviewer'):
            raise ValueError('background review needs recorded evidence and reviewer')
        reviews[raw] = item
    return reviews


def review_arguments(review, frame, data, waveair, origin, calibration):
    paths = {key: Path(review[key]) for key in ('manifest', 'images', 'recipe')}
    for key, path in paths.items():
        if not path.is_absolute() or sha256(path) != review[key+'_sha256']:
            raise ValueError('filtered background review input changed: '+key)
    if frame['sha256'] != review['raw_sha256'] or sha256(calibration/'calibration.json') != review['calibration_sha256']:
        raise ValueError('filtered background review raw/calibration identity changed')
    if list(origin) != review['raw_origin_yx']:
        raise ValueError('filtered background review crop changed')
    with np.load(paths['images']) as saved:
        images = {key: saved[key] for key in saved.files}
    if not np.array_equal(data, images['data'], equal_nan=True) or not np.array_equal(waveair, images['waveair'], equal_nan=True):
        raise ValueError('fresh filtered pixels or wavelengths differ from the background review')
    hashes = {'raw': frame['sha256'], 'images': review['images_sha256'], 'manifest': review['manifest_sha256']}
    window = DetectorWindow(tuple(data.shape), tuple(origin))
    recipe = validate_recipe(json.loads(paths['recipe'].read_text()), window, hashes)
    if recipe['source_mode'] != 'manual' or len(recipe['objects']) != 1 or recipe['sky']['mode'] != 'pypeit_local':
        raise ValueError('filtered background review requires one bounded PypeIt source')
    exposure = SimpleNamespace(window=window, images=images)
    mask, trace, evidence = exposure_sky_inputs(exposure, recipe)
    obj = recipe['objects'][0]
    row, x = window.to_local(obj['spec'], obj['spat'])
    return {'manual': [dict(obj, spec=row, spat=x)], 'sky_input_mask': mask, 'sky_trace': trace,
            'sky_model': {key: recipe['sky'][key] for key in ('degree', 'sigma_clip')}}, evidence
