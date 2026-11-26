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
    fig.extraction_axes=None
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
    fig.extraction_axes=None
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


@house_style
def update_extraction_selection(fig, exposure, obj=None, bands=()):
    """Update display geometry in both spatial panels, including partial recipes."""
    axes=getattr(fig,'extraction_axes',None)
    if axes is None:return
    image_ax,profile_ax,_=axes
    for ax in (image_ax,profile_ax):
        for artist in list(ax.get_children()):
            if getattr(artist,'_efospec_selection',False):artist.remove()
    def mark(artist,background=False):
        artist._efospec_selection=True
        artist._efospec_background=background
        return artist
    y0,x0=exposure.window.origin
    rows=np.arange(exposure.window.shape[0])+y0
    if obj is not None:
        anchor=int(np.clip(round(obj['spec']-y0),0,len(rows)-1))
        traces=exposure.images['found_traces']+x0
        trace=traces[np.argmin(abs(traces[:,anchor]-obj['spat']))].copy()
        trace+=obj['spat']-trace[anchor]
        radius=obj['radius']
        mark(image_ax.plot(trace,rows,color='xkcd:red',lw=2)[0])
        mark(image_ax.fill_betweenx(rows,trace-radius,trace+radius,color='xkcd:red',alpha=.18))
        mark(image_ax.plot(obj['spat'],obj['spec'],marker='+',color='xkcd:red',ms=12)[0])
        mark(profile_ax.axvline(obj['spat'],color='xkcd:red',ls='--'))
        mark(profile_ax.axvspan(obj['spat']-radius,obj['spat']+radius,color='xkcd:red',alpha=.18))
    for lo,hi in bands:
        for ax in (image_ax,profile_ax):
            mark(ax.axvspan(lo,hi,color='xkcd:dodger blue',alpha=.2),True)


@house_style
def draw_extraction(fig, exposure, recipe=None, result=None):
    """Tall detector beside spatial profile and counts; shared raw spatial axis."""
    from .image_display import image_normalization
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    fig.clear()
    grid=fig.add_gridspec(2,2,width_ratios=(.85,1.4))
    image_ax=fig.add_subplot(grid[:,0])
    profile_ax=fig.add_subplot(grid[0,1],sharex=image_ax)
    counts_ax=fig.add_subplot(grid[1,1])
    fig.extraction_axes=(image_ax,profile_ax,counts_ax)
    data=exposure.images['data'];y0,x0=exposure.window.origin
    ny,nx=data.shape;rows=np.arange(ny)+y0;x=np.arange(nx)+x0
    norm,display=image_normalization(data,bright_percentile=99.5)
    image_ax.imshow(data,origin='lower',aspect='auto',cmap='gray_r',norm=norm,
        extent=(x0-.5,x0+nx-.5,y0-.5,y0+ny-.5),interpolation='nearest')
    profile=np.nanmedian(data-exposure.images['sky'],axis=0)
    profile_ax.plot(x,profile,color='0.3')
    protected=np.zeros(nx,bool)
    for i,trace in enumerate(exposure.images['found_traces']):
        raw_trace=trace+x0
        image_ax.plot(raw_trace,rows,color='0.4',ls=TRACE_STYLES[i%4],lw=1)
        profile_ax.axvline(raw_trace[ny//2],color='0.4',ls=TRACE_STYLES[i%4],lw=1)
        protected|=(x>=raw_trace.min()-7)&(x<=raw_trace.max()+7)
    profile_view_limits(profile_ax,x,profile,protected)
    profile_ax.set_title('Spatial profile (row median)')
    profile_ax.set_xlabel('Raw spatial pixel x');profile_ax.set_ylabel('Residual electrons')
    image_ax.set_xlim(x0-.5,x0+nx-.5);image_ax.set_ylim(y0-.5,y0+ny-.5)
    image_ax.set_xlabel('Raw spatial pixel x');image_ax.set_ylabel('Raw spectral row')
    image_ax.set_title('2D detector (electrons)')
    counts_ax.set_xlabel('Raw spectral row');counts_ax.set_ylabel('Electrons')
    counts_ax.set_title('Uncalibrated count preview')
    counts_ax.set_xlim(rows[0],rows[-1])
    if recipe is not None and result is not None:
        counts=np.where(result['valid'],result['counts'],np.nan);sigma=np.sqrt(result['variance'])
        counts_ax.plot(rows,counts,color='xkcd:red')
        counts_ax.fill_between(rows,counts-sigma,counts+sigma,color='xkcd:red',alpha=.14)
        counts_ax.axhline(0,color='0.5',lw=1)
        update_extraction_selection(fig,exposure,recipe['objects'][0],recipe['sky']['include'])
    else:
        counts_ax.text(.5,.5,'Select trace and bands,\nthen preview counts',ha='center',va='center',transform=counts_ax.transAxes)
    for ax in fig.axes:
        width=ax.get_xlim()[1]-ax.get_xlim()[0]
        step=max(1.,float(10**np.floor(np.log10(width/5)))*round(width/5/10**np.floor(np.log10(width/5))))
        style.set_plotparams(ax,xticks=(step,step/4),yticks=None,grid=False)
    style.styled_legend(fig,handles=[Line2D([],[],color='xkcd:red',label='Selected trace'),
        Patch(color='xkcd:red',alpha=.18,label='Aperture'),
        Patch(color='xkcd:dodger blue',alpha=.2,label='Background bands')],
        ncol=3,loc='lower center',bbox_to_anchor=(.5,.005))
    fig.suptitle(plain_tex(exposure.result['object']+' -- extraction preview'))
    fig.profile_display={'image':display,'counts':'provisional saved-trace boxcar; no flux or wavelength acceptance',
                         'spatial_profile':'median saved sky-subtracted rows; aperture marker at selected anchor row'}
    fig.subplots_adjust(left=.09,right=.97,top=.88,bottom=.22,wspace=.5,hspace=.75)
    return fig
