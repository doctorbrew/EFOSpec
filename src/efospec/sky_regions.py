"""Capture the actual PypeIt global-sky input selection for diagnostic plots.

This selection precedes iterative rejection. The later extraction jointly fits
object and sky profiles; it does not use fixed IRAF-style background apertures.
"""
import json
from pathlib import Path
import tempfile

import numpy as np
from astropy.io import fits

from .inventory import sha256


def capture_sky_selection(finder, found):
    """Recover the mask used in the last global fit with skip_second_find=True."""
    from pypeit.core import pixels

    if not finder.par['reduce']['findobj']['skip_second_find']:
        raise ValueError('sky selection capture requires the saved first-pass objects')
    # An explicit initial mask is the mask used by PypeIt's sole global fit.
    initial = getattr(finder, 'initial_skymask', None)
    selected = (finder.create_skymask(found) if initial is None else initial.copy())
    selected &= finder.sciImg.select_flag(invert=True)
    selected &= (finder.slitmask >= 0)
    selected &= np.isfinite(finder.sciImg.image) & np.isfinite(finder.sciImg.ivar)
    selected &= finder.sciImg.ivar > 0
    for i, slit in enumerate(finder.slits.spat_id):
        onslit = finder.slitmask == slit
        _, edge = pixels.ximg_and_edgemask(
            finder.slits_left[:, i], finder.slits_right[:, i], onslit,
            trim_edg=tuple(finder.par['reduce']['trim_edge']))
        selected[onslit] &= ~edge[onslit]
    return {
        'sky_input_mask': selected,
        'found_traces': np.array([s.TRACE_SPAT.copy() for s in found]),
        'found_names': np.array([s.NAME for s in found], dtype='U80'),
        'sky_mask_stage': np.array('global_sky_input_before_iterative_rejection'),
    }


def recover_sky_selection(result, run):
    """Replay finding for an older run and verify all recorded source positions.

Writes a diagnostic sidecar only. The spectra and saved extraction images are
read-only. New reductions capture the selection directly in their images NPZ.
"""
    import pypeit
    from pypeit.find_objects import FindObjects
    from pypeit.images.pypeitimage import PypeItImage
    from pypeit.slittrace import SlitTraceSet
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
    from .extraction import native_qa_context

    run = Path(run).resolve()
    manifest = json.loads((run/'run.json').read_text())
    if manifest.get('pypeit_version') != pypeit.__version__:
        raise ValueError('sky selection replay requires the original PypeIt '+
                         str(manifest.get('pypeit_version', 'unknown'))+' runtime')
    driver_digest = sha256(Path(__file__).with_name('pypeit_adapter.py'))
    if driver_digest != manifest['source_sha256']['pypeit_adapter.py']:
        raise ValueError('instrument defaults changed since this run; cannot assert an exact sky-mask replay')
    basename = Path(result['product']).name[:-7]
    images = run / 'native' / (basename + '_images.npz')
    sidecar = images.with_name(basename + '_sky_regions.npz')
    raw = Path(result['raw'])
    if sha256(raw) != result['raw_sha256']:
        raise ValueError('raw input changed since the reduction')
    image_digest = sha256(images)
    with np.load(images) as saved:
        if 'sky_input_mask' in saved.files:
            return {'object': result['object'], 'status': 'already captured in reduction'}
        data, wave = saved['data'], saved['waveair']
        origin = int(saved['spatial_origin'])
    inst = EFOSpecEFOSC2Spectrograph()
    with fits.open(raw) as hdus:
        h = hdus[0].header.copy()
        detector = inst.get_detector_par(1, hdus)
    settings = result['processing']
    par = inst.profile_parameters('rapid')
    par['flexure']['spec_method'] = 'skip'
    par['reduce']['findobj']['maxnumber_sci'] = settings['findobj_maxnumber']
    par['reduce']['findobj']['snr_thresh'] = settings['findobj_snr_threshold']
    par['reduce']['findobj']['skip_second_find'] = True
    par['reduce']['skysub']['bspline_spacing'] = settings['sky_bspline_spacing']
    rn = np.full(data.shape, h['ESO DET OUT1 RON']**2)
    sci = PypeItImage(data, ivar=1/(np.maximum(data, 0)+rn), rn2img=rn, base_var=rn,
                     detector=detector, exptime=h['EXPTIME'], noise_floor=0.,
                     shot_noise=True, bpm=~np.isfinite(data))
    sci.build_mask(saturation=detector['saturation']*h['ESO DET OUT1 GAIN'], mincounts=-1e10)
    ny, nx = data.shape
    slits = SlitTraceSet(np.zeros(ny), np.full(ny, nx-1.), 'MultiSlit',
                        detname='DET01', nspat=nx, PYP_SPEC=inst.name, binspec=2, binspat=2,
                        specmin=np.array([-.5]), specmax=np.array([ny-.5]))
    with tempfile.TemporaryDirectory(prefix='efospec-sky-replay-') as directory:
        work = Path(directory)
        (work/'QA/PNGs').mkdir(parents=True)
        par['rdx']['redux_path'] = str(work)
        finder = FindObjects.get_instance(sci, slits, inst, par, 'science',
                    tilts=(wave-wave.min())/(wave.max()-wave.min()), show=False, basename=basename)
        with native_qa_context():
            _, found = finder.run()
        expected = {s['name']: s['trimmed_spatial_pixel'] for s in result['target']['candidates']}
        actual = {s.NAME: float(s.SPAT_PIXPOS+origin) for s in found}
        if set(expected) != set(actual) or any(abs(expected[k]-actual[k]) > 1e-5 for k in expected):
            raise ValueError(f'object finding did not reproduce the reduction: {actual} != {expected}')
        selection = capture_sky_selection(finder, found)
    np.savez_compressed(sidecar, **selection)
    if sha256(images) != image_digest or sha256(raw) != result['raw_sha256']:
        raise ValueError('input changed during sky-mask replay')
    record = {'object': result['object'], 'pypeit_version': pypeit.__version__,
              'instrument_driver_sha256': driver_digest,
              'method': 'replayed original first-pass finding with recorded parameters',
              'stage': 'global sky input selection before iterative rejection',
              'limitation': 'local extraction jointly fits object and sky; this is not its final rejection mask',
              'candidate_positions_reproduced': True, 'candidates': actual,
              'images_sha256': image_digest, 'raw_sha256': result['raw_sha256'],
              'sidecar': str(sidecar), 'sidecar_sha256': sha256(sidecar),
              'sky_input_fraction': float(selection['sky_input_mask'].mean()),
              'input_files_unchanged': True}
    sidecar.with_suffix('.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--target')
    args = parser.parse_args()
    manifest = json.loads((args.run/'run.json').read_text())
    results = [r for r in manifest['results'] if not args.target or r['object'] == args.target]
    if not results:
        parser.error('no matching exposures')
    print(json.dumps([recover_sky_selection(r, args.run) for r in results], indent=2))


if __name__ == '__main__':
    main()
