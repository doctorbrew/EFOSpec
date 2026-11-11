"""Shared display-only limits for spatial profiles; science arrays stay intact."""
import numpy as np


def _profile_limit_samples(values, protected, *, spatial_pixel=None, exclude_ranges=(),
                           edge_margin=0):
    """Mask isolated spike-like outliers and explicit regions for limits only.

    Positive spikes need >20 MAD-sigma prominence and a full width at half
    prominence <=2 spatial pixels; their >10-sigma core spans at most three
    columns. Broad source profiles and protected apertures/candidates survive.
    This is a display heuristic, not a scientific bad-pixel or source classifier.

    ``edge_margin`` keeps the outermost columns of a full-slit profile out of
    the limit estimate. Slit-boundary columns have no fitted background and run
    orders of magnitude above the sources, and the spike rule deliberately never
    masks a run touching the array end. Protected columns are still never
    dropped, and every sample stays plotted.
    """
    from scipy.ndimage import median_filter
    from scipy.signal import find_peaks
    displayed = np.array(values, dtype=float, copy=True)
    protected=np.asarray(protected,dtype=bool)
    if displayed.ndim!=1 or protected.shape!=displayed.shape:
        raise ValueError('profile and protected mask must be matching one-dimensional arrays')
    if type(edge_margin) is not int or edge_margin < 0 or 2*edge_margin >= displayed.size:
        raise ValueError('edge margin must be a non-negative integer inside the profile')
    finite = np.isfinite(displayed)
    explicit = np.zeros(displayed.shape, dtype=bool)
    if edge_margin:
        explicit[:edge_margin] = explicit[-edge_margin:] = True
        explicit &= ~protected
    if exclude_ranges:
        x = np.asarray(spatial_pixel, dtype=float)
        if x.shape != displayed.shape:
            raise ValueError('display exclusions require matching spatial coordinates')
        for lo, hi in exclude_ranges:
            if not np.isfinite([lo,hi]).all() or lo >= hi:
                raise ValueError('display exclusion must be a finite increasing interval')
            explicit |= (x >= lo) & (x < hi)
        if np.any(explicit & protected):
            raise ValueError('display exclusion overlaps a protected source or aperture')
    if finite.sum() < 7:
        displayed[explicit] = np.nan
        return displayed, explicit & finite
    filled = np.where(finite, displayed, np.nanmedian(displayed))
    deviation = filled-median_filter(filled, size=7, mode='nearest')
    center = np.median(deviation[finite])
    sigma = 1.4826*np.median(np.abs(deviation[finite]-center))
    threshold = max(10*sigma, np.finfo(float).eps*max(1., np.max(np.abs(filled))))
    candidates = finite & (deviation < -threshold)
    masked = np.zeros_like(candidates)
    # Broad depressions remain visible; only isolated one/two-column spikes
    # qualify for exclusion from the limit calculation.
    groups = np.split(np.flatnonzero(candidates), np.flatnonzero(np.diff(np.flatnonzero(candidates)) > 1)+1)
    for group in groups:
        if (0 < len(group) <= 2 and group[0] > 0 and group[-1] < len(values)-1
                and not protected[group].any()):
            masked[group] = True
    # A narrow core in a broad, high-S/N source is not an isolated spike.
    # Measure the width on the full profile, not its median-filter residual.
    peaks,_=find_peaks(filled,prominence=2*threshold,width=(None,2.))
    positive=finite & (deviation>threshold)
    groups=np.split(np.flatnonzero(positive),np.flatnonzero(np.diff(np.flatnonzero(positive))>1)+1)
    for group in groups:
        if not 0<len(group)<=3 or group[0]==0 or group[-1]==len(values)-1:
            continue
        qualified=np.intersect1d(group,peaks)
        if (len(qualified) and np.any(deviation[qualified]>2*threshold)
                and finite[group[0]-1] and finite[group[-1]+1]
                and not protected[group].any()):
            masked[group]=True
    masked |= explicit & finite
    displayed[masked] = np.nan
    return displayed, masked


def _profile_limits(profiles, *, background_subtracted=False):
    finite = np.concatenate(profiles)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return None
    low, high = float(finite.min()), float(finite.max())
    # Outward 10% padding works for positive, negative, and mixed-sign data.
    fallback = .1*max(high-low, abs(low), abs(high), 1.)
    if background_subtracted:
        # Give the zero baseline and negative residuals clear space below the
        # source peak, without allowing isolated dips to set the viewport.
        lower_padding = max(.1*abs(low), .2*(high-low), fallback)
        return min(0., low)-lower_padding, max(0., high)+(.1*abs(high) or fallback)
    return low-(.1*abs(low) or fallback), high+(.1*abs(high) or fallback)
