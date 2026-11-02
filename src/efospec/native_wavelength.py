"""Experimental raw-arc identification with physical EFOSC2 constraints.

No archive arc spectra, IRAF pixel IDs, or legacy polynomial coefficients.
Reference selection: ESO EFOSC2 manual v4.2, Table 17 (air wavelengths).
Actual fit wavelengths: PypeIt/NIST HeI+ArI lists in vacuum Angstroms.
"""
from itertools import combinations
import numpy as np
from numpy.polynomial import Polynomial

ESO_MANUAL = 'https://www.eso.org/sci/facilities/lasilla/instruments/efosc/doc/manual/EFOSC2manual_v4.2.pdf'
ESO_GRISMS = 'https://www.eso.org/sci/facilities/lasilla/instruments/efosc/inst/Efosc2Grisms.html'
# Range and dispersion are approximate instrument priors, not fitted solutions.
GRISMS = {'Gr11': (3380., 7520., 4.08), 'Gr13': (3685., 9315., 5.54),
          'Gr16': (6015., 10320., 4.24)}
# Conservative acceptance bound, distinct from the wider hypothesis search.
# A 300-A bound admitted blue ghost IDs in a real Gr11/slit1.5 arc despite
# small RMS and plausible red sky lines. Never use extrapolation as delivery.
ENDPOINT_TOLERANCE = 100.
ESO_AIR = np.array([3888.646,3948.979,3964.729,4044.420,4158.590,4200.674,
    4300.101,4333.561,4471.479,4510.733,4713.146,4921.931,5015.680,5875.621,
    6114.923,6172.278,6678.151,6752.833,6871.289,6965.430,7030.25,7065.190,
    7147.04,7272.93,7383.980,7503.869,7514.65,7635.106,7723.984,7948.176,
    8014.786,8115.311,8264.522,8408.210,8424.647,8521.442,8667.944,
    9122.967,9194.638,9224.499,9354.22,9657.78,9784.50,10830.30])


def physical_lines():
    from astropy import units as u
    from pypeit.core.wave import airtovac
    from pypeit.core.wavecal import waveio
    table = waveio.load_line_lists(['HeI', 'ArI'], include_unknown=False)[0]
    vacuum = airtovac(ESO_AIR*u.AA).value
    # This tolerance associates published rounded values with NIST entries;
    # it is not a tolerance for fitting an arc or accepting a solution.
    keep = np.min(abs(np.asarray(table['wave'])[:, None]-vacuum), axis=1) < .6
    table = table[keep]
    table.sort('wave')
    return table


def validate_solution(fit, grism, *, filter_name='Free'):
    """Reject small-RMS false solutions and unsupported wavelength extrapolation."""
    low, high, nominal = GRISMS[grism]
    if fit is None or fit.pypeitfit is None:
        raise ValueError('no native wavelength fit')
    wave = np.asarray(fit.wave_soln)
    dispersion = np.diff(wave)
    if (not np.isfinite(wave).all() or np.any(dispersion <= 0)
            or not .7*nominal < np.median(dispersion) < 1.3*nominal
            or abs(wave[0]-low) > ENDPOINT_TOLERANCE
            or abs(wave[-1]-high) > ENDPOINT_TOLERANCE):
        raise ValueError('native wavelength fit violates instrument range/dispersion/monotonicity: '
                         f'endpoints={wave[[0,-1]].tolist()}, expected={low,high} '
                         f'+/-{ENDPOINT_TOLERANCE} A')
    used = np.asarray(fit.pypeitfit.gpm, dtype=bool)
    pixels, refs = np.asarray(fit.pixel_fit)[used], np.asarray(fit.wave_fit)[used]
    start = np.searchsorted(wave, 4950.) if filter_name == 'GG495' else 0
    histogram = np.histogram(pixels, bins=np.linspace(start, len(wave)-1, 4))[0]
    if len(pixels) < 10 or min(histogram) < 2 or np.ptp(pixels)/(len(wave)-1-start) < .7:
        raise ValueError('native wavelength IDs lack spectral coverage: need 10 lines and two per third')
    if not np.isfinite(fit.rms) or fit.rms > .25:
        raise ValueError('native wavelength residual exceeds 0.25 pixel')
    # Leave out each interior line and refit; endpoints define the usable bracket.
    residuals = []
    degree = len(fit.pypeitfit.fitc)-1
    for index in range(1, len(pixels)-1):
        train = np.arange(len(pixels)) != index
        model = Polynomial.fit(pixels[train], refs[train], degree)
        residuals.append(float((model(pixels[index])-refs[index])/np.median(dispersion)))
    held_rms = float(np.sqrt(np.mean(np.square(residuals))))
    if held_rms > .25 or max(abs(np.asarray(residuals))) > .5:
        raise ValueError('native held-out line residual exceeds 0.25 RMS / 0.5 maximum pixel')
    return {'rms_pixel':float(fit.rms), 'held_out_rms_pixel':held_rms,
            'held_out_max_pixel':float(max(abs(np.asarray(residuals)))),
            'n_lines':len(pixels), 'lines_per_third':histogram.tolist(),
            'reference_pixels':pixels.tolist(), 'reference_vacuum_angstrom':refs.tolist(),
            'valid_wave_vacuum_angstrom':[float(min(refs)),float(max(refs))],
            'detector_wave_limits_vacuum_angstrom':wave[[0,-1]].tolist(),
            'median_dispersion_angstrom_per_pixel':float(np.median(dispersion)),
            'endpoint_tolerance_angstrom':ENDPOINT_TOLERANCE,
            'status':'EXPERIMENTAL', 'independent_science_validation':False}


def fit_raw_arc_spectrum(spectrum, grism, *, filter_name='Free', fwhm=4., nonlinear_counts=47709.):
    """Identify raw peaks by bounded affine hypotheses, then refine curvature.

    Search bounds come from the published grism range/dispersion. Candidate
    matches must cover the spectrum, and competing high-scoring solutions
    must agree. No fit is accepted using residual RMS alone.
    """
    from pypeit.core import arc
    from pypeit.core.wavecal import wv_fitting
    if grism not in GRISMS or (grism == 'Gr16' and filter_name != 'OG530') or (
            grism != 'Gr16' and filter_name not in {'Free','GG495'}):
        raise ValueError('unsupported native calibration setup')
    spectrum = np.asarray(spectrum, dtype=float)
    if spectrum.ndim != 1 or not np.isfinite(spectrum).all() or len(spectrum) != 1024:
        raise ValueError('native arc fitting requires a finite 1024-pixel spectrum')
    low, high, nominal = GRISMS[grism]
    lines = physical_lines()
    refs = np.asarray(lines['wave'])
    keep = (refs > low-150) & (refs < high+150)
    if filter_name == 'GG495': keep &= refs > 4950.
    lines, refs = lines[keep], refs[keep]
    detected = arc.detect_lines(spectrum, sigdetect=10., fwhm=fwhm, nonlinear_counts=nonlinear_counts)
    peaks = detected[2][detected[5]]
    if len(peaks) < 10:
        raise ValueError('insufficient unsaturated native arc peaks')
    hypotheses = []
    pairs = np.array(list(combinations(refs, 2)))
    # Only separated peaks seed the search; local blends cannot set dispersion.
    for i, j in combinations(range(len(peaks)), 2):
        if peaks[j]-peaks[i] < 300: continue
        disp = (pairs[:,1]-pairs[:,0])/(peaks[j]-peaks[i])
        zero = pairs[:,0]-peaks[i]*disp
        eligible = (.85*nominal < disp) & (disp < 1.15*nominal) & (abs(zero-low) < 300)
        for d, z in zip(disp[eligible], zero[eligible]):
            distance = abs((z+d*peaks)[:,None]-refs).min(axis=1)
            count = int((distance < 20.).sum())
            if count >= 10: hypotheses.append((count,float(z),float(d)))
    results = []
    start = max(0., (4950.-low)/nominal) if filter_name == 'GG495' else 0.
    starts = set()
    for _, zero, disp in sorted(hypotheses, reverse=True):
        predicted = zero+disp*peaks
        # Near-duplicate affine seeds must not exhaust the search budget before
        # a distinct line-ID hypothesis is tried (observed in Gr11/slit1.5).
        initial_ids = abs(predicted[:,None]-refs).argmin(axis=1)
        initial_good = abs(predicted-refs[initial_ids]) < 20.
        seed_key = (tuple(np.flatnonzero(initial_good)), tuple(initial_ids[initial_good]))
        if seed_key in starts: continue
        starts.add(seed_key)
        if len(starts) > 300: break
        for tolerance, degree in [(20,2),(12,2),(8,3),(6,4),(3,4),(2,4)]:
            ids = abs(predicted[:,None]-refs).argmin(axis=1)
            good = abs(predicted-refs[ids]) < tolerance
            good &= np.array([np.sum(ids[good] == v) == 1 for v in ids])
            if good.sum() < 10: break
            polynomial = Polynomial.fit(peaks[good], refs[ids[good]], degree)
            predicted = polynomial(peaks)
        else:
            counts = np.histogram(peaks[good], bins=np.linspace(start,1023,4))[0]
            if min(counts) < 2: continue
            rms = float(np.sqrt(np.mean((predicted[good]-refs[ids[good]])**2)))
            results.append((int(good.sum()),-rms,polynomial,good,ids))
    if not results:
        raise ValueError('no arc identification consensus with adequate spectral coverage')
    results.sort(key=lambda r:r[:2], reverse=True)
    accepted, seen = [], set()
    for candidate in results:
        _, _, _, good, ids = candidate
        key = (tuple(np.flatnonzero(good)),tuple(ids[good]))
        if key in seen: continue
        seen.add(key)
        fit = wv_fitting.iterative_fitting(spectrum, peaks, np.flatnonzero(good), refs[ids[good]],
            lines, nominal, input_only=True, n_final=4)
        try: qa = validate_solution(fit, grism, filter_name=filter_name)
        except ValueError: continue
        accepted.append((fit,qa))
    if not accepted:
        raise ValueError('no native wavelength consensus passes physical and held-out gates')
    accepted.sort(key=lambda item:(-item[1]['n_lines'],item[1]['held_out_rms_pixel']))
    fit,qa = accepted[0]
    for alternative, altqa in accepted[1:]:
        if altqa['n_lines'] < qa['n_lines']-1: continue
        # Compare only where both solutions have identified-line support.
        lower = max(min(qa['reference_pixels']),min(altqa['reference_pixels']))
        upper = min(max(qa['reference_pixels']),max(altqa['reference_pixels']))
        grid = np.linspace(lower,upper,101)/1023.
        if np.max(abs(alternative.pypeitfit.eval(grid)-fit.pypeitfit.eval(grid))) > nominal:
            raise ValueError('competing native wavelength identifications require review')
    qa.update(method='bounded_physical_line_consensus', physical_reference=ESO_MANUAL,
              instrument_prior=ESO_GRISMS,
              reference_selection='ESO Table 17 matched to PypeIt/NIST HeI+ArI within 0.6 A',
              fwhm_detection_pixel=float(fwhm), nonlinear_limit_electron=float(nonlinear_counts))
    return fit, qa


def reidentify_raw_arc(spectrum, grism, template_fit, template_spectrum, *,
                      filter_name='Free', fwhm=4., nonlinear_counts=47709.):
    """Refit measured peaks using a hash-checked native arc as an ID seed.

    The caller verifies the template's setup, files and raw inputs. Only its
    accepted line positions seed PypeIt's cross-correlation/reidentification;
    extrapolated template regions cannot supply new IDs.
    """
    from pypeit.core.wavecal import autoid, wv_fitting
    validate_solution(template_fit, grism, filter_name=filter_name)
    spectrum = np.asarray(spectrum, dtype=float)
    template_spectrum = np.asarray(template_spectrum, dtype=float)
    if (spectrum.shape != (1024,) or template_spectrum.shape != (1024,)
            or not np.isfinite(spectrum).all() or not np.isfinite(template_spectrum).all()):
        raise ValueError('native reidentification requires finite 1024-pixel spectra')
    used = np.asarray(template_fit.pypeitfit.gpm, dtype=bool)
    lines = physical_lines()
    peaks, _, pattern = autoid.reidentify(spectrum, template_spectrum,
        template_fit.wave_soln, lines, 1,
        det_arxiv={'0': np.asarray(template_fit.pixel_fit)[used]},
        cc_thresh=.8, cc_local_thresh=.8, match_toler=1., sigdetect=10.,
        fwhm=fwhm, nonlinear_counts=nonlinear_counts)
    good = np.flatnonzero(pattern['mask'])
    if len(good) < 10:
        raise ValueError('native template reidentification found fewer than 10 reliable lines')
    fit = wv_fitting.iterative_fitting(spectrum, peaks, good, pattern['IDs'][good],
        lines, GRISMS[grism][2], input_only=True, n_final=4)
    qa = validate_solution(fit, grism, filter_name=filter_name)
    qa.update(method='native_template_reidentify', global_correlation_min=.8,
        local_correlation_min=.8, matching_tolerance_pixel=1.,
        fwhm_detection_pixel=float(fwhm), nonlinear_limit_electron=float(nonlinear_counts),
        physical_reference=ESO_MANUAL, instrument_prior=ESO_GRISMS)
    return fit, qa
