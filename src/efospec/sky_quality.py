"""Explain the existing native sky-line gates without changing their limits."""
from math import isfinite


def line_quality(line):
    minimum_snr = 5. if line['rest_air_angstrom'] == 6363.776 else 8.
    lower_width = .6 if line.get('profile') == 'uniform_slit_convolved_gaussian' else 3.1
    error = line.get('centroid_error_angstrom')
    failures = []
    if line['peak_snr'] < minimum_snr:
        failures.append(f"peak/residual SNR {line['peak_snr']:.1f} below {minimum_snr:g}")
    if error is None or not isfinite(error):
        failures.append('centroid uncertainty is unavailable')
    elif error > 1.5:
        failures.append(f'centroid uncertainty {error:.2f} A exceeds 1.50 A')
    if not lower_width < line['sigma_angstrom'] < 13.9:
        failures.append('fitted width is at or near its allowed bound')
    return dict(failed_gates=failures, minimum_peak_snr=minimum_snr,
                maximum_centroid_error_angstrom=1.5,
                interior_sigma_bounds_angstrom=[lower_width,13.9],
                snr_definition='fitted amplitude parameter / MAD sigma of fit residuals; not a detection significance')


def line_failure_message(line):
    quality = line_quality(line)
    if not quality['failed_gates']:
        return None
    return (f"sky line {line['rest_air_angstrom']:g}: "+'; '.join(quality['failed_gates'])
            +f" (peak/residual SNR {line['peak_snr']:.1f}; minimum {quality['minimum_peak_snr']:g})")


def explained_sky_failure(error):
    """Clarify legacy generic wording while preserving its archived record."""
    original = error.get('error','')
    lines = error.get('diagnostics',{}).get('lines',[])
    if 'weak or unconstrained' in original and lines:
        return line_failure_message(lines[-1]) or original
    return original
