"""Bounded, two-sided background fitting with the pinned PypeIt B-spline solver.

The polynomial is spatial; the B-spline coordinate follows the wavelength map.
All widths here are *spatial detector pixels*, never Angstroms. No full-slit or
constant-background fallback is allowed. The selected and rejected pixels are
returned separately, including rows that lose support on either side.
"""
import numpy as np


class BackgroundSupportError(ValueError):
    code = 'background_support_required'
    action = 'Review both local background bands and neighbouring traces; no full-slit fallback was used.'

    def __init__(self, message, **diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def side_counts(mask, trace, radius):
    x = np.arange(mask.shape[1])[None, :]
    return np.array([(mask & (x < trace[:, None]-radius)).sum(axis=1),
                     (mask & (x > trace[:, None]+radius)).sum(axis=1)])


def validate_bounded_mask(mask, trace, radius, *, maximum_width=50):
    """Validate two finite local bands, including holes for bad pixels."""
    x = np.arange(mask.shape[1])
    for row, center in enumerate(trace):
        if np.any(mask[row] & (abs(x-center) <= radius)):
            raise BackgroundSupportError('Background selection includes the source aperture.', row=row)
        for side in (x < center-radius, x > center+radius):
            selected = np.flatnonzero(mask[row] & side)
            if len(selected) < 5:
                raise BackgroundSupportError('Background needs at least five samples on each side.', row=row)
            if selected[-1]-selected[0]+1 > maximum_width:
                raise BackgroundSupportError(f'Each local background band must span at most {maximum_width} spatial pixels.', row=row)
            if np.min(abs(selected-center))-radius > 2*maximum_width:
                raise BackgroundSupportError('Background band is too far from the source aperture.', row=row)


def nearby_mask(shape, trace, *, radius, fwhm, width_pixels, neighbours=(),
                max_gap_pixels=None, allowed_mask=None):
    """Find the nearest clean contiguous band of the requested width per side.

    Bands follow the trace, avoiding 1.5 FWHM (at least the boxcar aperture)
    around each source. A neighbouring source can displace a band, but never
    expands it. No narrower, one-sided or detector-edge fallback is made.
    Neighbours are (trace array, FWHM, boxcar radius) tuples in local pixels.
    """
    trace = np.asarray(trace, float)
    if (len(shape) != 2 or trace.shape != (shape[0],) or not np.isfinite(trace).all()
            or type(width_pixels) is not int or not 5 <= width_pixels <= 50
            or not np.isfinite([radius, fwhm]).all() or radius <= 0 or fwhm <= 0):
        raise ValueError('local background requires a finite trace and an explicit width of 5–50 spatial pixels')
    max_gap = 2*width_pixels if max_gap_pixels is None else float(max_gap_pixels)
    if not np.isfinite(max_gap) or max_gap < 0:
        raise ValueError('maximum background gap must be finite and nonnegative')
    x = np.arange(shape[1])[None, :]
    guard = max(radius+.5, 1.5*fwhm)
    clean = np.broadcast_to((x >= 3) & (x < shape[1]-3), shape).copy()
    if allowed_mask is not None:
        if np.shape(allowed_mask) != shape:
            raise ValueError('allowed background mask has the wrong shape')
        clean &= np.asarray(allowed_mask, bool)
    clean &= abs(x-trace[:, None]) > guard
    for other, other_fwhm, other_radius in neighbours:
        other = np.asarray(other, float)
        if (other.shape != trace.shape or not np.isfinite(other).all()
                or not np.isfinite([other_fwhm, other_radius]).all()
                or other_fwhm <= 0 or other_radius <= 0):
            raise ValueError('invalid neighbouring trace geometry')
        clean &= abs(x-other[:, None]) > max(other_radius+.5, 1.5*other_fwhm)
    mask = np.zeros(shape, bool)
    bounds = np.full((shape[0], 2, 2), -1, int)
    for row, center in enumerate(trace):
        for side in (0, 1):
            allowed = clean[row] & (x[0] < center-guard if side == 0 else x[0] > center+guard)
            starts = np.flatnonzero(np.convolve(allowed.astype(int), np.ones(width_pixels, int), 'valid') == width_pixels)
            if not len(starts):
                continue
            start = int(starts[-1] if side == 0 else starts[0])
            gap = center-guard-(start+width_pixels) if side == 0 else start-center-guard
            if gap > max_gap:
                continue
            mask[row, start:start+width_pixels] = True
            bounds[row, side] = start, start+width_pixels
    invalid = np.flatnonzero(np.any(bounds[:, :, 0] < 0, axis=1))
    if len(invalid):
        raise BackgroundSupportError(
            f'Cannot place {width_pixels}-pixel local bands on both sides in {len(invalid)}/{shape[0]} rows; '
            'review neighbours or prepare a wider calibrated window.',
            width_spatial_pixels=width_pixels, unsupported_rows=invalid.tolist(),
            window_shape=list(shape), max_gap_pixels=max_gap)
    return mask, bounds


def exposure_sky_inputs(exposure, recipe):
    """Translate a hash-bound recipe into a trace-following local selection.

    Saved candidate traces guide the geometry, never the astrophysical identity.
    Legacy records do not store every neighbour's FWHM: use the requested source
    guard for them and record that limitation instead of inferring a host class.
    """
    from .recipes import sky_mask
    obj, sky = recipe['objects'][0], recipe['sky']
    y0, x0 = exposure.window.origin
    traces = np.asarray(exposure.images.get('found_traces', []), float)
    if not len(traces) and 'trace' in exposure.images:
        traces = np.asarray([exposure.images['trace']], float)
    if traces.ndim != 2 or traces.shape[1] != exposure.window.shape[0] or not len(traces):
        raise BackgroundSupportError('Saved exposure has no trace geometry for local background selection.')
    row = obj['spec']-y0
    anchors = np.array([np.interp(row, np.arange(len(t)), t) for t in traces])
    index = int(np.argmin(abs(anchors-(obj['spat']-x0))))
    if abs(anchors[index]-(obj['spat']-x0)) > obj['radius']:
        raise BackgroundSupportError('Requested source is too far from every saved trace; retrace before selecting background.')
    trace = traces[index]+obj['spat']-x0-anchors[index]
    neighbours = [(t,obj['fwhm'],obj['radius']) for i,t in enumerate(traces) if i != index]
    allowed = np.ones(exposure.window.shape, bool)
    x = np.arange(exposure.window.shape[1])+x0
    for low, high in sky['exclude']:
        allowed[:, (x >= low) & (x < high)] = False
    if not sky['include']:
        for actual_width in range(sky['width_pixels'],sky.get('minimum_width_pixels',sky['width_pixels'])-1,-1):
            try:
                mask, bounds = nearby_mask(exposure.window.shape, trace, radius=obj['radius'],
                    fwhm=obj['fwhm'], width_pixels=actual_width, neighbours=neighbours,
                    allowed_mask=allowed, max_gap_pixels=2*sky['width_pixels'])
                break
            except BackgroundSupportError:
                if actual_width==sky.get('minimum_width_pixels',sky['width_pixels']):raise
    else:
        mask = sky_mask(recipe, exposure.window) & allowed
        local_x = np.arange(exposure.window.shape[1])[None, :]
        for other, fwhm, radius in [(trace,obj['fwhm'],obj['radius'])]+neighbours:
            mask &= abs(local_x-other[:, None]) > max(radius+.5,1.5*fwhm)
        validate_bounded_mask(mask,trace,obj['radius'])
        bounds = None
    info = dict(coordinates='zero_based_extraction_window', raw_spatial_origin=x0,
                requested_raw_bands=sky['include'],
                selection='nearest_clean_two_sided_bands' if bounds is not None else 'explicit_two_sided_bands',
                width_spatial_pixels=sky.get('width_pixels'),
                actual_width_spatial_pixels=actual_width if bounds is not None else None,
                neighbour_guard='requested source FWHM/radius applied to saved candidates; inspect QC',
                source_guard_pixels=max(obj['radius']+.5,1.5*obj['fwhm']),
                saved_candidate_index=index+1)
    return mask, trace, info


def fit_background(data, ivar, tilts, mask, trace, *, radius, degree=1,
                   sigma_clip=4., bsp=1., maxiter=100):
    """Use PypeIt's B-spline × Legendre fit, retaining its convergence evidence.

    ``degree=2`` supplies three Legendre terms. Unlike global_skysub in 1.14,
    failure never retries a spatial constant. We deliberately omit its positive
    log-sky prefit: that spatially constant prefit can clip a real gradient.
    Returned valid rows have >=5 accepted pixels *on each side*. Callers must
    mask invalid rows before extraction. Model covariance is not propagated by
    PypeIt's fixed-sky optimal extraction and must not be claimed as included.
    """
    import pypeit
    from pypeit.core import basis, fitting
    if pypeit.__version__ != '1.14.0':
        raise ValueError('local background adapter requires PypeIt 1.14.0')
    data, ivar, tilts = (np.asarray(v, float) for v in (data, ivar, tilts))
    mask, trace = np.asarray(mask, bool), np.asarray(trace, float)
    if (data.ndim != 2 or data.shape != ivar.shape or data.shape != tilts.shape
            or mask.shape != data.shape or trace.shape != (len(data),)
            or not np.isfinite(tilts).all() or not np.isfinite(trace).all()):
        raise ValueError('background arrays and trace geometry disagree')
    if type(degree) is not int or not 1 <= degree <= 3:
        raise ValueError('PypeIt local spatial degree must be 1, 2 or 3')
    if not np.isfinite([radius, sigma_clip, bsp]).all() or radius <= 0 or sigma_clip < 3 or bsp <= 0:
        raise ValueError('invalid background aperture, clipping or B-spline spacing')
    if type(maxiter) is not int or maxiter < 1:
        raise ValueError('background iteration limit must be a positive integer')
    good = mask & np.isfinite(data) & np.isfinite(ivar) & (ivar > 0)
    validate_bounded_mask(mask, trace, radius)
    counts = side_counts(good, trace, radius)
    if np.any(counts < 5):
        raise BackgroundSupportError('Background needs at least five usable pixels on each side before fitting.',
                                     unsupported_rows=np.flatnonzero(np.any(counts < 5, axis=0)).tolist())
    pixels = (tilts*(len(data)-1)).ravel()
    order = np.argsort(pixels)
    spatial = np.broadcast_to(np.linspace(-1., 1., data.shape[1]), data.shape).ravel()
    # Fit all coordinates with zero weight outside the bounded sampling mask.
    # This also returns the interpolated model under the source aperture.
    _, accepted, model, chi2, status = fitting.bspline_profile(
        pixels[order], np.where(np.isfinite(data), data, 0).ravel()[order],
        np.where(good, ivar, 0).ravel()[order],
        basis.flegendre(spatial[order], degree+1), ingpm=good.ravel()[order],
        nord=4, upper=sigma_clip, lower=sigma_clip, maxiter=maxiter,
        kwargs_bspline={'bkspace':bsp}, kwargs_reject={'groupbadpix':False, 'maxrej':10})
    if status != 0 or not np.isfinite(model).all():
        raise BackgroundSupportError(f'PypeIt spatial degree {degree} did not converge (exit status {status}); no lower-order fallback.',
                                     spatial_degree=degree, pypeit_exit_status=int(status))
    sky, used = np.empty_like(pixels), np.empty_like(pixels, dtype=bool)
    sky[order], used[order] = model, accepted
    sky, used = sky.reshape(data.shape), used.reshape(data.shape) & good
    final_counts = side_counts(used, trace, radius)
    valid = np.all(final_counts >= 5, axis=0)
    if valid.mean() < .9:
        raise BackgroundSupportError('More than 10% of rows lost two-sided background support after rejection.',
                                     unsupported_rows=np.flatnonzero(~valid).tolist(), spatial_degree=degree)
    summary = dict(engine='pypeit.core.fitting.bspline_profile', pypeit_version=pypeit.__version__,
                   spatial_degree=degree, legendre_terms=degree+1, pypeit_exit_status=int(status),
                   sigma_clip=float(sigma_clip), bspline_spacing=float(bsp),
                   maximum_iterations=maxiter,
                   reduced_chi2=float(chi2), invalid_rows=np.flatnonzero(~valid).tolist(),
                   accepted_fraction=float(used.sum()/good.sum()),
                   minimum_side_samples=int(final_counts[:, valid].min()),
                   no_local_sky=True, constant_fallback=False, positive_log_prefit=False,
                   uncertainty_scope='PypeIt fixed-sky extraction; background-model covariance not propagated')
    return dict(sky=sky, input_mask=good, accepted_mask=used, valid_rows=valid,
                side_counts=final_counts, summary=summary)
