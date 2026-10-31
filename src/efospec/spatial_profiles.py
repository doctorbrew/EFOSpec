"""Native-pixel spatial sums for diagnostic plots; no extraction or resampling."""
import numpy as np


def wavelength_binned_profiles(data, wavelength_edges, box_radius):
    """Sum sky-subtracted electrons in disjoint air-wavelength intervals.

    Use each detector pixel's wavelength, including spectral tilt. All finite
    on-slit pixels contribute, without clipping, normalization, or rejection. Shading
    fractions describe how often a spatial pixel falls in the saved global-sky
    input selection or the geometric boxcar aperture across that interval.
    The latter includes fractional pixel overlap and is not an optimal weight.
    """
    residual = np.asarray(data['data']) - np.asarray(data['sky'])
    wave = np.asarray(data['waveair'])
    sky = np.asarray(data['sky_input_mask'], dtype=bool)
    onslit = np.asarray(data.get('onslit', np.ones(residual.shape, dtype=bool)), dtype=bool)
    trace = np.asarray(data['trace'])
    edges = np.asarray(wavelength_edges, dtype=float)
    if (residual.ndim != 2 or wave.shape != residual.shape or sky.shape != residual.shape
            or onslit.shape != residual.shape):
        raise ValueError('profile images must share a two-dimensional geometry')
    if trace.shape != (residual.shape[0],) or not np.isfinite(trace).all():
        raise ValueError('a finite trace is required for every spectral row')
    if edges.ndim != 1 or len(edges) < 2 or not np.isfinite(edges).all() or np.any(np.diff(edges) <= 0):
        raise ValueError('wavelength edges must be finite and strictly increasing')
    if not np.isfinite(box_radius) or box_radius <= 0:
        raise ValueError('boxcar aperture radius must be positive')
    x = np.arange(residual.shape[1])
    origin = int(data['spatial_origin'])
    aperture = np.clip(
        np.minimum(x[None, :]+0.5, trace[:, None]+box_radius)
        - np.maximum(x[None, :]-0.5, trace[:, None]-box_radius), 0., 1.)
    trace_wave = np.array([np.interp(t, x, w) for t, w in zip(trace, wave)])
    finite = np.isfinite(residual) & np.isfinite(wave) & onslit
    profiles = []
    for index, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        last = index == len(edges)-2
        selected = finite & (wave >= lo) & ((wave <= hi) if last else (wave < hi))
        count = selected.sum(axis=0)
        flux = np.where(selected, residual, 0.).sum(axis=0)
        flux[count == 0] = np.nan  # Missing coverage is not a zero measurement.
        background_fraction = np.divide((selected & sky).sum(axis=0), count,
                                         out=np.zeros(len(x)), where=count > 0)
        aperture_fraction = np.divide((selected*aperture).sum(axis=0), count,
                                      out=np.zeros(len(x)), where=count > 0)
        trace_rows = (trace_wave >= lo) & ((trace_wave <= hi) if last else (trace_wave < hi))
        if not trace_rows.any() or not count.any():
            raise ValueError(f'no trace coverage in wavelength bin {lo:g}--{hi:g}')
        trace_positions = trace[trace_rows]+origin
        profiles.append({
            'wavelength_air_angstrom': [float(lo), float(hi)],
            'spatial_pixel': x+origin, 'summed_electrons': flux,
            'native_pixel_count': count, 'background_fraction': background_fraction,
            'aperture_fraction': aperture_fraction,
            'median_trace_pixel': float(np.median(trace_positions)),
            'trace_pixel_range': [float(trace_positions.min()), float(trace_positions.max())],
        })
    return profiles
