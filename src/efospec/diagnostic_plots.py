"""Real detector diagnostics, including exposures with no extracted spectrum."""
import numpy as np
from .figure_style import house_style, COLORS


def raw_inspection(path):
    """Uncalibrated nominal source window; no wavelength or trace is invented."""
    from astropy.io import fits
    data=fits.getdata(path).astype(float)
    if data.ndim!=2:raise ValueError('raw inspection requires a two-dimensional detector')
    # Same raw-pixel convention as native extraction, bounded to the detector.
    ny,nx=data.shape
    x0=max(0,min(448,nx-201));x1=min(nx,x0+201)
    y0=min(4,ny-1);y1=min(1015,ny)
    return dict(data=data[y0:y1,x0:x1],raw_x_origin=x0,raw_y_origin=y0,
        data_unit='ADU',sky_mask_stage='source_finding_only_no_accepted_background_fit')


def sky_available(images):
    return ('sky' in images and
        not str(images.get('sky_mask_stage','')).startswith('source_finding_only_no_') and
        np.asarray(images.get('sky_input_mask',[]),bool).any())


@house_style
def plot_before_after(images, result, output, *, origin=(0,0), traces=(), labels=None):
    """A missing subtraction is an empty panel, never a second raw image."""
    import matplotlib.pyplot as plt
    from .figure_style import save_qc
    from .recovery_qc import _image, _candidate_label
    data=np.asarray(images['data']);ny,nx=data.shape;y0,x0=origin
    extent=[x0-.5,x0+nx-.5,y0-.5,y0+ny-.5]
    available=sky_available(images)
    unit=str(images.get('data_unit','electron'))
    fig,axes=plt.subplots(1,2,figsize=(20,12),layout='constrained')
    for index,ax in enumerate(axes):
        if index==0 or available:
            pixels=data if index==0 else data-images['sky']
            im=_image(ax,pixels,extent,residual=index==1)
            fig.colorbar(im,ax=ax,label='ADU (uncalibrated)' if unit=='ADU' else r'$e^{-}$',shrink=.65)
            for i,trace in enumerate(traces):
                colour=COLORS[i%len(COLORS)]
                ax.plot(trace,np.arange(ny)+y0,color=colour,lw=3.,ls='--')
                ax.set_xlim(extent[:2])
                _candidate_label(ax,trace[int(.03*(ny-1))],labels[i] if labels else f'C{i+1}',colour)
        else:
            ax.text(.5,.5,'Sky subtraction unavailable\nNo accepted background model',
                ha='center',va='center',transform=ax.transAxes,fontsize=22)
        ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:])
        ax.set_xlabel('Raw x / spatial pixel' if origin!=(0,0) else 'Spatial pixel (saved window)')
        ax.set_ylabel('Raw y / spectral pixel' if origin!=(0,0) else 'Spectral pixel (saved window)')
        ax.set_title('Before sky subtraction'+(' (raw)' if unit=='ADU' else '') if index==0 else 'After sky subtraction')
    fig.suptitle(result['object'],fontsize=28)
    save_qc(fig,output,'traces',result['object']);plt.close(fig)
    return dict(sky_subtracted=bool(available),data_unit=unit,raw_origin_yx=list(origin),
                trace_count=len(traces),after_panel='saved subtraction' if available else 'empty')


@house_style
def draw_raw_profiles(images,result):
    """Three detector-row sums when calibrated wavelengths are unavailable."""
    import matplotlib.pyplot as plt
    from .profile_plot import _observed_profile_limits
    from .figure_style import style,plain_tex
    data=np.asarray(images['data']);y0=int(images['raw_y_origin']);x0=int(images['raw_x_origin'])
    x=np.arange(data.shape[1])+x0
    fig,axes=plt.subplots(3,1,figsize=(13,13),sharex=True,layout='constrained')
    bins=[]
    for ax,rows in zip(axes,np.array_split(np.arange(len(data)),3)):
        count=np.isfinite(data[rows]).sum(axis=0)
        signal=np.nansum(data[rows],axis=0);signal[count==0]=np.nan
        ax.plot(x,signal/1000.,color='0.3',lw=1.3)
        limits=_observed_profile_limits([signal/1000.])
        if limits is not None:ax.set_ylim(*limits)
        ax.set_xlim(x[0]-.5,x[-1]+.5)
        ax.set_title(f'Raw spectral rows {rows[0]+y0}--{rows[-1]+y0}',fontsize=20)
        ax.set_ylabel(r'Summed signal [$10^3$ ADU]')
        style.set_plotparams(ax,xticks=(20,5),yticks=None,fs=18)
        ax.tick_params(axis='x',labelbottom=True)
        bins.append(dict(raw_spectral_rows=[int(rows[0]+y0),int(rows[-1]+y0)],
            spatial_pixel=x.tolist(),summed_adu=np.where(np.isfinite(signal),signal,None).tolist()))
    axes[-1].set_xlabel('Spatial pixel (raw detector)')
    fig.suptitle(plain_tex(result['object'])+' / Raw spatial profile\nNo calibrated wavelengths or accepted background',fontsize=20)
    return fig,dict(model_available=False,sky_subtracted=False,extraction_accepted=False,
        display_only=True,profile_statistic='finite raw ADU summed in three disjoint detector-row intervals',
        wavelength_available=False,trace_count=0,raw_origin_yx=[y0,x0],bins=bins)
