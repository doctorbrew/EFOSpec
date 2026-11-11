"""Exposure-specific, inspection-only handoffs from a nightly log to Qt."""
import json
from pathlib import Path
import shlex
from urllib.parse import parse_qs, urlencode, urlsplit


def review_url(run, raw):
    return 'efospec://review?' + urlencode(dict(run=str(Path(run).resolve()), raw=Path(raw).name))


def parse_review_url(value):
    url = urlsplit(value)
    query = parse_qs(url.query, strict_parsing=True)
    if (url.scheme != 'efospec' or url.netloc != 'review' or url.path not in ('', '/')
            or url.fragment or set(query) != {'run', 'raw'}
            or any(len(v) != 1 for v in query.values())):
        raise ValueError('Expected an efospec://review link with one run and raw exposure.')
    run, raw = query['run'][0], query['raw'][0]
    if not Path(run).is_absolute() or Path(raw).name != raw or raw in {'.', '..'}:
        raise ValueError('Review links require an absolute run and an exposure filename.')
    return run, raw


def review_command(run, raw):
    return shlex.join(['efospec', 'gui', str(Path(run).resolve()), '--raw', Path(raw).name])


def failures(manifest):
    return manifest.get('errors', []) + manifest.get('skipped', [])


def failure_reason(item):
    from .sky_quality import explained_sky_failure
    return explained_sky_failure(item) or item.get('reason') or item.get('code', 'Reduction failed')


def recovery_advice(item):
    code = item.get('code')
    if code == 'background_support_required':
        return ('Inspect the final trace, aperture and rejected background pixels. Refit clean bands on both '
                'sides of the final trace, then rerun extraction and support checks in a new revision.')
    if code == 'wavelength_validation_failed':
        return ('Inspect the arc identification, sky-line fits and independent residuals. Background edits '
                'alone do not validate wavelengths. Review counts retain unshifted arc wavelengths.')
    if code == 'unsupported_setup':
        return ('This setup is outside the selected reduction route. Check matching arcs, flats and standards '
                'and the separate red/filtered routes; an aperture edit cannot add setup support.')
    return 'Inspect source identity, trace and calibration diagnostics before extracting a new revision.'


def failure_log(run, item):
    """Keep recorded reasons available even when an archived log has moved."""
    lines = [item.get('object', 'Unknown'), item.get('path', ''),
             item.get('code', 'Reduction failed'), failure_reason(item), recovery_advice(item)]
    if item.get('traceback'):
        path = Path(item['traceback'])
        try:
            path.resolve().relative_to(Path(run).resolve())
            lines += ['\nOriginal error log', path.read_text()]
        except (ValueError, OSError) as exc:
            lines += ['Original error log unavailable: ' + str(exc)]
    lines += ['\nSaved failure record', json.dumps(item, indent=2)]
    return '\n'.join(lines)
