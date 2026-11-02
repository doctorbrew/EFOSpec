"""Reproducible recovery and uncertainty checks for fixed-profile extraction.

These experiments validate conditional numerical behavior, not host identity or
unconstrained galaxy morphology. Deliberate mismatch cases are reported intact.
"""
import json
from copy import deepcopy
from pathlib import Path
import numpy as np

from .joint import choose_background_degree, extract_joint


def profiles(x, rows, separation, host_width=3., *, sn_width=1.5, host_offset=0.):
    center=(len(x)-1)/2
    p=np.array([np.exp(-.5*((x-center)/sn_width)**2),
                np.exp(-.5*((x-center-separation-host_offset)/host_width)**2)])
    p/=p.sum(axis=1)[:,None]
    return np.repeat(p[:,None,:],rows,axis=1)


def metrics(fit, truth):
    valid=fit['valid'];n=int(valid.sum())
    record={'valid_fraction':float(valid.mean()),'valid_rows':n,
            'flags':{str(flag):int((fit['flags']==flag).sum()) for flag in np.unique(fit['flags'])}}
    if not n:return record
    error=fit['flux'][valid]-truth[valid]
    sigma=np.sqrt(np.diagonal(fit['covariance'][valid],axis1=1,axis2=2))
    pull=error/sigma
    record.update(mean_fractional_bias=np.mean(error/truth[valid],axis=0).tolist(),
                  median_fractional_bias=np.median(error/truth[valid],axis=0).tolist(),
                  mean_pull=pull.mean(axis=0).tolist(),pull_std=pull.std(axis=0,ddof=1).tolist(),
                  coverage_68=(abs(pull)<=1).mean(axis=0).tolist(),
                  coverage_95=(abs(pull)<=1.96).mean(axis=0).tolist(),
                  median_cross_covariance=float(np.median(fit['covariance'][valid,0,1])),
                  median_reduced_chi2=float(np.median(fit['reduced_chi2'][valid])))
    return record


def synthetic_validation(seed=20261102, rows=256):
    if rows<64:raise ValueError('Use at least 64 independent synthetic rows.')
    rng=np.random.default_rng(seed);x=np.arange(96.);coordinate=np.linspace(-1,1,len(x))
    sky=np.broadcast_to((x<14)|(x>81),(rows,len(x)))
    records=[];last=None
    for separation_fwhm in (.5,1.,2.):
        for ratio in (.5,3.):
            for width_ratio in (1.,3.):
                degree=len(records)%3
                p=profiles(x,rows,separation_fwhm*1.5*2.354820045,1.5*width_ratio)
                truth=np.column_stack([2000+300*np.sin(np.arange(rows)/21),
                                       ratio*(2000+200*np.cos(np.arange(rows)/33))])
                background=180+45*coordinate*(degree>=1)+100*coordinate**2*(degree==2)
                expected=np.einsum('rs,srx->rx',truth,p)+background
                variance=expected+36
                data=expected+rng.normal(size=expected.shape)*np.sqrt(variance)
                selection=choose_background_degree(data,variance,sky)
                fit=extract_joint(data,variance,p,sky,background_degree=selection['degree'])
                summary=metrics(fit,truth)
                summary.update(separation_fwhm=separation_fwhm,host_to_sn_flux=ratio,
                               host_to_sn_width=width_ratio,true_degree=degree,selection=selection)
                summary['conditional_pass']=bool(summary['valid_fraction']>.98 and
                    np.all(np.abs(summary['mean_pull'])<max(.25,4/np.sqrt(rows))) and
                    np.all((np.array(summary['pull_std'])>.75)&(np.array(summary['pull_std'])<1.25)) and
                    np.all((np.array(summary['coverage_95'])>.88)&(np.array(summary['coverage_95'])<.995)))
                records.append(summary)
                if degree==2 and width_ratio==3 and separation_fwhm==1:
                    last=(data,variance,p,sky,truth)
    data,variance,p,sky,truth=last
    mismatch=[]
    for name,fit_profiles,degree in [
        ('host_width_20_percent_wrong',profiles(x,rows,1.5*2.354820045,5.4),2),
        ('host_center_offset_1_pixel',profiles(x,rows,1.5*2.354820045,4.5,host_offset=1.),2),
        ('linear_background_for_quadratic_sky',p,1),
    ]:
        result=metrics(extract_joint(data,variance,fit_profiles,sky,background_degree=degree),truth)
        result['case']=name;mismatch.append(result)
    shifted=profiles(x,rows,1.5*2.354820045,2.,host_offset=6.)[1]
    asymmetric=.75*p[1]+.25*shifted
    expected=variance-36+truth[:,1,None]*(asymmetric-p[1])
    asymmetric_variance=expected+36
    result=metrics(extract_joint(expected+rng.normal(size=expected.shape)*np.sqrt(asymmetric_variance),
        asymmetric_variance,p,sky,background_degree=2),truth)
    result['case']='asymmetric_host_fit_with_single_gaussian';mismatch.append(result)
    identical=np.array([p[0],p[0]])
    degenerate=extract_joint(data,variance,identical,sky,background_degree=2)
    rejected=not degenerate['valid'].any()
    return {'seed':seed,'independent_rows_per_case':rows,'matched_cases':records,
            'mismatch_cases':mismatch,'identical_profiles_rejected':rejected,
            'conditional_tests_passed':bool(rejected and all(r['conditional_pass'] for r in records)),
            'science_validated':False,
            'limits':['Known fixed Gaussian spatial profiles, independent Gaussian pixel noise and known variance.',
                      'Formal errors exclude profile, calibration and spectral-resampling uncertainty.',
                      'Mismatch cases are sensitivity diagnostics, not cases to discard from a science sample.']}


def observed_injections(exposure, seed=812, trials=6):
    """Inject photon counts into the longest shared saved off-source sky band.

    The measured background is reused, so trials do not calibrate its uncertainty.
    No host identity or rectification accuracy is inferred from this experiment.
    """
    mask=np.asarray(exposure.images['sky_input_mask'],bool).all(axis=0)
    edges=np.flatnonzero(np.diff(np.r_[False,mask,False])).reshape(-1,2)
    if len(edges)==0:raise ValueError('No common saved background band is available.')
    lo,hi=max(edges,key=lambda pair:pair[1]-pair[0])
    if hi-lo<32:raise ValueError('Observed injections require a background band at least 32 pixels wide.')
    data=exposure.context.data[:,lo:hi].copy();nx=data.shape[1];x=np.arange(nx)
    bad=exposure.images.get('mask',np.zeros(exposure.context.data.shape))[:,lo:hi]!=0
    data[bad]=np.nan
    variance=np.maximum(data,0)+exposure.frame['metadata']['ESO DET OUT1 RON']**2
    if exposure.context.processed:
        ivar=exposure.context.processed['ivar'][:,lo:hi]
        variance=np.divide(1,ivar,out=np.full_like(ivar,np.nan),where=ivar>0)
    sky=np.broadcast_to((x<7)|(x>=nx-7),data.shape).copy() & np.isfinite(data) & np.isfinite(variance)
    keep=sky.sum(axis=1)>=12;data=data[keep];variance=variance[keep];sky=sky[keep]
    if len(data)<64:raise ValueError('Too few valid background rows for injections.')
    p=profiles(x,len(data),3.,2.2,sn_width=1.3)
    y=np.arange(len(data));truth=np.column_stack([1800+250*np.sin(y/40),2600+300*np.cos(y/55)])
    signal=np.einsum('rs,srx->rx',truth,p)
    selection=choose_background_degree(data,variance,sky)
    rng=np.random.default_rng(seed);records=[]
    for trial in range(trials):
        fit=extract_joint(data+rng.poisson(signal),variance+signal,p,sky,background_degree=selection['degree'])
        record=metrics(fit,truth);record['trial']=trial;records.append(record)
    return {'seed':seed,'parent_product':Path(exposure.result['product']).name,
            'input_sha256':exposure.hashes,'raw_spatial_band':[int(lo+exposure.window.origin[1]),int(hi+exposure.window.origin[1])],
            'background_selection':selection,'trials':records,
            'limits':['One measured background realization reused across trials; not independent background noise trials.',
                      'Synthetic profiles and spectra imposed on detector rows; no test of wavelength rectification or galaxy identity.']}


def observed_sensitivity(exposure, recipe):
    """Perturb an explicitly selected companion; no host identity is inferred."""
    from .joint_revisions import fit_exposure
    baseline=fit_exposure(exposure,recipe)
    if len(recipe['objects'])!=2:raise ValueError('Sensitivity checks need two explicitly selected sources.')
    variants=[]
    for degree in (0,1,2):
        value=deepcopy(recipe);value['background_degree']=degree
        variants.append((f'background_degree_{degree}',value))
    for scale in (.8,1.2):
        value=deepcopy(recipe);value['objects'][1]['fwhm']*=scale
        variants.append((f'companion_width_times_{scale}',value))
    for offset in (-1.,1.):
        value=deepcopy(recipe);value['objects'][1]['spat']+=offset
        variants.append((f'companion_center_offset_{offset}',value))
    records=[]
    def full(model):
        values=np.full((len(model['grid']),2),np.nan)
        values[model['rows']]=np.where(model['fit']['valid'][:,None],model['fit']['flux'],np.nan)
        return values
    original=full(baseline)
    for name,value in variants:
        try:
            model=fit_exposure(exposure,value);flux=full(model)
            good=np.isfinite(original).all(axis=1)&np.isfinite(flux).all(axis=1)
            good&=(model['grid']>=4000)&(model['grid']<=8500)
            if good.sum()<20:raise ValueError('Too few common valid wavelength bins.')
            records.append(dict(case=name,recipe=value,status='fit',common_bins=int(good.sum()),
                relative_integrated_change=(flux[good].sum(axis=0)/original[good].sum(axis=0)-1).tolist(),
                median_counts_per_bin=np.median(flux[good],axis=0).tolist(),
                valid_fraction=float(model['fit']['valid'].mean()),
                median_reduced_chi2=float(np.nanmedian(model['fit']['reduced_chi2']))))
        except ValueError as exc:
            records.append(dict(case=name,recipe=value,status='rejected',reason=str(exc)))
    return dict(recipe=recipe,input_sha256=exposure.hashes,
        background_selection=baseline['background_selection'],chosen_degree=baseline['degree'],
        variants=records,wavelength_range_air_angstrom=[4000,8500],
        limits=['Operator-selected companion; source identity and true flux are unknown.',
                'Changes are relative sensitivity on common valid bins, not accuracy or random error.',
                'Fixed Gaussian profiles share measured trace curvature; no extended-host reconstruction.'])


def save_validation(output, *, run=None, product=None, reference_root=None, rows=256, recipe=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    report=synthetic_validation(rows=rows)
    if run is not None:
        from .revisions import Exposure
        exposure=Exposure(run,product,reference_root)
        report['observed_injections']=observed_injections(exposure)
        if recipe is not None:
            report['observed_sensitivity']=observed_sensitivity(exposure,recipe)
    (output/'validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    render_validation(report,output)
    return report


def render_validation(report,output):
    from .figure_style import house_style,style,COLORS,save_qc
    @house_style
    def draw():
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,1,figsize=(18,12),sharex=True)
        cases=report['matched_cases'];x=np.arange(1,len(cases)+1)
        for source,name in enumerate(('Injected SN','Injected companion')):
            mean=np.array([c['mean_pull'][source] for c in cases])
            error=np.array([c['pull_std'][source]/np.sqrt(c['valid_rows']) for c in cases])
            offset=.08*(-1 if source==0 else 1)
            axes[0].errorbar(x+offset,mean,yerr=error,fmt='none',ecolor=COLORS[source],alpha=.5)
            axes[0].plot(x+offset,mean,'o',mfc='white',mec=COLORS[source],label=name)
            axes[1].plot(x+offset,[c['coverage_68'][source] for c in cases],'o',mfc='white',mec=COLORS[source],label=name)
        axes[0].axhline(0,color='0.5',ls='--');axes[1].axhline(.682689,color='0.5',ls='--')
        axes[0].set_ylabel('Mean residual / formal uncertainty');axes[1].set_ylabel('Fraction within formal $1\\sigma$')
        axes[1].set_xlabel('Matched-profile scenario (parameters in validation.json)')
        axes[0].set_ylim(-.4,.4);axes[1].set_ylim(.45,.85);axes[1].set_xlim(.5,len(cases)+.5)
        fig.suptitle('Conditional two-source recovery: known profiles and independent pixel noise')
        fig.subplots_adjust(hspace=.55,bottom=.18,top=.92)
        save_qc(fig,output,'joint-conditional-validation','synthetic-SN-companion')
        plt.close(fig)
    draw()
    if 'observed_sensitivity' not in report:return
    @house_style
    def draw_sensitivity():
        import matplotlib.pyplot as plt
        names={'background_degree_1':'Linear background','background_degree_2':'Quadratic background',
               'companion_width_times_0.8':'Companion width $-20\\%$',
               'companion_width_times_1.2':'Companion width $+20\\%$',
               'companion_center_offset_-1.0':'Companion centre $-1$ pixel',
               'companion_center_offset_1.0':'Companion centre $+1$ pixel'}
        records=[v for v in report['observed_sensitivity']['variants'] if v['status']=='fit' and v['case'] in names]
        if not records:return
        fig,ax=plt.subplots(figsize=(18,11));y=np.arange(len(records))
        for source,name in enumerate(('SN','Unverified companion')):
            values=np.array([v['relative_integrated_change'][source]*100 for v in records])
            ax.plot(values,y+(.10 if source else -.10),'o',color=COLORS[source],mfc='white',label=name)
        ax.axvline(0,color='0.5',ls='--');ax.set_yticks(y,labels=[names[v['case']] for v in records])
        ax.set_xlabel('Integrated count change from selected model [percent]')
        ax.set_ylim(len(records)-.5,-.5);ax.set_xlim(-100,35)
        ax.set_title('Real SN2023xxj companion sensitivity: 4000--8500 $\\AA$')
        fig.subplots_adjust(left=.34,right=.96,bottom=.22,top=.9)
        save_qc(fig,output,'joint-observed-sensitivity','SN2023xxj')
        plt.close(fig)
    draw_sensitivity()
