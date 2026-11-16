"""House-style views of retained sky correlations; no extraction or correction."""
import numpy as np
from .figure_style import house_style,save_qc,COLORS
from .inventory import sha256


@house_style
def plot_region(arrays,index,measurement,trials,vectors,output,stage,target):
    import matplotlib.pyplot as plt
    from scipy.ndimage import gaussian_filter1d
    wave=arrays[f'matched_wave_{index}'];observed=arrays[f'observed_{index}'];template=arrays[f'template_{index}']
    a=observed-gaussian_filter1d(observed,15.);b=template-gaussian_filter1d(template,15.)
    x=np.arange(len(a));lags=np.arange(-10.,10.01,.25);scores=[]
    for lag in lags:
        shifted=np.interp(x+lag,x,b,left=np.nan,right=np.nan)
        keep=(x>=20)&(x<len(x)-20)&np.isfinite(a)&np.isfinite(shifted)
        aa=a[keep]-a[keep].mean();bb=shifted[keep]-shifted[keep].mean();norm=np.linalg.norm(aa)*np.linalg.norm(bb)
        scores.append(float(aa@bb/norm) if norm>1e-12 else 0.)
    scores=np.asarray(scores);best=measurement['quality']['peak_lag_pixels']
    a=a/max(np.linalg.norm(a),1e-12);b=b/max(np.linalg.norm(b),1e-12)
    fig,axes=plt.subplots(2,1,figsize=(14,12),layout='constrained')
    ax=axes[0];ax.plot(wave,a,color=COLORS[2],label='Observed sky')
    ax.plot(wave,b,color='.5',ls=':',label='Template / unshifted')
    ax.plot(wave,np.interp(x+best,x,b,left=np.nan,right=np.nan),color=COLORS[0],ls='--',label=f'Template / diagnostic {best:+.2f} pixel')
    interval=measurement['range_vacuum_angstrom']
    ax.set(xlim=(wave[20],wave[-21]),xlabel='Vacuum wavelength (Å)',ylabel='High-pass sky / L2 norm',
           title=f'{target} / {stage} / {interval[0]:g}--{interval[1]:g} Å')
    ax=axes[1];centre=float(arrays[f'correlation_centre_{index}']);xx=arrays[f'lags_{index}']-centre
    corr=arrays[f'correlation_{index}'];scale=max(float(np.max(abs(corr))),1e-12)
    ax.plot(xx,corr/scale,'o',color=COLORS[2],label='PypeIt peak samples')
    fine=np.linspace(xx.min(),xx.max(),150);fit=np.polynomial.polynomial.polyval(fine+centre,arrays[f'fit_coefficients_{index}'])
    ax.plot(fine,fit/scale,color=COLORS[2],ls='--',label='Seven-point quadratic')
    ax.plot(lags,scores/max(float(np.max(abs(scores))),1e-12),color=COLORS[0],label='Normalized high-pass correlation')
    if 'without_initial_observed_clip' in vectors:
        c=vectors['without_initial_observed_clip'];ll=vectors['lags'];mask=abs(ll)<=10
        ax.plot(ll[mask],c[mask]/max(float(np.max(abs(c[mask]))),1e-12),color=COLORS[1],ls='-.',label='Without initial observed-sky clipping')
    ax.axvline(measurement['shift_pixels'],color=COLORS[2],ls=':',lw=1)
    ax.axvline(best,color=COLORS[0],ls=':',lw=1)
    ax.set(xlim=(-4,4),ylim=(-.1,1.15),xlabel='Template lag (detector pixels)',ylabel='Correlation / peak magnitude',
           title=f'PypeIt {measurement["shift_pixels"]:+.3f} pixel; normalized {best:+.3f} pixel')
    if trials['status']!='baseline_reproduced':ax.set_title(ax.get_title()+' / clipping trial unavailable')
    stem=save_qc(fig,output,f'sky-{stage}-region-{index}',target);plt.close(fig)
    return {str(stem.with_name(stem.name+ext)):sha256(stem.with_name(stem.name+ext)) for ext in ('.pdf','.jpg')}
