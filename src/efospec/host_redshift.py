"""Independent, provisional narrow-emission-line redshifts from saved 2D data.

NED values never enter the spectral search. A detected line system is not by
itself a confirmed transient host. No wavelength calibration is changed here.
"""
import numpy as np
from scipy.ndimage import median_filter, gaussian_filter1d
from scipy.signal import find_peaks
from scipy.optimize import least_squares

# Vacuum Angstroms, SDSS spectral-line table. Components in a blend are fitted
# together; the OII and SII doublets each count as ONE independent line group.
LINE_SOURCE='https://classic.sdss.org/dr7/algorithms/linestable.php'
GROUPS={
    'OII':([3727.092,3729.875],[0,1],[1.,1.]),
    'Hgamma':([4341.68],[0],[1.]),
    'Hbeta':([4862.68],[0],[1.]),
    'OIII':([4960.295,5008.240],[0,1],[1.,1.]),
    'Halpha_NII':([6549.86,6564.61,6585.27],[0,1,2],[1.,1.,1.]),
    'SII':([6718.29,6732.67],[0,1],[1.,1.]),
}
ANCHORS={'OII':3728.5,'Hgamma':4341.68,'Hbeta':4862.68,'OIII':5008.240,'Halpha_NII':6564.61,'SII':6724.}


def extract_2d_line_spectrum(arrays, *, radius=20.):
    """Rectify diagnostic counts, remove spatially common sky, sum near trace.

    Use pre-background image data so that a local host-background subtraction
    cannot erase the lines being sought. All interpolation weights enter the
    diagonal variance. Covariance and background-model systematics are not a
    calibrated redshift error and are stated separately by the caller.
    """
    from astropy import units as u
    from pypeit.core.wave import airtovac
    data=np.asarray(arrays['data'],float);ivar=np.asarray(arrays['ivar'],float)
    wave=airtovac(np.asarray(arrays['waveair'])*u.AA).value
    trace=np.asarray(arrays['trace']);ny,nx=data.shape;x=np.arange(nx)
    grid=np.array([np.interp(t,x,w) for t,w in zip(trace,wave)])
    good=(np.asarray(arrays['mask'])==0)&np.isfinite(data)&(ivar>0)
    variance=np.divide(1.,ivar,out=np.full_like(data,np.nan),where=ivar>0)
    image=np.full_like(data,np.nan);var=np.full_like(data,np.nan)
    for col in range(nx):
        upper=np.clip(np.searchsorted(wave[:,col],grid),1,ny-1);lower=upper-1
        fraction=(grid-wave[lower,col])/(wave[upper,col]-wave[lower,col])
        use=good[lower,col]&good[upper,col]&(fraction>=0)&(fraction<=1)
        image[use,col]=((1-fraction)*data[lower,col]+fraction*data[upper,col])[use]
        var[use,col]=((1-fraction)**2*variance[lower,col]+fraction**2*variance[upper,col])[use]
    off=(abs(x[None,:]-trace[:,None])>40)&(x>5)&(x<nx-6)
    sky=np.nanmedian(np.where(off,image,np.nan),axis=1)
    nsky=np.sum(off&np.isfinite(image),axis=1)
    sky_var=1.2533**2*np.nanmedian(np.where(off,var,np.nan),axis=1)/np.maximum(nsky,1)
    residual=image-sky[:,None]
    aperture=(abs(x[None,:]-trace[:,None])<=radius)&np.isfinite(residual)&np.isfinite(var)
    n=aperture.sum(axis=1)
    flux=np.where(aperture,residual,0).sum(axis=1)
    error=np.sqrt(np.where(aperture,var,0).sum(axis=1)+n**2*sky_var)
    valid=(n>=radius)&(nsky>=20)&np.isfinite(error)&(error>0)
    flux[~valid]=np.nan;error[~valid]=np.nan
    return dict(wave_vacuum=grid,counts=flux,sigma=error,rectified_sky_subtracted=residual,
                rectified_variance=var,trace=trace,spatial_pixel=x+int(arrays['spatial_origin']),
                valid=valid,aperture_radius_pixels=radius,sky=sky)


def fit_group(wave,flux,error,z0,name,fwhm):
    rest,indices,weights=GROUPS[name];rest=np.array(rest);indices=np.array(indices)
    centres=rest*(1+z0);window=max(45.,2*fwhm)
    keep=(wave>centres.min()-window)&(wave<centres.max()+window)&np.isfinite(flux)&np.isfinite(error)&(error>0)
    if keep.sum()<12 or centres.min()-window<wave.min() or centres.max()+window>wave.max():return None
    w,y,e=wave[keep],flux[keep],error[keep];scale=max(float(np.median(e)),1e-12);y=y/scale;e=e/scale
    n=indices.max()+1;mid=np.mean(centres);xx=(w-mid)/window
    initial=np.polyfit(xx,y,1);continuum=initial[1]+initial[0]*xx
    amp=max(float(np.max(y-continuum)),1.)
    initial=np.r_[z0,fwhm/2.355,np.full(n,amp/n),initial[::-1]]
    def model(p):
        gaussian=np.exp(-.5*((w[:,None]-rest[None,:]*(1+p[0]))/p[1])**2)
        return gaussian@(p[2:2+n][indices]*weights)+p[-2]+p[-1]*xx
    lower=np.r_[z0-.002,max(np.median(np.diff(w)),fwhm/6),np.zeros(n),[-np.inf,-np.inf]]
    upper=np.r_[z0+.002,fwhm/1.5,np.full(n,np.inf),[np.inf,np.inf]]
    fit=least_squares(lambda p:(model(p)-y)/e,initial,bounds=(lower,upper),max_nfev=200)
    dof=len(y)-len(initial)
    if not fit.success or dof<3:return None
    chi2=float(np.sum(fit.fun**2)/dof)
    cov=np.linalg.pinv(fit.jac.T@fit.jac)*max(1.,chi2)
    errors=np.sqrt(np.maximum(np.diag(cov),0));zerr=float(errors[0])
    snrs=np.divide(fit.x[2:2+n],errors[2:2+n],out=np.zeros(n),where=errors[2:2+n]>0)
    width_bound=fit.x[1]>.98*upper[1] or fit.x[1]<1.02*lower[1]
    null=np.column_stack([np.ones(len(xx)),xx])/e[:,None]
    coeff=np.linalg.lstsq(null,y/e,rcond=None)[0]
    improvement=float(np.sum((null@coeff-y/e)**2)-np.sum(fit.fun**2))
    centre_error=zerr*float(np.mean(rest))
    # A masked line core cannot be identified from a fitted wing alone.
    strongest=int(np.argmax(snrs));component=np.flatnonzero(indices==strongest)[0]
    centre=rest[component]*(1+fit.x[0]);half_width=fwhm/2
    core=(wave>=centre-half_width)&(wave<=centre+half_width)
    coverage=float(np.sum(core&np.isfinite(flux)&np.isfinite(error)&(error>0))/max(1,np.sum(core)))
    # At low resolution, unknown doublet/blend ratios can trade against z.
    # Boundary-constrained covariance is optimistic; retain a conservative
    # half-blend-span floor when the closest components are unresolved.
    blend_floor=(float(np.ptp(rest)/(2*np.mean(rest))) if len(rest)>1 and
                 np.min(np.diff(rest))*(1+fit.x[0])<fwhm else 0.)
    detected=(np.max(snrs)>=5 and improvement>=30 and not width_bound and centre_error<fwhm/3
              and abs(fit.x[0]-z0)<.00195 and coverage>=.75)
    return dict(group=name,z=float(fit.x[0]),z_stat_error=zerr,snr=float(np.max(snrs)),
        z_weight_error=max(zerr,blend_floor),blend_centroid_floor=blend_floor,core_coverage=coverage,
        component_snr=snrs.tolist(),fwhm_angstrom=float(2.355*fit.x[1]),chi2_reduced=chi2,
        delta_chi2=improvement,detected=bool(detected),width_bound=bool(width_bound),
        rest_vacuum_angstrom=rest.tolist(),observed_vacuum_angstrom=(rest*(1+fit.x[0])).tolist(),
        wave=w.tolist(),counts=(y*scale).tolist(),sigma=(e*scale).tolist(),model=(model(fit.x)*scale).tolist())


def measure_redshift(wave,flux,error,*,fwhm,zmin=-.003,zmax=1.):
    """Blind search; require >=3 consistent independent emission-line groups.

    Thresholds are conservative candidate gates, not calibrated confidence
    probabilities. Alternative line identifications are retained and checked.
    """
    wave,flux,error=[np.asarray(v,float) for v in (wave,flux,error)]
    if wave.shape!=flux.shape or flux.shape!=error.shape or np.any(np.diff(wave)<=0):raise ValueError('invalid redshift spectrum')
    flux=flux.copy();error=error.copy()
    for lo,hi in [(5560,5600),(6280,6330),(6345,6385),(6850,6960),(7580,7720)]:
        blocked=(wave>lo)&(wave<hi);flux[blocked]=np.nan;error[blocked]=np.nan
    good=np.isfinite(flux)&np.isfinite(error)&(error>0)
    if good.sum()<100:return dict(status='insufficient_data',z=None,solutions=[])
    filled=np.interp(wave,wave[good],flux[good]);sigma=np.interp(wave,wave[good],error[good])
    continuum=median_filter(filled,size=61,mode='nearest');residual=filled-continuum
    step=float(np.median(np.diff(wave)));kernel=max(1.,fwhm/2.355/step)
    significance=gaussian_filter1d(residual/sigma,kernel)*np.sqrt(2*np.sqrt(np.pi)*kernel)
    significance[~good]=0
    # Fixed terrestrial features cannot serve as galaxy evidence.
    for lo,hi in [(5560,5600),(6280,6330),(6345,6385),(6850,6960),(7580,7720)]:
        significance[(wave>lo)&(wave<hi)]=0
    peaks,_=find_peaks(significance,height=5,prominence=3,distance=max(2,int(fwhm/step)))
    peaks=sorted(peaks,key=lambda p:significance[p],reverse=True)[:40]
    hypotheses=[]
    for peak in peaks:
        for rest in ANCHORS.values():
            z=wave[peak]/rest-1
            if not zmin<=z<=zmax:continue
            strengths=[max(0.,float(np.interp(r*(1+z),wave,significance,left=0,right=0))) for r in ANCHORS.values()]
            strengths=sorted(strengths,reverse=True)
            if strengths[2]<3:continue
            hypotheses.append((sum(min(s,20)**2 for s in strengths),z))
    seeds=[]
    for score,z in sorted(hypotheses,reverse=True):
        if all(abs(z-other)>.0015 for other in seeds):seeds.append(z)
        if len(seeds)>=16:break
    solutions=[]
    for z in seeds:
        groups=[fit_group(wave,flux,error,z,name,fwhm) for name in GROUPS]
        groups=[g for g in groups if g is not None]
        detected=[g for g in groups if g['detected']]
        if len(detected)<3:continue
        median=float(np.median([g['z'] for g in detected]))
        consistent=[g for g in detected if abs(g['z']-median)*np.mean(g['rest_vacuum_angstrom'])<=fwhm*.35]
        if len(consistent)<3:continue
        weights=np.array([1/max(g['z_weight_error'],1e-10)**2 for g in consistent])
        zs=np.array([g['z'] for g in consistent]);best=float(np.average(zs,weights=weights))
        score=sum(min(g['snr'],20)**2 for g in consistent)
        stat=float(np.sqrt(1/weights.sum()))
        # Every consistent narrow group contributes. Where the groups disagree by
        # more than their own fit errors imply, their scatter is the better
        # description of the uncertainty, so take whichever is larger.
        scatter=float(np.std(zs,ddof=1)/np.sqrt(len(zs))) if len(zs)>1 else 0.
        solutions.append(dict(z=best,z_stat_error=stat,score=float(score),
            z_error=float(max(stat,scatter)),z_scatter_error=scatter,
            z_error_basis='larger of the inverse-variance fit error and the standard error of the '
                          'group-to-group scatter, over every consistent narrow emission-line group',
            groups=groups,consistent_groups=[g['group'] for g in consistent],
            group_z_scatter=float(np.std(zs)),number_of_groups=len(consistent)))
    solutions.sort(key=lambda s:s['score'],reverse=True)
    # Cluster multiple search seeds that converge onto the same solution.
    unique=[]
    for s in solutions:
        if all(abs(s['z']-v['z'])>.0015 for v in unique):unique.append(s)
    if not unique:return dict(status='no_reliable_line_system',z=None,solutions=[])
    ambiguous=len(unique)>1 and unique[1]['score']>=.7*unique[0]['score']
    return dict(status='ambiguous' if ambiguous else 'candidate',z=None if ambiguous else unique[0]['z'],
        solutions=unique[:3],search_range=[zmin,zmax],line_reference=LINE_SOURCE,
        error_scope='fit covariance with unresolved-blend centroid floors; wavelength calibration, background, resampling covariance and line identification systematics are not included')


def spatial_line_check(extracted,solution,fwhm):
    """Check whether at least two line groups share localized spatial emission."""
    wave=extracted['wave_vacuum'];image=extracted['rectified_sky_subtracted']
    var=extracted['rectified_variance'];x=extracted['spatial_pixel']
    trace=extracted['trace']+x[0];records=[]
    for group in solution['groups']:
        if group['group'] not in solution['consistent_groups']:continue
        centres=np.array(group['observed_vacuum_angstrom'])
        distance=np.min(abs(wave[:,None]-centres),axis=1)
        on=distance<fwhm*.65;off=(distance>fwhm*1.5)&(distance<fwhm*2.5)
        if on.sum()<2 or off.sum()<3:continue
        def mean_rows(values):
            count=np.isfinite(values).sum(axis=0)
            return np.divide(np.nansum(values,axis=0),count,out=np.full(values.shape[1],np.nan),where=count>0)
        profile=mean_rows(image[on])-mean_rows(image[off])
        variance=np.nansum(var[on],axis=0)/np.maximum(np.isfinite(var[on]).sum(axis=0),1)**2
        variance+=np.nansum(var[off],axis=0)/np.maximum(np.isfinite(var[off]).sum(axis=0),1)**2
        centre=float(np.median(trace[on]));inside=abs(x-centre)<=extracted['aperture_radius_pixels']
        outside=(abs(x-centre)>40)&(x>x[0]+5)&(x<x[-1]-5)&np.isfinite(profile)&np.isfinite(variance)&(variance>0)
        if outside.sum()<20:continue
        baseline=float(np.median(profile[outside]))
        baseline_var=float(1.2533**2*np.median(variance[outside])/outside.sum())
        profile=profile-baseline
        valid=inside&np.isfinite(profile)&np.isfinite(variance)&(variance>0)
        if valid.sum()<5:continue
        smooth=gaussian_filter1d(np.where(valid,profile,0),1.)
        peak=int(np.argmax(np.where(valid,smooth,-np.inf)))
        support=valid&(abs(x-x[peak])<=3)
        snr=float(np.sum(profile[support])/np.sqrt(np.sum(variance[support])+support.sum()**2*baseline_var))
        records.append(dict(group=group['group'],peak_spatial_pixel=float(x[peak]),snr=snr,
            outer_spatial_baseline=baseline,
            spatial_pixel=x.tolist(),line_profile=np.where(np.isfinite(profile),profile,0).tolist()))
    strong=[r for r in records if r['snr']>=5]
    clusters=[[r for r in strong if abs(r['peak_spatial_pixel']-anchor['peak_spatial_pixel'])<=5] for anchor in strong]
    coherent=max(clusters,key=len) if clusters else []
    passed=len(coherent)>=2 and len(coherent)>=.75*len(strong)
    return dict(passed=bool(passed),groups=records,
        coherent_groups=[r['group'] for r in coherent],
        rule='at least two groups with spatial line SNR >=5 in a 10-pixel interval, containing >=75 percent of strong groups; host association not established')
