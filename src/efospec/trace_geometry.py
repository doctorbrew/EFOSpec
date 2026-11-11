"""Independent local contrast checks and measured point-source apertures.

All distances are binned spatial detector pixels. A collapsed-profile peak
alone does not establish a trace or an astrophysical identification.
"""
import numpy as np

TRACE_DEGREE = 3
TRACE_STYLES = ('-', '--', '-.', ':')
TRACE_LINEWIDTH = 4.4


def trace_evidence(data, ivar, trace, fwhm, *, support=None, bins=6):
    """Test a Gaussian core against a local linear background in spectral bins.

    Use propagated noise and inflate by excess spatial residual scatter. Require
    positive local contrast in at least half the bins; emission-line-only objects
    are deliberately sent to review, not declared absent. No trace is reshaped.
    """
    data, ivar, trace = map(lambda a: np.asarray(a, float), (data, ivar, trace))
    if data.ndim != 2 or data.shape != ivar.shape or trace.shape != (len(data),):
        raise ValueError('trace evidence geometry mismatch')
    if not np.isfinite(fwhm) or fwhm <= 0 or not np.isfinite(trace).all():
        raise ValueError('finite trace and positive FWHM required')
    good = np.isfinite(data) & np.isfinite(ivar) & (ivar > 0)
    if support is not None:
        good &= np.asarray(support, bool)
    distance = np.arange(data.shape[1])[None, :]-trace[:, None]
    records = []
    for rows in np.array_split(np.arange(len(data)), bins):
        use = good[rows] & (abs(distance[rows]) <= max(8., 2.5*fwhm))
        d = distance[rows][use]; values = data[rows][use]; weight = ivar[rows][use]
        # Both flanks must be measured; a peak on a sky-support edge is not enough.
        supported = all(np.count_nonzero(d*side > 1.5*fwhm) >= len(rows)*2 for side in (-1, 1))
        if not supported or len(d) < 10:
            records.append(dict(snr=None, supported=False)); continue
        core = np.exp(-.5*(d/(fwhm/2.354820045))**2)
        # Remove each row's median to avoid wavelength-dependent sky variance
        # dominating the local spatial test; the fitted intercept absorbs offsets.
        row_median = np.zeros(len(rows))
        valid_rows = use.any(axis=1)
        row_median[valid_rows] = np.nanmedian(np.where(use[valid_rows], data[rows][valid_rows], np.nan), axis=1)
        values = (data[rows]-row_median[:, None])[use]
        design = np.column_stack([core, np.ones(len(d)), d])
        a = design*np.sqrt(weight[:, None]); b = values*np.sqrt(weight)
        coeff, _, rank, _ = np.linalg.lstsq(a, b, rcond=None)
        if rank != 3:
            records.append(dict(snr=None, supported=False)); continue
        residual = (values-design@coeff)*np.sqrt(weight)
        inflation = max(1., 1.4826*np.median(abs(residual-np.median(residual))))
        error = np.sqrt(np.linalg.inv(a.T@a)[0, 0])*inflation
        records.append(dict(snr=float(coeff[0]/error), supported=True))
    passing = sum(r['snr'] is not None and r['snr'] >= 3 for r in records)
    return dict(accepted=passing >= (bins+1)//2, positive_bins=passing, bins=records,
                minimum_bin_snr=3., required_positive_bins=(bins+1)//2,
                method='local Gaussian contrast over linear background in independent spectral bins',
                identity_confirmed=False)


def measured_aperture(data, ivar, trace, fwhm, *, neighbours=()):
    """Grow a trace-aligned aperture until both wings reach the profile noise.

    At least 99.7% of a Gaussian core (3 sigma), then three consecutive
    noise-consistent wing pixels on each side. A neighbour/detector boundary
    before that point is an explicit failure, never a claim of total flux.
    """
    ny, nx = data.shape
    data = np.where(np.isfinite(ivar) & (ivar > 0), data, np.nan)
    reach = min(50, int(np.floor(np.min(trace))), int(np.floor(nx-1-np.max(trace))))
    if reach < 5:
        raise ValueError('no uncontaminated room to measure both aperture wings')
    offsets = np.arange(-reach, reach+1)
    x = np.arange(nx)
    aligned = np.array([np.interp(t+offsets, x, row, left=np.nan, right=np.nan)
                        for t, row in zip(trace, data)])
    noise_rows = np.where(ivar > 0, 1/np.sqrt(np.maximum(ivar, 1e-30)), np.nan)
    noise_aligned = np.array([np.interp(t+offsets, x, row, left=np.nan, right=np.nan)
                              for t, row in zip(trace, noise_rows)])
    profile = np.nanmedian(aligned, axis=0)
    noise = 1.2533*np.nanmedian(noise_aligned, axis=0)/np.sqrt(np.maximum(np.sum(np.isfinite(aligned), axis=0), 1))
    minimum = max(2, int(np.ceil(3*fwhm/2.354820045)))
    cap = min(float(np.min(trace)-3), float(nx-4-np.max(trace)), float(offsets[-1]-2))
    for other, fw, radius in neighbours:
        cap = min(cap, float(np.min(abs(np.asarray(other)-trace)))-max(1.5*fw, radius+.5)-1)
    flank = (abs(offsets) >= max(minimum+3, int(.7*cap))) & (abs(offsets) <= cap)
    if flank.sum() < 6 or cap < minimum+3:
        raise ValueError('no uncontaminated room to measure both aperture wings')
    baseline = np.polyval(np.polyfit(offsets[flank], profile[flank], 1), offsets)
    residual = profile-baseline
    scatter = 1.4826*np.nanmedian(abs(residual[flank]-np.nanmedian(residual[flank])))
    threshold = 2*np.maximum(noise, scatter)
    radii = []
    for side in (-1, 1):
        for radius in range(minimum, int(cap)-1):
            cells = np.isin(offsets, side*np.arange(radius, radius+3))
            if np.all(abs(residual[cells]) <= threshold[cells]):
                radii.append(radius); break
        else:
            raise ValueError('source wings do not reach background before a neighbour or detector boundary')
    radius = float(max(radii)+.5)
    return radius, dict(radius_pixels=radius, fwhm_pixels=float(fwhm),
        gaussian_core_fraction=.9973, wing_threshold_sigma=2., wing_run_pixels=3,
        method='trace-aligned median growth to noise-consistent wings',
        total_flux_guaranteed=False, neighbour_limited_radius_pixels=float(cap))


def background_limits(profile, model, mask=None):
    """Keep the full interior background curve plus two-sigma headroom visible."""
    profile, model = np.asarray(profile), np.asarray(model)
    use = np.isfinite(profile) & np.isfinite(model)
    use[:3] = False; use[-3:] = False
    background = use & np.asarray(mask, bool) if mask is not None else use
    if background.sum() < 5: background = use
    residual = (profile-model)[background]
    noise = max(float(1.4826*np.median(abs(residual-np.median(residual)))), 1e-6)
    level = float(np.median(model[background]))
    model_low, model_high = float(np.min(model[use])), float(np.max(model[use]))
    return (model_low-2*noise, max(model_high, float(np.max(profile[use])))+2*noise), dict(
        background_electrons=level, background_range_electrons=[model_low, model_high],
        sigma_electrons=noise, rule='full interior background curve minus 2 sigma to data/model peak plus 2 sigma')
