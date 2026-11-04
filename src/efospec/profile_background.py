"""Explicit reuse of a saved, two-sided PypeIt background for QC profiles."""
import json
from pathlib import Path

import numpy as np

from .inventory import sha256


def load_profile_background(exposure, directory):
    """Require an explicit hash-bound model; never select a trial implicitly."""
    path = Path(directory)/'profile-background.json'
    if not path.exists():
        if exposure.result.get('processing',{}).get('sky_policy') == 'bounded_two_sided_pypeit':
            return _bounded_arrays(exposure)
        return None
    record = json.loads(path.read_text())
    for name in ('manifest', 'images', 'recipe'):
        if sha256(Path(record[name])) != record[name+'_sha256']:
            raise ValueError(f'Profile background {name} changed')
    from .revisions import Exposure
    source = Exposure(Path(record['manifest']).parent, record['product'])
    if (source.images_path.resolve() != Path(record['images']).resolve()
            or source.hashes['raw'] != exposure.hashes['raw']
            or source.window != exposure.window
            or not np.array_equal(source.images['data'], exposure.images['data'], equal_nan=True)
            or not np.array_equal(source.images['waveair'], exposure.images['waveair'], equal_nan=True)):
        raise ValueError('Profile background does not match this exposure and detector window')
    if source.manifest.get('recipe_sha256') != record['recipe_sha256']:
        raise ValueError('Profile background recipe does not match its reduction')
    background = _bounded_arrays(source)
    background.update(provenance=record, selection_file=str(path), selection_sha256=sha256(path))
    return background


def _bounded_arrays(source):
    processing = source.result.get('processing', {})
    fit = processing.get('background_fit', {})
    if (processing.get('sky_policy') != 'bounded_two_sided_pypeit'
            or fit.get('pypeit_exit_status') != 0 or fit.get('minimum_side_samples', 0) < 5):
        raise ValueError('Profile background lacks a successful two-sided PypeIt fit')
    arrays = source.images
    valid = np.asarray(arrays['sky_valid_rows'], bool)
    accepted = np.asarray(arrays['sky_accepted_mask'], bool)
    if not valid.any() or np.any(accepted[valid].sum(axis=1) < 10):
        raise ValueError('Profile background has insufficient accepted samples')
    # Interpolate only between the two background bands, never extrapolate
    # beyond the region bracketed in every supported spectral row.
    lower = int(np.argmax(accepted[valid], axis=1).max())
    upper = int((accepted.shape[1]-1-np.argmax(accepted[valid, ::-1], axis=1)).min())
    if lower >= upper:
        raise ValueError('Profile background has no common interpolation interval')
    residual = arrays['data']-arrays['sky']
    good = (arrays['mask'] == 0) & np.isfinite(residual)
    return {'residual':np.where(good, residual, np.nan), 'valid_rows':valid,
            'x_limits':(source.window.origin[1]+lower, source.window.origin[1]+upper),
            'provenance':None}


def summed_profile(residual, indices, valid_rows):
    """Sum the same supported y rows at every x; no median or recentering."""
    selected = indices[np.asarray(valid_rows, bool)[indices]]
    if not len(selected):
        return np.full(residual.shape[1], np.nan), 0
    # np.sum deliberately leaves a missing pixel missing, rather than silently
    # treating it as zero or mixing different row counts across the profile.
    return np.sum(residual[selected], axis=0), len(selected)
