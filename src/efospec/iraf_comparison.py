"""Optional read-only comparison with PESSTO/IRAF flux products beside raw data.

No reduction, calibration, source selection, wavelength shift or normalization
is performed here. Unsupported and ambiguous associations stay explicit.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import numpy as np
from astropy.io import fits
from astropy import units as u
from astropy.time import Time

from .inventory import sha256
from .naming import observing_night
from .run_paths import resolve_result_paths

SETUP = ('ESO INS GRIS1 NAME', 'ESO INS FILT1 NAME', 'ESO INS SLIT1 NAME',
         'ESO DET WIN1 BINX', 'ESO DET WIN1 BINY', 'ESO DET READ SPEED')
FLUX_UNIT = u.erg / u.cm**2 / u.s / u.AA


def discover(root):
    """Recognize flux-calibrated IRAF multispectra by headers, not filenames."""
    records, errors, seen = [], [], {}
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or not path.name.lower().endswith(('.fits', '.fit', '.fits.gz')):
            continue
        try:
            h = fits.getheader(path)
            if (str(h.get('INSTRUME', '')).strip() != 'EFOSC'
                    or h.get('FILETYPE') != 22208
                    or 'PYPEITV' in h or 'PYPEIT' in h or 'pypeit' in str(h.get('PROCSOFT', '')).lower()
                    or not ('IRAF-TLM' in h or str(h.get('PROCSOFT', '')).startswith('ntt_'))):
                continue
            digest = sha256(path)
            if digest in seen:
                seen[digest]['aliases'].append(str(path.resolve()))
                continue
            record = dict(path=str(path.resolve()), sha256=digest, aliases=[],
                          object=str(h.get('OBJECT', '')), status='discovered')
            records.append(record); seen[digest] = record
        except (OSError, ValueError) as exc:
            errors.append(dict(path=str(path), error=str(exc)))
    return records, errors


def match_header(header, frames, night):
    """Require a unique exposure identity and consistent setup/time metadata."""
    if observing_night(header['DATE-OBS']) != night.replace('-', ''):
        raise ValueError('IRAF product belongs to another observing night')
    provenance = {Path(str(v)).name for k, v in header.items()
                  if k.startswith('PROV') and k[4:].isdigit() and v}
    if len(provenance) > 1:
        raise ValueError('combined IRAF product: multiple raw exposures require explicit review')
    identity = provenance or ({Path(str(header['ARCFILE'])).name} if header.get('ARCFILE') else set())
    matches = []
    for frame in frames:
        raw = frame['metadata']
        ids = {Path(frame['path']).name, Path(str(raw.get('ARCFILE') or '')).name}
        if identity and not identity.intersection(ids):
            continue
        if any(header.get(k) is None or raw.get(k) is None or str(header[k]).strip() != str(raw[k]).strip()
               for k in ('OBJECT', *SETUP)):
            continue
        if abs(float(header['EXPTIME'])-float(raw['EXPTIME'])) > .01:
            continue
        if abs((Time(header['DATE-OBS'])-Time(raw['DATE-OBS'])).sec) > 1.:
            continue
        matches.append(frame)
    if len(matches) != 1:
        raise ValueError(f'expected one raw exposure with consistent identity/setup/time; found {len(matches)}')
    return matches[0], 'raw_provenance_and_metadata' if identity else 'unique_object_setup_time_exptime'


def read_spectrum(path, *, native=False):
    """Read a single-aperture linear flux spectrum; preserve validity gaps."""
    with fits.open(path, memmap=False) as hdus:
        h = hdus[0].header
        data = hdus[0].data
        if data is None or data.ndim != 3 or data.shape[1] != 1 or data.shape[0] < 1:
            raise ValueError('only single-aperture multispectra are supported')
        if h.get('DC-FLAG', 0) != 0 or str(h.get('CTYPE1', '')).upper() not in ('LINEAR', 'AWAV', 'WAVE'):
            raise ValueError('only explicit linear wavelength coordinates are supported')
        # WAT records must not hide a nonlinear multispec dispersion solution.
        if any('spec1' in str(v).lower() for k, v in h.items() if k.startswith('WAT2')):
            raise ValueError('IRAF multispec dispersion requires a dedicated reader')
        step = h.get('CD1_1', h.get('CDELT1'))
        if step is None or not np.isfinite(step) or step == 0:
            raise ValueError('missing or invalid linear wavelength increment')
        wave_unit = h.get('CUNIT1')
        if not wave_unit:
            if 'angstrom' not in str(h.get('WAT1_001', '')).lower() and not native:
                raise ValueError('wavelength units are unspecified')
            wave_unit = 'Angstrom'
        wave = (h['CRVAL1']+(np.arange(data.shape[-1])+1-h.get('CRPIX1', 1))*step)
        wave = (wave*u.Unit(wave_unit)).to_value(u.AA)
        flux = (np.asarray(data[0, 0], float)*u.Unit(h['BUNIT'])).to_value(FLUX_UNIT)
        good = np.isfinite(wave) & np.isfinite(flux)
        if native:
            if 'VALID' not in hdus:
                raise ValueError('native product lacks validity mask')
            good &= hdus['VALID'].data[0].astype(bool)
        if good.sum() < 20:
            raise ValueError('fewer than 20 valid flux samples')
        if not (np.all(np.diff(wave)>0) or np.all(np.diff(wave)<0)):
            raise ValueError('wavelength grid is not monotonic')
        return wave, np.where(good, flux, np.nan), dict(
            wavelength_medium=h.get('WAVEMED', 'unspecified in IRAF header'),
            wavelength_frame=h.get('SPECSYS', 'unspecified'),
            aperture=h.get('APNUM1', 'unspecified'),
            detector_section=h.get('CCDSEC', 'unspecified'),
            trim_record=h.get('TRIM', 'unspecified'),
            band=h.get('BANDID1', 'primary flux band'), flux_unit=str(FLUX_UNIT))


def plot_pair(native_path, iraf_path, output, label, night, version):
    from .figure_style import house_style, save_qc, COLORS
    import matplotlib.pyplot as plt
    nw, nf, nm = read_spectrum(native_path, native=True)
    iw, inf, im = read_spectrum(iraf_path)
    lo, hi = max(nw.min(), iw.min()), min(nw.max(), iw.max())
    if hi <= lo:
        raise ValueError('no common wavelength coverage')
    shown=np.concatenate([flux[np.isfinite(flux) & (wave>=lo) & (wave<=hi)]*1e16
                          for wave,flux in ((nw,nf),(iw,inf))])
    if not shown.size:raise ValueError('no finite flux in the common wavelength range')
    bottom,top=min(0.,float(shown.min())),float(shown.max())
    padding=.08*max(top-bottom,.01)
    limits=(bottom-padding,top+padding)

    @house_style
    def render():
        fig, ax = plt.subplots(figsize=(13, 6))
        try:
            ax.plot(iw, inf*1e16, color=COLORS[2], lw=1.2, label='PESSTO / IRAF')
            ax.plot(nw, nf*1e16, color=COLORS[0], lw=1.2, label=f'EFOSpec / PypeIt {version}')
            ax.set(xlim=(lo, hi), xlabel=r'Wavelength ($\mathrm{\AA}$)',
                   ylim=limits,
                   ylabel=r'$F_\lambda\ (10^{-16}\,\mathrm{erg\,s^{-1}\,cm^{-2}\,\AA^{-1}})$',
                   title=f'{label} / {night}')
            fig.subplots_adjust(bottom=.25)
            return save_qc(fig, output, 'iraf-comparison', label, title_fontsize=28)
        finally:
            plt.close(fig)
    stem = render()
    return dict(native=nm, iraf=im, overlap_angstrom=[float(lo), float(hi)],
                flux_display_limits_1e_minus16=list(limits),
                display_policy='All finite samples from both spectra within the displayed wavelength range; include zero and pad by 8 percent',
                pdf=str(stem)+'.pdf', jpg=str(stem)+'.jpg')


def compare_run(run_dir, input_dir, output):
    run_dir, input_dir, output = map(lambda p: Path(p).resolve(), (run_dir, input_dir, output))
    manifest = run_dir/'run.json'; run_hash = sha256(manifest)
    run = json.loads(manifest.read_text())
    if run.get('execution_status') == 'running':
        raise ValueError('wait for reduction completion before comparing')
    night = run['night']
    from .inventory import inventory
    inv = inventory([input_dir])
    if inv['errors'] or inv['identity_conflicts']:
        raise ValueError('resolve raw inventory conflicts before comparison')
    frames = [f for f in inv['frames'] if f['role']=='science' and 'duplicate_of' not in f]
    candidates, scan_errors = discover(input_dir)
    results = {}
    for row in run['results']:
        if row.get('role') == 'science':
            results.setdefault(row['raw_sha256'], []).append(row)
    output.mkdir(parents=True, exist_ok=False)
    record = dict(schema_version=1, night=night, tag='iraf-comparison', parent_run=str(run_dir),
                  parent_sha256=run_hash, input_dir=str(input_dir), pypeit_version=run['pypeit_version'],
                  comparison_source_sha256=sha256(Path(__file__)),
                  created_utc=datetime.now(timezone.utc).isoformat(), candidates=candidates,
                  scan_errors=scan_errors, unmatched_native=[], status='complete',
                  limitations=['Overlays use delivered wavelengths and absolute flux; no shifts, normalization or interpolation.',
                    'Raw-exposure matching does not verify identical source/aperture; inspect both saved APNUM1 records.',
                    'IRAF products are historical comparisons, not ground truth; wavelength medium/frame may be unspecified.',
                    'Extraction, response, telluric and slit-loss differences can affect agreement; no scientific acceptance is inferred.'])
    compared = set()
    for index, item in enumerate(candidates):
        try:
            path = Path(item['path']); h = fits.getheader(path)
            frame, method = match_header(h, frames, night)
            item.update(raw=frame['path'], raw_sha256=frame['sha256'], match_method=method)
            rows = results.get(frame['sha256'], [])
            if len(rows) != 1:
                failures=[e.get('error',e.get('reason','')) for e in run.get('errors',[])+run.get('skipped',[])
                          if Path(e.get('path','')).resolve()==Path(frame['path']).resolve()]
                item.update(status='no_unique_native_product', reason='; '.join(failures) or
                            f'{len(rows)} delivered science products for this raw exposure')
                continue
            row = resolve_result_paths(rows[0], run_dir)
            native = Path(row['product']); native_hash = sha256(native)
            item.update(native_product=str(native), native_sha256=native_hash)
            folder=output/f'pair-{index+1:03d}';folder.mkdir()
            item.update(plot_pair(native, path, folder, item['object'], night, run['pypeit_version']))
            item['figure_sha256']={key:sha256(Path(item[key])) for key in ('pdf','jpg')}
            if sha256(path)!=item['sha256'] or sha256(native)!=native_hash:
                raise ValueError('comparison input changed while plotting')
            item['status']='compared';compared.add(frame['sha256'])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            item.update(status='not_compared', reason=str(exc))
    record['unmatched_native'] = [dict(object=r['object'], raw=r['raw'])
                                 for key, rows in results.items() if key not in compared for r in rows]
    record['status'] = 'partial' if scan_errors or any(c['status']!='compared' for c in candidates) else 'complete'
    if not candidates:record['status']='no_iraf_products'
    if sha256(manifest)!=run_hash:raise ValueError('parent manifest changed during comparison')
    (output/'comparison.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    return record


def run_for_revision(revision):
    revision=Path(revision).resolve()
    state=json.loads((revision/'night.json').read_text())
    root=revision/'iraf-comparison'
    output=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
    record=compare_run(revision/'reduction', state['input_dir'], output)
    pointer=dict(path=output.name, sha256=sha256(output/'comparison.json'))
    (root/'current.json').write_text(json.dumps(pointer, indent=2)+'\n')
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('revision', type=Path)
    args=parser.parse_args()
    result=run_for_revision(args.revision)
    print(json.dumps(dict(status=result['status'], compared=sum(c['status']=='compared' for c in result['candidates']))))
    return int(result['status']=='partial')


if __name__=='__main__':
    raise SystemExit(main())
