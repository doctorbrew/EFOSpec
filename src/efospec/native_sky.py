"""Independent sky-line validation of a native arc wavelength solution."""
import numpy as np
from scipy.optimize import curve_fit
from .sky_quality import line_quality, line_failure_message


class SkyValidationError(ValueError):
    code='wavelength_validation_failed'

    def __init__(self,message,lines):
        super().__init__(message)
        self.diagnostics={'lines':lines,'held_out_6363_pass':False}


def exposure_flexure(data, waveair, *, required, **options):
    """Try the same sky check on standards; only measured success permits a shift.

    Insufficient standard sky retains the arc grid and the actual failed check.
    Unexpected errors propagate. Sky validation does not measure point-source
    miscentring across the slit or a stellar radial velocity.
    """
    try:
        shift, record = measure_flexure(data, waveair, **options)
    except SkyValidationError as exc:
        if required:
            raise
        return 0., dict(exc.diagnostics, status='unvalidated', shift_angstrom=0.,
            applied_shift_angstrom=None, validation_error=str(exc),
            policy='raw_arc_only; standard sky check attempted and failed')
    return shift, dict(record, status='validated_sky', applied_shift_angstrom=shift)


def measure_flexure(data,waveair, *, slit_width_pixels=None, good_pixels=None):
    """Two offset anchors, then a genuinely isolated 6363-A validation window."""
    data,waveair=np.asarray(data,float),np.asarray(waveair,float)
    if data.ndim!=2 or data.shape!=waveair.shape or data.shape[1]<40:
        raise ValueError('sky validation requires a two-dimensional long-slit window')
    if good_pixels is not None:
        if np.shape(good_pixels)!=data.shape:raise ValueError('sky mask must match the calibrated pixels')
        data=np.where(good_pixels,data,np.nan)
    wave=waveair[:,waveair.shape[1]//2]
    if not np.all(np.diff(waveair,axis=0)>0):raise ValueError('sky wavelength map must increase')
    columns=np.arange(10,data.shape[1]-10)
    samples=np.array([np.interp(wave,waveair[:,col],data[:,col]) for col in columns])
    # Use every spatial sample and reject source/CR contamination before
    # averaging. Subsampling one column in three discarded measurable sky S/N.
    from astropy.stats import sigma_clip
    clipped=sigma_clip(samples,sigma=3.,maxiters=5,axis=0,cenfunc='median',stdfunc='mad_std')
    sky=np.asarray(np.ma.mean(clipped,axis=0).filled(np.nan))
    sky[np.ma.count(clipped,axis=0)<20]=np.nan
    def gaussian(w,a,center,sigma,b,slope):
        return a*np.exp(-.5*((w-center)/sigma)**2)+b+slope*(w-center)
    if slit_width_pixels is not None and (not np.isfinite(slit_width_pixels) or slit_width_pixels<=0):
        raise ValueError('projected slit width must be positive detector pixels')
    lines=[];shift=0.
    for rest in (5577.338,6300.304,6363.776):
        expected=rest-shift
        dispersion=float(np.median(np.diff(wave)))
        projected_width = float(slit_width_pixels*dispersion) if slit_width_pixels is not None else None
        # A resolved, slit-filled 6363 line needs continuum on both sides of
        # its projected profile. The old 28-A window left five free parameters
        # constrained by only nine samples for a 35-A projected slit.
        half_window=(min(48.,max(28.,projected_width/2+4*dispersion))
                     if projected_width is not None and rest==6363.776 else
                     (45. if slit_width_pixels is not None else 28.))
        neighbour_guard=((6300.304+6363.776)/2-shift
                         if rest==6363.776 else -np.inf)
        keep=(abs(wave-expected)<half_window)&(wave>neighbour_guard)&np.isfinite(sky)
        w,f=wave[keep],sky[keep]
        if len(w)<9:raise SkyValidationError(f'insufficient spectral coverage for sky line {rest:g}',lines)
        base=float(np.median(np.r_[f[:2],f[-2:]]))
        if projected_width is not None:
            from scipy.special import erf
            def profile(w,a,center,sigma,b,slope):
                return a*.5*(erf((w-center+projected_width/2)/(np.sqrt(2)*sigma))
                             -erf((w-center-projected_width/2)/(np.sqrt(2)*sigma)))+b+slope*(w-center)
            sigma_min,sigma_guess=.5,3.
        else:
            profile=gaussian; sigma_min,sigma_guess=3.,7.5
        guess=[max(float(f.max()-base),1.),float(np.clip(w[f.argmax()],expected-19,expected+19)),sigma_guess,base,0.]
        try:
            p,cov=curve_fit(profile,w,f,p0=guess,bounds=([0,expected-20,sigma_min,-np.inf,-np.inf],
                    [np.inf,expected+20,14,np.inf,np.inf]),maxfev=10000)
        except (RuntimeError,ValueError) as exc:
            raise SkyValidationError(f'cannot fit isolated sky line {rest:g}',lines) from exc
        residual=f-profile(w,*p)
        noise=max(1.4826*np.median(abs(residual-np.median(residual))),1e-6)
        snr=float(p[0]/noise);error=float(np.sqrt(max(cov[1,1],0)))
        formal=np.sqrt(np.maximum(np.diag(cov),0.))
        centroid_slope_correlation=(float(cov[1,4]/(formal[1]*formal[4]))
                                    if formal[1]>0 and formal[4]>0 else None)
        lines.append(dict(rest_air_angstrom=rest,measured_air_angstrom=float(p[1]),
            offset_angstrom=float(rest-p[1]),peak_snr=snr,sigma_angstrom=float(p[2]),
            centroid_error_angstrom=error if np.isfinite(error) else None,
            amplitude_formal_error_electron=float(formal[0]) if np.isfinite(formal[0]) else None,
            centroid_slope_correlation=centroid_slope_correlation,
            profile='uniform_slit_convolved_gaussian' if projected_width is not None else 'gaussian',
            projected_slit_width_angstrom=projected_width, fit_half_window_angstrom=half_window,
            neighbour_guard_air_angstrom=neighbour_guard if np.isfinite(neighbour_guard) else None,
            fit_samples={'wave_air':w.tolist(),'sky_electron':f.tolist(),'model_electron':profile(w,*p).tolist()}))
        lines[-1]['quality'] = line_quality(lines[-1])
        failure = line_failure_message(lines[-1])
        if failure:
            raise SkyValidationError(failure,lines)
        if rest==6300.304:
            if abs(lines[0]['offset_angstrom']-lines[1]['offset_angstrom'])>3:
                raise SkyValidationError('native sky anchors disagree by more than 3 A',lines)
            shift=float(np.mean([line['offset_angstrom'] for line in lines]))
            if abs(shift)>20:raise SkyValidationError('native sky shift exceeds 20 A',lines)
    for line in lines:line['residual_after_shift_angstrom']=line['measured_air_angstrom']+shift-line['rest_air_angstrom']
    residual=lines[2]['residual_after_shift_angstrom']
    if abs(residual)>3:raise SkyValidationError(f'independent 6363-A residual is {residual:.2f} A',lines)
    return shift,dict(shift_angstrom=shift,lines=lines,held_out_6363_residual_angstrom=residual,
                      held_out_6363_pass=True,policy='isolated 5577/6300 fits and held-out 6363 validation',
                      spatial_estimator='3-sigma clipped mean of all interior columns',
                      spatial_samples=int(len(columns)))
