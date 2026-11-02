"""House-style inspection shared by the desktop editor and saved experiments."""
import numpy as np
from .figure_style import COLORS,style,plain_tex,save_qc,house_style


@house_style
def draw_candidates(fig,exposure):
    fig.clear();ax=fig.subplots()
    x=np.arange(exposure.window.shape[1])+exposure.window.origin[1]
    profile=np.nanmedian(exposure.images['data']-exposure.images['sky'],axis=0)
    ax.plot(x,profile,color=COLORS[0],label='Saved sky-subtracted spatial profile')
    for i,trace in enumerate(exposure.images['found_traces']):
        ax.axvline(trace[len(trace)//2]+exposure.window.origin[1],color=COLORS[i%3],ls='--',label=f'C{i+1} (unverified)')
    ax.set_xlim(x[2],x[-3]);ax.set_ylim(np.min(profile[2:-2])*1.1,np.max(profile[2:-2])*1.1)
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
    for ax,index in zip(axes,selected):
        if index==0:
            ax.plot(x,profile,color=COLORS[0],label='Raw spatial profile (median of rows)')
            ax.plot(x,model,color=COLORS[1],label=f"Background: degree {recipe['sky']['degree']} (median of row fits)")
            values=np.r_[profile[visible],model[visible]]
        else:
            ax.plot(x,residual,color=COLORS[2],label='After local sky + host interpolation')
            ax.axhline(0,color='0.4',lw=1.);values=residual[visible]
        for i,(lo,hi) in enumerate(recipe['sky']['include']):
            ax.axvspan(lo,hi,color=COLORS[0],alpha=.14,label='Requested background bands' if i==0 else None)
        ax.axvspan(obj['spat']-obj['radius'],obj['spat']+obj['radius'],color=COLORS[2],alpha=.14,label='Boxcar aperture')
        ax.axvline(obj['spat'],color=COLORS[2],ls='--')
        ax.set_xlim(low,high)
        span=max(float(np.ptp(values)),1.)
        ax.set_ylim(float(np.min(values))-.1*span,float(np.max(values))+.1*span)
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
