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
    from astropy import units as u
    return (vactoair(spectrum.wave*u.AA).value, spectrum.flux.copy(),
            float(fwhm), 'PypeIt/paranal_sky.fits')


def _bspline_correlation(observed, reference, template_fwhm, fwhm_pixels, max_pixels):
    """Retain the existing diagnostic's B-spline continuum with PypeIt 3 APIs.

    This is EFOSpec preprocessing, not PypeIt 3's native percentile-clipped
    algorithm. Both paths are explicit; neither authorizes a correction.
    """
    from pypeit.core import flexure, fitting
    smooth=flexure.get_fwhm_gauss_smooth(reference,observed,template_fwhm,
                                       spec_fwhm_pix=fwhm_pixels)
    if smooth is None:raise ValueError('cannot match sky resolution')
    reference=reference.gauss_smooth(smooth) if smooth>0 else reference
    reference=reference.rebin(observed.wave)
    observed=observed.rebin(observed.wave)
    residuals=[]
    for spectrum in (reference,observed):
        spectrum.flux[:2]=0.;spectrum.flux[-2:]=0.
        spectrum.flux=np.maximum(spectrum.flux,0.)
        mean=float(np.mean(spectrum.flux))
        if mean<=0:raise ValueError('nonpositive sky normalization')
        spectrum.flux=spectrum.flux/mean
        _,_,continuum,_,status=fitting.iterative_bspline_fit(
            spectrum.wave,spectrum.flux,nord=3,maxiter=15,upper=3.,lower=3.,
            kwargs_knots={'stride':max(1,spectrum.npix//20)},
            kwargs_reject={'groupbadpix':True,'maxrej':1})
        if status!=0:raise ValueError(f'sky continuum did not converge (status {status})')
        residuals.append(spectrum.flux-continuum)
    corr=np.correlate(*residuals,'same');center=len(corr)//2
    peak=np.argmax(corr[center-max_pixels:center+max_pixels])+center-max_pixels
    points=np.arange(peak-3,peak+4)
    if points.min()<0 or points.max()>=len(corr):raise ValueError('correlation peak at array edge')
    fit=fitting.PypeItFit(xval=points.astype(float),yval=corr[points],
                         func='polynomial',order=np.array([2]));fit.fit()
    return dict(shift=float(-.5*fit.fitc[1]/fit.fitc[2]-center),polyfit=fit,
        subpix=points,corr_cen=center,corr=corr[points],sky_spec=observed,
        arx_spec=reference,smooth=smooth)


def correlate_sky(waveair, sky, *, template=None, fwhm_angstrom=None, wavelength_range=(5300.,6500.),
                  continuum_method='bspline'):
    """Compare against PypeIt's physical sky template without altering data.

The comparison covers 5300--6500 air A to include the optical anchors while
avoiding unvalidated red fringe/second-order regions. PypeIt measures a pixel
shift on a uniform vacuum grid; convert its corrected grid back to air before
reporting an additive offset. Preserve the distinction between these models.
"""
    import pypeit
    from astropy import units as u
    from pypeit.onespec import OneSpec
    from pypeit.core import flexure
    from pypeit.core.wave import airtovac, vactoair
    if pypeit.__version__ != '3.0.0':
        raise ValueError('sky correlation adapter requires PypeIt 3.0.0')
    waveair, sky = np.asarray(waveair, float), np.asarray(sky, float)
    if (waveair.ndim != 1 or sky.shape != waveair.shape or
            not np.isfinite(waveair).all() or not np.all(np.diff(waveair) > 0)):
        raise ValueError('sky comparison requires an increasing wavelength vector')
    keep=(waveair>=wavelength_range[0])&(waveair<=wavelength_range[1])&np.isfinite(sky)
    if keep.sum()<60 or np.any(np.diff(np.flatnonzero(keep))!=1):
        raise ValueError('insufficient contiguous sky coverage in the requested wavelength band')
    tw, tf, template_fwhm, name = sky_template() if template is None else template
    vacuum=airtovac(waveair[keep]*u.AA).value
    grid=np.linspace(vacuum[0],vacuum[-1],len(vacuum))
    flux=np.interp(grid,vacuum,sky[keep])
    if np.ptp(flux)<=0:raise ValueError('featureless sky spectrum')
    observed=OneSpec(grid,None,flux,fluxed=False)
    reference=OneSpec(airtovac(np.asarray(tw)*u.AA).value,None,np.asarray(tf).copy(),fluxed=False)
    step=float(np.median(np.diff(grid)))
    max_pixels=min(int(np.ceil(80./step)),len(grid)//2-5)
    fwhm_pixels=None if fwhm_angstrom is None else fwhm_angstrom/step
    if continuum_method=='bspline':
        measured=_bspline_correlation(observed,reference,template_fwhm,fwhm_pixels,max_pixels)
        method='EFOSpec.bspline_correlation_with_PypeIt3'
    elif continuum_method=='native':
        measured=flexure.spec_flex_shift(observed,arx_skyspec=reference,arx_fwhm_pix=template_fwhm,
            spec_fwhm_pix=fwhm_pixels,mxshft=max_pixels,excess_shft='crash',method='slitcen')
        method='PypeIt.spec_flex_shift'
    else:raise ValueError('continuum_method must be bspline or native')
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
        'max_shift_pixels':max_pixels,'method':method,'continuum_method':continuum_method,
        'template_fwhm_pixels':float(template_fwhm),'observed_fwhm_angstrom':fwhm_angstrom,
        'smoothing_fwhm_pixels':float(measured['smooth']),
        'limitation':'Same sky data as the line fits; not independent validation or an accepted correction.'}
    arrays={'correlation_lags':measured['subpix']-measured['corr_cen'],
        'correlation_values':measured['corr'],
        'correlation_wavevac':measured['sky_spec'].wave,
        'correlation_sky':measured['sky_spec'].flux,
        'correlation_template':measured['arx_spec'].flux}
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
    # Disjoint wavelength intervals test whether a single offset even describes
    # this exposure. They do not establish line identities, peak significance or
    # an absolute wavelength acceptance, and never authorize a correction.
    bands = []
    for i, limits in enumerate(((6500., 7450.), (7650., 8500.))):
        try:
            band, extra = correlate_sky(wave, sky, wavelength_range=limits)
            arrays.update({f'band_{i}_{key}': value for key, value in extra.items()})
        except Exception as exc:
            band = dict(status='unavailable', applied=False, error=str(exc))
        bands.append(dict(band, requested_range_air_angstrom=list(limits)))
    measured = all(b.get('status') == 'measured' and np.isfinite(b.get('shift_angstrom', np.nan)) for b in bands)
    difference = abs(bands[0]['shift_angstrom']-bands[1]['shift_angstrom']) if measured else None
    consistency = dict(status=('consistent' if difference <= 3. else 'inconsistent') if measured else 'unavailable',
        bands=bands, difference_angstrom=difference, maximum_difference_angstrom=3.,
        applied=False, limitation='Disjoint-band consistency only; independent red-feature identification and uncertainty validation remain required.')
    np.savez_compressed(directory/'curves.npz',**arrays)
    record={'schema_version':1,'status':'unvalidated','metadata':metadata,
        'line_check':{'lines':[],'failed_gates':['red_sky_validation_required']},
        'correlation':comparison,'band_consistency':consistency,'applied_shift_angstrom':None,
        'curves_sha256':sha256(directory/'curves.npz'),'wavelength_medium':'air',
        'wavelength_unit':'Angstrom','spectral_reference_frame':'topocentric'}
    (directory/'check.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    return record
