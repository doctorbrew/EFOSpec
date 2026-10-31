"""Experimental rapid reduction: archive calibration bridge + PypeIt extraction.

This deliberately does not masquerade as a native PypeIt calibration run.
Only the inspected 2x2 EFOSC2 Gr11/Gr13 Free-filter mode is enabled.
"""
import json
import re
import sys
import traceback
from pathlib import Path
import shutil

import numpy as np
from astropy.io import fits

from .archive_calibration import fit_arc, sky_flexure
from .inventory import inventory, sha256
from .naming import science_stem, product_name


def target_hint(frame, legacy_root):
    """Use historical aperture geometry only; never use its measured flux."""
    h, setup = frame['metadata'], frame['setup']
    stem = science_stem(h['OBJECT'], h['DATE-OBS'], setup['grism'], setup['filter'], setup['slit'])
    for p in sorted(Path(legacy_root).rglob('ap'+stem+'_*')):
        match = re.search(r'^\s*center\s+([\d.]+)', p.read_text(), flags=re.M)
        if match:
            return float(match[1])-1, {'source':str(p), 'sha256':sha256(p),
                                       'association':'historical_aperture'}
    for p in sorted(Path(legacy_root).rglob(stem+'_*_ex.fits')):
        header = fits.getheader(p)
        if header.get('DATE-OBS') != h['DATE-OBS']:
            continue
        values = str(header.get('APNUM1','')).split()
        if len(values) == 4:
            return (float(values[2])+float(values[3]))/2-1, {
                'source':str(p), 'sha256':sha256(p), 'association':'historical_aperture'}
    # This is an acquisition-position hypothesis, not an astrometric identity.
    return 449., {'source':'nominal acquisition position in this dataset',
                  'association':'UNVERIFIED_target_association'}


def select_archive(frame, reference_root):
    setup, h = frame['setup'], frame['metadata']
    if (setup['grism'] not in {'Gr11','Gr13'} or setup['filter'] != 'Free'
            or setup['binx'] != 2 or setup['biny'] != 2):
        raise ValueError('rapid archive bridge supports only Gr11/Gr13 Free, 2x2')
    base = Path(reference_root)/'archive/efosc'
    arcs = sorted((base/'arc'/setup['grism']/setup['filter']/setup['slit']).glob('*.fits'))
    if len(arcs) != 1:
        raise ValueError(f'exactly one reviewed archived arc required, found {len(arcs)}')
    candidates = []
    for p in sorted((base/'sens'/setup['grism']/setup['filter']).glob('*.fits')):
        sh = fits.getheader(p)
        if sh.get('MJD-OBS') is not None:
            candidates.append((abs(sh['MJD-OBS']-h['MJD-OBS']), p))
    candidates.sort()
    if not candidates or (len(candidates)>1 and candidates[0][0] == candidates[1][0]):
        raise ValueError('missing or tied archived sensitivity association')
    return arcs[0], candidates[0][1]


def extract_frame(frame, reference_root, output, hint, hint_info, waveair, arc_qa,
                  sensitivity, shift, sky_qa):
    import pypeit
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph

    if pypeit.__version__ != '1.14.0':
        raise ValueError('this runner is tested only with PypeIt 1.14.0')
    path = Path(frame['path'])
    h, setup = frame['metadata'], frame['setup']
    stem = science_stem(h['OBJECT'], h['DATE-OBS'], setup['grism'], setup['filter'], setup['slit'])
    registry = {p.name: fits.getheader(p).get('DATE-OBS') for p in (output/'products').glob('*_f.fits')}
    filename = product_name(stem, h['DATE-OBS'], registry, '_f')
    basename = filename[:-7]
    if (output/'products'/filename).exists():
        raise FileExistsError(f'product already exists: {filename}; use a fresh output directory')
    inst = EFOSpecEFOSC2Spectrograph()
    ny, nx = waveair.shape
    ymin = 4 if setup['grism']=='Gr11' else 0
    xlo, xhi = max(0,int(hint)-70), min(nx,int(hint)+71)
    with fits.open(path) as hdus:
        det = inst.get_detector_par(1,hdus)
        data = hdus[0].data[ymin:1015,99+xlo:99+xhi].astype(float)*h['ESO DET OUT1 GAIN']
    w = waveair[:,xlo:xhi]+shift
    from .extraction import extract_spectra
    from .products import PreparedExposure, export_spectrum
    context = PreparedExposure(frame, Path(reference_root), det, data, w, xlo, ymin,
                               hint, hint_info, arc_qa, Path(sensitivity), shift, sky_qa)
    engine = extract_spectra(data, w, det, exposure_time=h['EXPTIME'],
                            read_noise=h['ESO DET OUT1 RON'], output=output,
                            basename=basename, target_position=hint-xlo)
    return export_spectrum(context, engine, 'primary', output, basename)


def reduce_night(input_dir, output_dir, reference_root, *, targets=None, include_standards=False,
                 plot_python=None, skip_report=False):
    """Single-writer run with durable per-exposure results and explicit failures."""
    output = Path(output_dir).resolve()
    reference_root = Path(reference_root).resolve()
    if (output/'run.json').exists():
        raise FileExistsError('run.json exists; choose a new run directory to preserve source details')
    for sub in ('products','native','qa','QA/PNGs','source'):
        (output/sub).mkdir(parents=True,exist_ok=True)
    report = inventory([input_dir])
    if report['errors'] or report['identity_conflicts']:
        raise ValueError('resolve unreadable inputs or conflicting archive identities first')
    roles = {'science','standard_candidate'} if include_standards else {'science'}
    frames = [f for f in report['frames'] if f['role'] in roles and 'duplicate_of' not in f
              and (not targets or f['metadata']['OBJECT'] in targets)]
    if not frames:
        raise ValueError('no matching raw exposures')
    if any(f['issues'] for f in frames):
        raise ValueError('selected frames have invalid metadata')
    import pypeit
    import astropy
    import scipy
    source_hashes={}
    for p in sorted(Path(__file__).parent.glob('*.py')):
        source_hashes[p.name]=sha256(p)
        shutil.copyfile(p,output/'source'/p.name)
    run = {'schema_version':1,'status':'EXPERIMENTAL','method':'archive_calibration_bridge_with_native_PypeIt_extraction',
           'input_dir':str(Path(input_dir).resolve()),'output_dir':str(output),
           'python':sys.executable,'pypeit_version':pypeit.__version__,'numpy_version':np.__version__,
           'python_version':sys.version.split()[0], 'astropy_version':astropy.__version__,
           'scipy_version':scipy.__version__, 'source_sha256':source_hashes,
           'limitations':['No raw arc, bias or flat calibration in this demonstration.',
                         'Archived IRAF line positions and sensitivity are imported; not native PypeIt calibration generation.',
                         'No telluric correction; absolute flux and red second-order contamination are unvalidated.',
                         'Red fringing remains because rapid processing applies no flat correction.',
                         'Source positions without a historical aperture remain unverified.',
                         'Resampling covariance is not stored; output uncertainty is diagonal only.'],
           'results':[],'errors':[],'skipped':[]}
    cache = {}
    for f in sorted(frames,key=lambda f:f['metadata']['MJD-OBS']):
        try:
            if f['setup']['grism'] not in {'Gr11','Gr13'}:
                run['skipped'].append({'path':f['path'],'reason':'grism outside demonstrated archive bridge'})
                continue
            arc,sens = select_archive(f,reference_root)
            if str(arc) not in cache:
                cache[str(arc)]=fit_arc(arc)
            wave,arcqa=cache[str(arc)]
            raw = fits.getdata(f['path']).astype(float)
            ymin=4 if f['setup']['grism']=='Gr11' else 0
            data=raw[ymin:1015,99:950]
            if data.shape!=wave.shape:
                raise ValueError('archived arc and trimmed science geometry disagree')
            shift,skyqa=sky_flexure(data,wave)
            hint,hintinfo=target_hint(f,input_dir)
            print(f"Reducing {f['metadata']['OBJECT']} {f['setup']['grism']}: shift {shift:.3f} A",file=sys.stderr,flush=True)
            qa=extract_frame(f,reference_root,output,hint,hintinfo,wave,arcqa,sens,shift,skyqa)
            run['results'].append(qa)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            run['errors'].append({'path':f['path'],'object':f['metadata']['OBJECT'],'error':str(exc)})
        finally:
            (output/'run.json').write_text(json.dumps(run,indent=2,allow_nan=False)+'\n')
    if not skip_report:
        from .report import build_report
        try:
            run['report'] = build_report(output, plot_python=plot_python)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            run['report'] = {'status': 'incomplete', 'generation_error': str(exc)}
        (output/'run.json').write_text(json.dumps(run, indent=2, allow_nan=False)+'\n')
    return run
