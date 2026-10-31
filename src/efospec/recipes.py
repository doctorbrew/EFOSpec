"""Validated extraction recipes; positions and widths are native image pixels."""
from copy import deepcopy
from dataclasses import dataclass
import math
import re

import numpy as np


@dataclass(frozen=True)
class DetectorWindow:
    """Shape and origin in [spectral, spatial] order, after detector binning."""
    shape: tuple
    origin: tuple

    def __post_init__(self):
        if (len(self.shape) != 2 or len(self.origin) != 2
                or any(type(v) is not int or v < 2 for v in self.shape)
                or any(type(v) is not int or v < 0 for v in self.origin)):
            raise ValueError('invalid detector window')

    def to_local(self, spec, spat):
        return float(spec)-self.origin[0], float(spat)-self.origin[1]

    def to_raw(self, spec, spat):
        return float(spec)+self.origin[0], float(spat)+self.origin[1]


def _fields(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError(f'{label} has missing or unsupported fields')


def _number(value, low, high, label):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not low <= value <= high):
        raise ValueError(f'{label} must be a finite number in [{low}, {high}]')
    return float(value)


def sky_mask(recipe, window):
    """Select actual global-sky input pixels; source apertures remain excluded.

    Spatial bands span the saved spectral window. Bounds are half-open, in
    native detector pixels. None delegates mask construction to PypeIt.
    """
    if recipe['sky']['mode'] == 'automatic':
        return None
    spatial = np.arange(window.shape[1])+window.origin[1]
    selected = np.zeros(window.shape[1], dtype=bool)
    for low, high in recipe['sky']['include']:
        selected |= (spatial >= low) & (spatial < high)
    for low, high in recipe['sky']['exclude']:
        selected &= ~((spatial >= low) & (spatial < high))
    for obj in recipe['objects']:
        # Protect both the geometric aperture and extended profile wings.
        selected &= abs(spatial-obj['spat']) > max(obj['radius'], 3*obj['fwhm'])
    selected[[0, -1]] = False
    return np.broadcast_to(selected, window.shape).copy()


def validate_recipe(value, window, expected_inputs):
    """Validate and copy a recipe without silently ignoring edited controls."""
    _fields(value, ('schema_version', 'engine_version', 'coordinates', 'input_sha256',
                    'source_mode', 'objects', 'sky'), 'recipe')
    recipe = deepcopy(value)
    if type(recipe['schema_version']) is not int or recipe['schema_version'] != 1:
        raise ValueError('unsupported recipe schema version')
    if recipe['engine_version'] != '1.14.0':
        raise ValueError('recipe requires PypeIt 1.14.0')
    if recipe['coordinates'] != 'raw_detector_pixels_zero_based':
        raise ValueError('recipe coordinates must be zero-based native detector pixels')
    hashes = recipe['input_sha256']
    if (not isinstance(hashes, dict) or not {'raw', 'images', 'manifest'} <= set(hashes)
            or any(not isinstance(v, str) or not re.fullmatch(r'[0-9a-f]{64}', v)
                   for v in hashes.values()) or hashes != expected_inputs):
        raise ValueError('recipe input hashes do not match this exposure')
    mode, objects = recipe['source_mode'], recipe['objects']
    if mode not in ('automatic', 'manual') or not isinstance(objects, list):
        raise ValueError('invalid source selection mode or objects')
    if mode == 'automatic' and objects:
        raise ValueError('automatic selection cannot silently ignore manual objects')
    if mode == 'manual' and not 1 <= len(objects) <= 2:
        raise ValueError('manual selection requires one or two objects')
    ids = set()
    for obj in objects:
        _fields(obj, ('id', 'label', 'kind', 'spec', 'spat', 'fwhm', 'radius'), 'object')
        identity = obj['id']
        if (not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', identity)
                or identity in ids):
            raise ValueError('object IDs must be unique simple identifiers')
        ids.add(identity)
        if (not isinstance(obj['label'], str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._+-]{0,59}', obj['label'])):
            raise ValueError('object labels must be plain names, up to 60 characters')
        if obj['kind'] not in ('point', 'galaxy'):
            raise ValueError('object kind must be point or galaxy')
        obj['spec'] = _number(obj['spec'], window.origin[0],
                              window.origin[0]+window.shape[0]-1, 'spectral anchor')
        obj['spat'] = _number(obj['spat'], window.origin[1]+1,
                              window.origin[1]+window.shape[1]-2, 'spatial anchor')
        obj['fwhm'] = _number(obj['fwhm'], 1., 30., 'FWHM in pixels')
        obj['radius'] = _number(obj['radius'], .5, 30., 'boxcar half-width in pixels')
        _, local = window.to_local(obj['spec'], obj['spat'])
        if local-obj['radius'] < 1 or local+obj['radius'] > window.shape[1]-2:
            raise ValueError('object aperture extends outside the saved detector window')
    if objects and objects[0]['id'] != 'primary':
        raise ValueError('the first object must have the stable ID primary')
    if len(objects) == 2 and abs(objects[0]['spat']-objects[1]['spat']) < 5*max(o['fwhm'] for o in objects):
        raise ValueError('two-source mode requires separated traces: at least five FWHM')
    sky = recipe['sky']
    _fields(sky, ('mode', 'include', 'exclude'), 'sky selection')
    if sky['mode'] not in ('automatic', 'regions'):
        raise ValueError('invalid sky selection mode')
    for key in ('include', 'exclude'):
        if not isinstance(sky[key], list) or len(sky[key]) > 32:
            raise ValueError('sky selections must contain at most 32 spatial bands')
        for index, pair in enumerate(sky[key]):
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError('each sky band requires lower and upper bounds')
            low, high = [_number(v, window.origin[1], window.origin[1]+window.shape[1],
                                 'sky band') for v in pair]
            if low >= high:
                raise ValueError('sky band bounds must increase')
            sky[key][index] = [low, high]
    if sky['mode'] == 'automatic' and (sky['include'] or sky['exclude']):
        raise ValueError('automatic sky selection cannot ignore edited background bands')
    if sky['mode'] == 'regions' and mode != 'manual':
        raise ValueError('selected background requires manual source anchors')
    minimum = max(8, math.ceil(.21*window.shape[1]))
    if sky['mode'] == 'regions' and np.min(sky_mask(recipe, window).sum(axis=1)) < minimum:
        raise ValueError(f'background selection needs at least {minimum} sky pixels per row (PypeIt sky-fit gate)')
    return recipe
