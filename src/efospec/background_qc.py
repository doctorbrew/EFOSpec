"""House-style inspection shared by the desktop editor and saved experiments."""
import numpy as np
from .figure_style import COLORS,style,plain_tex,save_qc,house_style
from .trace_geometry import TRACE_STYLES
from .profile_limits import _profile_limit_samples, _profile_limits
from .profile_plot import _observed_profile_limits


def profile_view_limits(ax,x,signal,protected,*,model=None,background=None,visible=None):
    """Use the nightly profile display rules without changing plotted samples."""
    retained,excluded=_profile_limit_samples(signal,protected,spatial_pixel=x,edge_margin=3)
    if visible is not None:retained=np.where(visible,retained,np.nan)
    if model is None:
        limits=_profile_limits([retained],background_subtracted=True)
    else:
        fitted=np.where(np.isfinite(retained),model,np.nan)
        limits=_observed_profile_limits([retained,fitted],background=background)
    if limits is not None:ax.set_ylim(*limits)
    return dict(display_only=True,excluded_spatial_pixels=x[excluded].tolist())


@house_style
def draw_candidates(fig,exposure):
    fig.clear();ax=fig.subplots()
    x=np.arange(exposure.window.shape[1])+exposure.window.origin[1]
    profile=np.nanmedian(exposure.images['data']-exposure.images['sky'],axis=0)
    ax.plot(x,profile,color='0.3',label='Saved sky-subtracted spatial profile')
    protected=np.zeros(x.shape,bool)
    for i,trace in enumerate(exposure.images['found_traces']):
        raw_trace=trace+exposure.window.origin[1]
        protected|=(x>=raw_trace.min()-3)&(x<=raw_trace.max()+3)
        ax.axvline(raw_trace[len(trace)//2],color='0.3',ls=TRACE_STYLES[i%4],lw=2,label=f'C{i+1} (unverified)')
    ax.set_xlim(x[2],x[-3])
    fig.profile_display=profile_view_limits(ax,x,profile,protected)
    ax.set_xlabel('Raw spatial pixel x (zero based)');ax.set_ylabel('Median residual electrons')
    ax.set_title(plain_tex(exposure.result['object']+' -- select source and background bands'))
    style.set_plotparams(ax,xticks=(20,5),yticks=None,grid=False)
    style.styled_legend(ax,ncol=2,loc='upper center',bbox_to_anchor=(.5,-.22))
    fig.subplots_adjust(bottom=.28,top=.92)
    return ax


@house_style
def draw_background(fig, exposure, recipe, result, *, panel=None):
    fig.clear()
    selected=[0,1] if panel is None else [panel]
    axes=np.atleast_1d(fig.subplots(len(selected),1))
    x=np.arange(exposure.window.shape[1])+exposure.window.origin[1]
    valid=result['valid'];data=exposure.context.data
    if not valid.any():raise ValueError('no valid background rows for preview')
    profile=np.nanmedian(data[valid],axis=0)
    model=np.nanmedian(result['model'][valid],axis=0)
    residual=np.nanmedian((data-result['model'])[valid],axis=0)
    obj=recipe['objects'][0]
    low=min(lo for lo,hi in recipe['sky']['include'])-12
    high=max(hi for lo,hi in recipe['sky']['include'])+12
    visible=(x>=low)&(x<=high)
    protected=(x>=obj['spat']-obj['radius'])&(x<=obj['spat']+obj['radius'])
    for trace in exposure.images['found_traces']:
        protected|=(x>=np.min(trace)+exposure.window.origin[1]-3)&(x<=np.max(trace)+exposure.window.origin[1]+3)
    support=(x>=min(lo for lo,hi in recipe['sky']['include']))&(x<max(hi for lo,hi in recipe['sky']['include']))
    model=np.where(support,model,np.nan)
    fig.profile_display=[]
    for ax,index in zip(axes,selected):
        if index==0:
            ax.plot(x,profile,color='0.3',label='Observed data (median of rows)')
            ax.plot(x,model,color='xkcd:dodger blue',ls='--',label=f"Background: degree {recipe['sky']['degree']}")
        else:
            ax.plot(x,residual,color='0.3',label='After local sky + host interpolation')
            ax.axhline(0,color='0.4',lw=1.)
        for i,(lo,hi) in enumerate(recipe['sky']['include']):
            patch=ax.axvspan(lo,hi,color='xkcd:dodger blue',alpha=.14,label='Background sampling' if i==0 else None)
            patch._efospec_background=True
        ax.axvspan(obj['spat']-obj['radius'],obj['spat']+obj['radius'],color='xkcd:red',alpha=.14,label='Boxcar aperture')
        ax.axvline(obj['spat'],color='xkcd:red',ls='--')
        ax.set_xlim(low,high)
        fig.profile_display.append(profile_view_limits(ax,x,residual,protected,visible=visible) if index else
            profile_view_limits(ax,x,profile,protected,model=model,background=profile[support&~protected],visible=visible))
        ax.set_xlabel('Raw spatial pixel x (zero based)');ax.set_ylabel('Electrons per pixel')
        style.set_plotparams(ax,xticks=(10,2),yticks=None,grid=False)
        style.styled_legend(ax,ncol=2,loc='upper center',bbox_to_anchor=(.5,-.24),fontsize=18)
    fig.suptitle(plain_tex(exposure.result['object']+': provisional local background'))
    fig.subplots_adjust(hspace=.85,bottom=.25 if panel is None else .32,top=.9)
    return fig


@house_style
def save_background_plot(exposure,recipe,result,output):
    import matplotlib.pyplot as plt
    fig=plt.figure(figsize=(20,14))
    draw_background(fig,exposure,recipe,result)
    save_qc(fig,output,'polynomial-background',exposure.result['object'])
    plt.close(fig)
