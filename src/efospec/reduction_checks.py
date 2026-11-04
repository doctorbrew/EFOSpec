"""Automatic, replayable wavelength and setup evidence for every reduction.

PypeIt template correlation is a diagnostic, not permission to bypass a failed
line check. Only the existing accepted line correction is applied upstream of
extraction. Wavelengths at this interface are topocentric air Angstroms.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np

from .archive_calibration import SkyFlexureError, sky_flexure
from .inventory import sha256


@lru_cache(maxsize=1)
def sky_template():
    from pypeit.core.flexure import get_archive_spectrum
    from pypeit.core.wave import vactoair
    spectrum, fwhm = get_archive_spectrum('paranal_sky.fits')
    return (vactoair(spectrum.wavelength).value, spectrum.flux.value.copy(),
            float(fwhm), 'PypeIt/paranal_sky.fits')


def correlate_sky(waveair, sky, *, template=None, fwhm_angstrom=None, wavelength_range=(5300.,6500.)):
    """Compare against PypeIt's physical sky template without altering data.

The comparison covers 5300--6500 air A to include the optical anchors while
avoiding unvalidated red fringe/second-order regions. PypeIt measures a pixel
shift on a uniform vacuum grid; convert its corrected grid back to air before
reporting an additive offset. Preserve the distinction between these models.
"""
    import pypeit
    from astropy import units as u
    from linetools.spectra.xspectrum1d import XSpectrum1D
    from pypeit.core import flexure
    from pypeit.core.wave import airtovac, vactoair
    if pypeit.__version__ != '1.14.0':
        raise ValueError('sky correlation adapter requires PypeIt 1.14.0')
    waveair, sky = np.asarray(waveair, float), np.asarray(sky, float)
    if (waveair.ndim != 1 or sky.shape != waveair.shape or
            not np.isfinite(waveair).all() or not np.all(np.diff(waveair) > 0)):
        raise ValueError('sky comparison requires an increasing wavelength vector')
    keep=(waveair>=wavelength_range[0])&(waveair<=wavelength_range[1])&np.isfinite(sky)
    if keep.sum()<60 or np.any(np.diff(np.flatnonzero(keep))!=1):
        raise ValueError('insufficient contiguous optical sky coverage')
    tw, tf, template_fwhm, name = sky_template() if template is None else template
    vacuum=airtovac(waveair[keep]*u.AA).value
    grid=np.linspace(vacuum[0],vacuum[-1],len(vacuum))
    flux=np.interp(grid,vacuum,sky[keep])
    if np.ptp(flux)<=0:raise ValueError('featureless sky spectrum')
    observed=XSpectrum1D.from_tuple((grid,flux))
    reference=XSpectrum1D.from_tuple((airtovac(np.asarray(tw)*u.AA).value,np.asarray(tf)))
    step=float(np.median(np.diff(grid)))
    max_pixels=min(int(np.ceil(80./step)),len(grid)//2-5)
    measured=flexure.spec_flex_shift(observed,reference,template_fwhm,
        spec_fwhm_pix=None if fwhm_angstrom is None else fwhm_angstrom/step,
        mxshft=max_pixels,excess_shft='crash',method='slitcen')
    if measured is None:raise ValueError('PypeIt could not measure a sky correlation')
    pixels=float(measured['shift'])
    if not np.isfinite(pixels) or abs(pixels)>=max_pixels-1:
        raise ValueError('correlation peak is nonfinite or reaches the search boundary')
    if measured['polyfit'].fitc[2]>=0:
        raise ValueError('correlation fit does not have a maximum')
    shifted=flexure.flexure_interp(pixels,grid)
    offsets=vactoair(shifted*u.AA).value-vactoair(grid*u.AA).value
    digest=hashlib.sha256(np.asarray([tw,tf],dtype='<f8').tobytes()).hexdigest()
    record={'status':'measured','applied':False,'pypeit_version':pypeit.__version__,
        'template':name,'template_arrays_sha256':digest,'shift_pixels':pixels,
        'shift_angstrom':float(np.median(offsets)),
        'offset_range_air_angstrom':[float(offsets.min()),float(offsets.max())],
        'range_air_angstrom':[float(waveair[keep][0]),float(waveair[keep][-1])],
        'max_shift_pixels':max_pixels,'method':'PypeIt.spec_flex_shift',
        'template_fwhm_pixels':float(template_fwhm),'observed_fwhm_angstrom':fwhm_angstrom,
        'smoothing_fwhm_pixels':float(measured['smooth']),
        'limitation':'Same sky data as the line fits; not independent validation or an accepted correction.'}
    arrays={'correlation_lags':measured['subpix']-measured['corr_cen'],
        'correlation_values':measured['corr'],
        'correlation_wavevac':measured['sky_spec'].wavelength.value,
        'correlation_sky':measured['sky_spec'].flux.value,
        'correlation_template':measured['arx_spec'].flux.value}
    return record,arrays


def check_flexure(data, waveair, directory, metadata):
    """Persist both passing and failed checks before returning or re-raising."""
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=False)
    arrays={}; failure=None; shift=None
    try:
        shift,qa=sky_flexure(data,waveair,diagnostic_arrays=arrays)
    except SkyFlexureError as exc:
        failure=exc;qa=exc.diagnostics
    try:
        widths=[2.35482*m['sigma_angstrom'] for m in qa['lines'] if m['fit_valid']]
        correlation,extra=correlate_sky(arrays['waveair'],arrays['sky'],
            fwhm_angstrom=float(np.median(widths)) if widths else None)
        arrays.update(extra)
        if shift is not None:
            correlation['difference_from_line_shift_angstrom']=correlation['shift_angstrom']-shift
            correlation['agrees_with_line_shift']=abs(correlation['shift_angstrom']-shift)<=3.
    except Exception as exc:
        correlation={'status':'unavailable','applied':False,'error':str(exc),
                     'exception_type':type(exc).__name__}
    np.savez_compressed(directory/'curves.npz',**arrays)
    qa['review_file']=str(directory/'check.json')
    record={'schema_version':1,'status':'failed' if failure else 'passed',
        'metadata':metadata,'line_check':qa,'correlation':correlation,
        'applied_shift_angstrom':shift,'curves_sha256':sha256(directory/'curves.npz'),
        'coordinate_system':'zero_based_trimmed_image','wavelength_medium':'air',
        'wavelength_unit':'Angstrom','spectral_reference_frame':'topocentric'}
    (directory/'check.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    if failure:raise failure
    return shift,qa


def setup_checks(inventory, output):
    """Record real candidate associations separately from scientific support."""
    from .native_readiness import assess_native_readiness
    report=assess_native_readiness(inventory)
    report['methodology']='Raw-calibration preflight; availability is not acceptance. Archive and native routes remain explicit.'
    path=Path(output)/'setup-checks.json'
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return {e['path']:e for e in report['exposures']}


def check_red_sky(data, waveair, directory, metadata):
    """Save Gr16 correlation evidence without inventing a validated red-line gate."""
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=False)
    wave=waveair[:,waveair.shape[1]//2]
    columns=np.arange(20,data.shape[1]-20,5)
    sky=np.nanmedian([np.interp(wave,waveair[:,i],data[:,i]) for i in columns],axis=0)
    arrays={'waveair':wave,'sky':sky,'spatial_columns':columns}
    try:
        comparison,extra=correlate_sky(wave,sky,wavelength_range=(6500.,8500.))
        arrays.update(extra)
    except Exception as exc:
        comparison={'status':'unavailable','applied':False,'error':str(exc)}
    np.savez_compressed(directory/'curves.npz',**arrays)
    record={'schema_version':1,'status':'unvalidated','metadata':metadata,
        'line_check':{'lines':[],'failed_gates':['red_sky_validation_required']},
        'correlation':comparison,'applied_shift_angstrom':None,
        'curves_sha256':sha256(directory/'curves.npz'),'wavelength_medium':'air',
        'wavelength_unit':'Angstrom','spectral_reference_frame':'topocentric'}
    (directory/'check.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    return record
