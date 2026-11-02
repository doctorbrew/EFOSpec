"""Explicit legacy calibration conversion for experimental rapid reductions.

The arc is a *processed archive reference*, never labelled a raw input.
Wavelengths in its IRAF identification list are air Angstroms. A new 2-D
polynomial is fitted to the recorded line positions; IRAF is not executed.
"""
from pathlib import Path
import re
import numpy as np
from numpy.polynomial.legendre import legvander2d, legval2d
from scipy.optimize import curve_fit
from scipy.sparse import csr_matrix
from astropy.io import fits
from .inventory import sha256


def arc_records(path):
    records = []
    for block in re.split(r'\nbegin\s+', Path(path).read_text())[1:]:
        match = re.search(r'\[([\d.]+),\*\]', block)
        if not match:
            continue
        x = float(match[1]) - 1  # IRAF is one-based
        lines = block.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith('features'):
                for row in lines[i+1:i+1+int(line.split()[1])]:
                    col = row.split()
                    if len(col) >= 6 and int(col[5]) == 1:
                        records.append([x, float(col[0])-1, float(col[2])])
    if len(records) < 30:
        raise ValueError('insufficient archived arc identifications')
    return np.array(records)


def fit_arc(arc_path):
    path = Path(arc_path)
    ids = path.parent / 'database' / ('id' + path.stem)
    records = arc_records(ids)
    image = fits.getdata(path).astype(float)
    ny, nx = image.shape
    x, y, ref = records.T
    v = legvander2d(2*x/(nx-1)-1, 2*y/(ny-1)-1, [3,4]).reshape(len(x), -1)
    coefficients = np.linalg.lstsq(v, ref, rcond=None)[0]
    residual = v @ coefficients - ref
    # Hold out entire interior reference lines, not neighbouring positions of
    # the same line, to avoid leakage between spatial samples.
    lines = np.unique(ref)
    hold_lines = lines[2:-2:4]
    hold = np.isin(ref, hold_lines)
    coeff_test = np.linalg.lstsq(v[~hold], ref[~hold], rcond=None)[0]
    held_rms = float(np.sqrt(np.mean((v[hold] @ coeff_test-ref[hold])**2)))
    yy, xx = np.indices(image.shape)
    wave = legval2d(2*xx/(nx-1)-1, 2*yy/(ny-1)-1, coefficients.reshape(4,5))
    if not np.all(np.diff(wave, axis=0) > 0):
        raise ValueError('non-monotonic archive wavelength solution')
    rms = float(np.sqrt(np.mean(residual**2)))
    if rms > 1.5 or held_rms > 2.0:
        raise ValueError(f'archive arc fit fails experimental gate: RMS={rms}, held-out={held_rms}')
    return wave, {'arc': str(path.resolve()), 'arc_sha256': sha256(path),
        'identifications': str(ids.resolve()), 'identifications_sha256': sha256(ids),
        'source': 'processed_archived_arc_and_IRAF_line_positions',
        'medium': 'air', 'unit': 'Angstrom', 'spatial_order': 3, 'spectral_order': 4,
        'rms_angstrom': rms, 'held_out_rms_angstrom': held_rms,
        'held_out_lines': hold_lines.tolist(), 'reference_lines': lines.tolist(),
        'n_identifications': len(records),
        'limitation': 'held-out archival IDs test the imported fit, not a contemporary raw arc'}


class SkyFlexureError(ValueError):
    """A failed scientific gate with machine-readable measurements."""
    code = 'sky_flexure_unreliable'
    action = 'Inspect sky-line fits and contemporary raw arcs; do not assume zero flexure.'

    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('cannot establish consistent sky flexure from two lines: '
                         + str(diagnostics['lines']))


def sky_flexure(data, waveair, *, max_shift=80.):
    """Fit 5577 and the 6300/6363 blend with independently free centroids.

    The shift uses only 5577 and 6300 (S/N > 8, agreement within 3 A).
    6363 is a check, never a third shift anchor or a fixed-separation constraint.
    Its fit shares a continuum with 6300, so their errors are correlated.
    All wavelengths and the bounded search radius are in air Angstroms.
    """
    data, waveair = np.asarray(data), np.asarray(waveair)
    if (data.ndim != 2 or data.shape != waveair.shape or data.shape[1] < 45
            or not np.isfinite(waveair).all() or not np.all(np.diff(waveair, axis=0) > 0)
            or not np.isfinite(max_shift) or max_shift <= 0):
        raise ValueError('sky flexure requires matching increasing 2D wavelengths and a positive search limit')
    wave = waveair[:, data.shape[1]//2]
    columns = np.arange(20, data.shape[1]-20, 5)
    sky = np.nanmedian([np.interp(wave, waveair[:, i], data[:, i]) for i in columns], axis=0)
    measurements, failures = [], []
    diagnostics = {'lines': measurements, 'fit_failures': failures,
                   'max_shift_angstrom': float(max_shift),
                   'method': 'independent_centroids_with_red_doublet_model',
                   'anchor_snr_min': 8., 'anchor_agreement_angstrom': 3.,
                   'check_shares_continuum_with_6300': True}

    def gaussian(w, a, center, sigma):
        return a*np.exp(-.5*((w-center)/sigma)**2)

    def record(rest, p, cov, index, residual, bounds):
        noise = max(float(1.4826*np.median(abs(residual-np.median(residual)))), 1e-6)
        a, center, sigma = p[index:index+3]
        errors = np.sqrt(np.maximum(np.diag(cov)[index:index+3], 0.))
        # Reject constrained peaks and unconstrained covariance, rather than
        # mistaking an optimizer's boundary solution for a measured line.
        at_bound = bool(any(abs(v-lo) < .01 or abs(v-hi) < .01
                            for v, lo, hi in zip(p[index:index+3],
                                               bounds[0][index:index+3], bounds[1][index:index+3])))
        measurements.append({'rest_air_angstrom': rest, 'measured_air_angstrom': float(center),
            'offset_angstrom': float(rest-center), 'peak_snr': float(a/noise),
            'sigma_angstrom': float(sigma),
            'centroid_error_angstrom': float(errors[1]) if np.isfinite(errors[1]) else None,
            'fit_valid': bool(np.isfinite(errors).all() and not at_bound), 'at_fit_bound': at_bound})

    # First locate the isolated green line, then centre its fitting window.
    rest = 5577.338
    search = (abs(wave-rest) < max_shift) & np.isfinite(sky)
    if search.sum() < 10:
        failures.append({'line': rest, 'reason': 'insufficient wavelength coverage'})
        raise SkyFlexureError(diagnostics)
    peak = float(wave[search][np.argmax(sky[search])])
    keep = (abs(wave-peak) < 55.) & np.isfinite(sky)
    w, f = wave[keep], sky[keep]
    def green(w, a, center, sigma, b, slope):
        return gaussian(w, a, center, sigma)+b+slope*(w-peak)
    bounds = ([0., rest-max_shift, 2., -np.inf, -np.inf],
              [np.inf, rest+max_shift, 16., np.inf, np.inf])
    try:
        base = float(np.median(np.r_[f[:3], f[-3:]]))
        p, cov = curve_fit(green, w, f, p0=[max(float(f.max()-base), 1.), peak, 7., base, 0.],
                           bounds=bounds, maxfev=5000)
        record(rest, p, cov, 0, f-green(w, *p), bounds)
    except (ValueError, RuntimeError) as exc:
        failures.append({'line': rest, 'reason': str(exc)})
        raise SkyFlexureError(diagnostics) from exc
    seed_shift = measurements[0]['offset_angstrom']
    # Both red centroids vary freely within +/-20 A of the green estimate.
    # Modelling the neighbour prevents its wings from corrupting the baseline.
    centers = np.array([6300.304, 6363.776])-seed_shift
    keep = (wave > centers[0]-55.) & (wave < centers[1]+55.) & np.isfinite(sky)
    w, f = wave[keep], sky[keep]
    def red(w, a, c, s, a2, c2, s2, b, slope):
        return gaussian(w, a, c, s)+gaussian(w, a2, c2, s2)+b+slope*(w-centers.mean())
    lower, upper, guess = [], [], []
    if len(w) < 12:
        failures.append({'line': '6300/6363', 'reason': 'insufficient wavelength coverage'})
    else:
        base = float(np.median(np.r_[f[:3], f[-3:]]))
        for line, center in zip([6300.304, 6363.776], centers):
            lower.extend([0., max(line-max_shift, center-20.), 2.])
            upper.extend([np.inf, min(line+max_shift, center+20.), 16.])
            guess.extend([max(float(np.interp(center, w, f)-base), 1.), center, 7.])
        lower.extend([-np.inf, -np.inf]); upper.extend([np.inf, np.inf]); guess.extend([base, 0.])
        try:
            p, cov = curve_fit(red, w, f, p0=guess, bounds=(lower, upper), maxfev=5000)
            for line, index in [(6300.304, 0), (6363.776, 3)]:
                record(line, p, cov, index, f-red(w, *p), (lower, upper))
        except (ValueError, RuntimeError) as exc:
            failures.append({'line': '6300/6363', 'reason': str(exc)})
    anchors = [m for m in measurements if m['rest_air_angstrom'] != 6363.776
               and m['peak_snr'] > 8 and m['fit_valid']]
    diagnostics['accepted_anchor_count'] = len(anchors)
    diagnostics['anchor_difference_angstrom'] = (abs(anchors[0]['offset_angstrom']-anchors[1]['offset_angstrom'])
                                                if len(anchors) == 2 else None)
    diagnostics['failed_gates'] = ([f'anchor_{int(m["rest_air_angstrom"])}_snr_or_fit'
                                  for m in measurements if m['rest_air_angstrom'] != 6363.776
                                  and (m['peak_snr'] <= 8 or not m['fit_valid'])]
                                 + (['missing_anchor_fit'] if len(measurements) < 2 else [])
                                 + (['anchor_disagreement'] if len(anchors) == 2 and
                                    diagnostics['anchor_difference_angstrom'] > 3 else []))
    if len(anchors) != 2 or abs(anchors[0]['offset_angstrom']-anchors[1]['offset_angstrom']) > 3:
        raise SkyFlexureError(diagnostics)
    shift = float(np.mean([m['offset_angstrom'] for m in anchors]))
    for m in measurements:
        m['residual_after_shift_angstrom'] = m['measured_air_angstrom']+shift-m['rest_air_angstrom']
    check = next((m for m in measurements if m['rest_air_angstrom'] == 6363.776
                  and m['peak_snr'] > 5 and m['fit_valid']), None)
    diagnostics.update(shift_angstrom=shift,
        held_out_6363_residual_angstrom=None if check is None else check['residual_after_shift_angstrom'],
        held_out_6363_pass=bool(check is not None and abs(check['residual_after_shift_angstrom']) < 3))
    return shift, diagnostics


def sensitivity_factor(waveair, sensitivity_path, extinction_path, exposure, airmass, gain):
    """Convert extracted electrons/pixel to physical F_lambda per air Angstrom.

    IRAF S=2.5*log10((ADU/s/Angstrom)/F_lambda), not a PypeIt sensfunc file.
    """
    values,h=fits.getdata(sensitivity_path,header=True)
    step=h.get('CD1_1',h.get('CDELT1'))
    sw=h['CRVAL1']+(np.arange(values.size)+1-h.get('CRPIX1',1))*step
    if step<=0 or exposure<=0 or gain<=0 or airmass<1:
        raise ValueError('invalid response calibration inputs')
    ext=np.loadtxt(extinction_path)
    dispersion=np.gradient(waveair)
    good=(np.isfinite(waveair)&(dispersion>0)&(waveair>=sw[0])&(waveair<=sw[-1])
          &(waveair>=ext[0,0])&(waveair<=ext[-1,0]))
    logresponse=np.interp(waveair,sw,values)
    attenuation=10**(0.4*airmass*np.interp(waveair,ext[:,0],ext[:,1]))
    factor=attenuation/(gain*exposure*dispersion*10**(logresponse/2.5))
    return factor,good


def rebin_density(wave, flux, variance, valid, output_wave):
    """Bin-overlap flux-density resampling, including squared-weight variance.

    Bad/partially covered output bins remain invalid. Induced covariance is not
    stored and is explicitly documented in output source details.
    """
    wave,output_wave=np.asarray(wave),np.asarray(output_wave)
    if len(wave)<2 or len(output_wave)<2 or np.any(np.diff(wave)<=0) or np.any(np.diff(output_wave)<=0):
        raise ValueError('strictly increasing wavelength grids required')
    def edges(w):
        return np.r_[w[0]-(w[1]-w[0])/2,(w[:-1]+w[1:])/2,w[-1]+(w[-1]-w[-2])/2]
    a,b=edges(wave),edges(output_wave)
    rows,cols,weights=[],[],[]
    for i in range(len(output_wave)):
        for j in range(max(0,np.searchsorted(a,b[i],side='right')-1),min(len(wave),np.searchsorted(a,b[i+1]))):
            overlap=min(b[i+1],a[j+1])-max(b[i],a[j])
            if overlap>0:
                rows.append(i);cols.append(j);weights.append(overlap/(b[i+1]-b[i]))
    r=csr_matrix((weights,(rows,cols)),shape=(len(output_wave),len(wave)))
    valid=np.asarray(valid)&np.isfinite(flux)&np.isfinite(variance)&(variance>=0)
    good=np.asarray(r@valid.astype(float))>1-1e-8
    result=r@np.where(valid,flux,0.)
    var=r.power(2)@np.where(valid,variance,0.)
    return np.where(good,result,np.nan),np.where(good,var,np.nan),good
