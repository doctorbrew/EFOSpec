"""Shared PypeIt extraction for automatic reductions and saved manual recipes."""
import numpy as np
from astropy import units as u


class SourceSelectionError(ValueError):
    """Keep detected positions available when target identity is unresolved."""
    code = 'source_selection_required'
    action = 'Verify the target against acquisition data and supply an explicit extraction recipe.'

    def __init__(self, message, found, target_position):
        super().__init__(message)
        self.diagnostics = {'expected_spatial_pixel': target_position,
            'coordinate_system': 'zero_based_extraction_window',
            'candidates': [{'name': str(s.NAME), 'spatial_pixel': float(s.SPAT_PIXPOS)} for s in found],
            'review_recommendation': {'workflow':'aperture_and_background_review',
                'reason':'Multiple or unassociated traces may include field sources or host structure.',
                'suggested_background':'two_sided_polynomial_preview',
                'host_contamination_confirmed':False,'automatic_subtraction':False}}


def select_sources(found, target_position=None, manual=None):
    """Map stable recipe IDs to found objects without silently swapping sources."""
    if len(found) == 0:
        raise SourceSelectionError('no source detected in target window', found, target_position)
    if manual is None:
        if target_position is None or not np.isfinite(target_position):
            raise ValueError('automatic selection requires a finite target position')
        distance = np.array([abs(s.SPAT_PIXPOS-target_position) for s in found])
        order = np.argsort(distance)
        if distance[order[0]] > 15 or (len(order) > 1 and distance[order[1]] < 15):
            raise SourceSelectionError(f'absent or ambiguous source at expected position {target_position}',
                                       found, target_position)
        return {'primary': str(found[order[0]].NAME)}
    selected = {}
    for obj in manual:
        matches = [s for s in found if s.hand_extract_flag
                   and abs(s.hand_extract_spat-obj['spat']) < 1e-6
                   and abs(s.hand_extract_spec-obj['spec']) < 1e-6]
        if len(matches) != 1:
            raise ValueError(f'manual source {obj["id"]} was not found uniquely')
        selected[obj['id']] = str(matches[0].NAME)
    if len(set(selected.values())) != len(manual):
        raise ValueError('manual sources do not have distinct extraction identities')
    return selected


def extract_spectra(data, waveair, detector, *, exposure_time, read_noise,
                    output, basename, target_position=None, manual=None, sky_input_mask=None, processed=None):
    """Jointly model neighbouring objects and return requested spectra and images.

    Data and read noise are electrons. Coordinates, manual FWHM and boxcar
    radii are pixels in this image, after binning. Air wavelengths are Angstroms.
    A supplied sky mask controls the global fit, held during optimal extraction.
    PypeIt diagnostics are written below output; callers own product delivery.
    """
    import pypeit
    from pypeit.images.pypeitimage import PypeItImage
    from pypeit.slittrace import SlitTraceSet
    from pypeit.find_objects import FindObjects
    from pypeit.extraction import Extract
    from pypeit.manual_extract import ManualExtractionObj
    from pypeit.core.wave import airtovac
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
    from .sky_regions import capture_sky_selection

    if pypeit.__version__ != '1.14.0':
        raise ValueError('extraction is validated only with PypeIt 1.14.0')
    data, waveair = np.asarray(data, dtype=float), np.asarray(waveair, dtype=float)
    if (data.ndim != 2 or data.shape != waveair.shape or min(data.shape) < 3
            or not np.isfinite(waveair).all() or np.any(waveair <= 0)
            or not np.all(np.diff(waveair, axis=0) > 0)):
        raise ValueError('science image and increasing wavelength map must have matching 2D geometry')
    if not np.isfinite([exposure_time, read_noise]).all() or exposure_time <= 0 or read_noise <= 0:
        raise ValueError('exposure time and read noise must be positive and finite')
    if sky_input_mask is not None:
        sky_input_mask = np.asarray(sky_input_mask, dtype=bool)
        if sky_input_mask.shape != data.shape or np.any(sky_input_mask.sum(axis=1) < 8):
            raise ValueError('sky mask must match the image and retain eight pixels per row')
    inst = EFOSpecEFOSC2Spectrograph()
    par = inst.profile_parameters('rapid')
    par['flexure']['spec_method'] = 'skip'
    par['reduce']['findobj']['maxnumber_sci'] = 3
    par['reduce']['findobj']['snr_thresh'] = 5
    par['reduce']['findobj']['skip_second_find'] = True
    par['reduce']['skysub']['bspline_spacing'] = 1.0
    par['rdx']['redux_path'] = str(output)
    if sky_input_mask is not None:
        par['reduce']['skysub']['no_local_sky'] = True
    ny, nx = data.shape
    tilts = (waveair-waveair.min())/(waveair.max()-waveair.min())
    rn = np.full(data.shape, float(read_noise)**2)
    if processed is None:
        sci = PypeItImage(data, ivar=1/(np.maximum(data, 0)+rn), rn2img=rn, base_var=rn,
                         detector=detector, exptime=exposure_time, noise_floor=0., shot_noise=True,
                         bpm=~np.isfinite(data))
    else:
        required = {'ivar', 'rn2img', 'base_var', 'img_scale', 'bad_pixels'}
        if set(processed) != required or any(np.shape(processed[k]) != data.shape for k in required):
            raise ValueError('processed variance and mask planes must match the image')
        if any(np.any(~np.isfinite(processed[k])) or np.any(processed[k] < 0)
               for k in required - {'bad_pixels'}):
            raise ValueError('processed variance planes must be finite and nonnegative')
        sci = PypeItImage(data, ivar=processed['ivar'], rn2img=processed['rn2img'],
                         base_var=processed['base_var'], img_scale=processed['img_scale'],
                         bpm=processed['bad_pixels'], detector=detector, exptime=exposure_time,
                         noise_floor=0., shot_noise=True)
    gain = float(detector['gain'][0])
    sci.build_mask(saturation=detector['saturation']*gain, mincounts=-1e10)
    slits = SlitTraceSet(np.zeros(ny), np.full(ny, nx-1.), 'MultiSlit',
                        detname='DET01', nspat=nx, PYP_SPEC=inst.name, binspec=2, binspat=2)
    instruction = None
    if manual is not None:
        if not manual:
            raise ValueError('manual extraction needs at least one source')
        instruction = ManualExtractionObj(
            frame=basename, spec=np.array([o['spec'] for o in manual], dtype=float),
            spat=np.array([o['spat'] for o in manual], dtype=float),
            fwhm=np.array([o['fwhm'] for o in manual], dtype=float),
            boxcar_rad=np.array([o['radius'] for o in manual], dtype=float),
            detname=np.array(['DET01']*len(manual)), neg=np.zeros(len(manual), dtype=bool))
    finder = FindObjects.get_instance(sci, slits, inst, par, 'science', tilts=tilts,
                                     show=False, basename=basename, manual=instruction,
                                     initial_skymask=sky_input_mask)
    sky, found = finder.run()
    selection = capture_sky_selection(finder, found)
    try:
        names = select_sources(found, target_position, manual)
    except SourceSelectionError as exc:
        from pathlib import Path
        from tempfile import NamedTemporaryFile
        directory = Path(output)/'native'
        directory.mkdir(parents=True, exist_ok=True)
        # Repeated failed exposures do not reserve a successful product name.
        # Allocate a distinct diagnostic even when their legacy stems coincide.
        with NamedTemporaryFile(dir=directory, prefix=basename+'_selection_failed_',
                                suffix='.npz', delete=False) as stream:
            np.savez_compressed(stream, data=data, waveair=waveair, sky=sky, **selection)
            diagnostic = Path(stream.name)
        exc.diagnostics['diagnostic_file'] = str(diagnostic.resolve())
        raise
    extractor = Extract.get_instance(sci, slits, found, inst, par, 'science', global_sky=sky,
                                     tilts=tilts, waveimg=airtovac(waveair*u.AA).value,
                                     show=False, basename=basename)
    arrays = extractor.run()
    extracted = arrays[4]
    objects = {}
    for identity, name in names.items():
        selected = np.array([i for i, obj in enumerate(extracted) if obj.NAME == name])
        if len(selected) != 1:
            raise ValueError(f'target {identity} lost during extraction')
        objects[identity] = extracted[selected]
    return {'objects': objects, 'found': found, 'arrays': arrays, 'selection': selection,
            'sky_policy': 'selected_global_sky' if sky_input_mask is not None else 'automatic_global_and_local'}
