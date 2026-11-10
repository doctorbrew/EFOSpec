"""Saved 1D fits and 2D evidence for automatic line-system candidates."""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from .figure_style import house_style, save_qc, COLORS
from .image_display import image_normalization
from .inventory import sha256

EVIDENCE_CMAP = 'RdBu_r'


def _evidence_norm(image):
    """Diverging arcsinh scale about the local background of this panel.

    These cut-outs keep the host continuum, which is positive across the whole
    field, so centring on zero would leave half the colour map unused. Centring
    on the clipped median instead makes the diverging map say what the panel is
    evidence for: line emission above the local background reads red, and
    absorption or over-subtraction reads blue. Display only.
    """
    finite = np.isfinite(image)
    if not finite.any():
        raise ValueError('no finite pixels in the redshift evidence image')
    return image_normalization(image, cmap=EVIDENCE_CMAP, samples=image[finite],
                               bright_percentile=99., symmetric=True)[0]


@house_style
def plot_redshift(record, extracted, directory):
    spectral=record['spectral'];solutions=spectral.get('solutions',[])
    wave=extracted['wave_vacuum'];flux=extracted['counts'];error=extracted['sigma']
    if solutions:
        solution=solutions[0]
        groups=sorted([g for g in solution['groups'] if g['group'] in solution['consistent_groups']],
                      key=lambda g:g['snr'],reverse=True)[:3]
    else:groups=[]
    fig=plt.figure(figsize=(19,15 if groups else 10))
    grid=fig.add_gridspec(3 if groups else 2,3,hspace=.6,wspace=.4)
    ax=fig.add_subplot(grid[0,:]);ax.plot(wave,flux,color=COLORS[0],lw=.8)
    ax.fill_between(wave,flux-error,flux+error,color=COLORS[0],alpha=.15)
    finite=flux[np.isfinite(flux)]
    if len(finite):
        low,high=np.percentile(finite,[1,99.7]);span=max(high-low,1.)
        ax.set_ylim(low-.1*span,high+.2*span)
    ax.set_xlim(wave.min(),wave.max());ax.set_ylabel('Counts (electrons)')
    ax.set_xlabel(r'Observed vacuum wavelength ($\mathrm{\AA}$)')
    z=spectral.get('z_heliocentric');z_error=spectral.get('z_heliocentric_error')
    detail=spectral['status'].replace('_',' ')
    if z is not None:
        detail=(f'Candidate heliocentric z = {z:.5f}'
                +(rf' $\pm$ {z_error:.5f}' if z_error is not None else ''))
    quality='sky wavelength check passed' if spectral['wavelength_validated'] else 'PROVISIONAL: wavelength unvalidated'
    ax.set_title(record['object']+' / '+detail+'\n'+quality)
    x=extracted['spatial_pixel'];trace=extracted['trace']+x[0]
    for i,group in enumerate(groups):
        ax=fig.add_subplot(grid[1,i]);w=np.array(group['wave']);f=np.array(group['counts']);e=np.array(group['sigma'])
        ax.plot(w,f,color=COLORS[0],lw=1.2);ax.fill_between(w,f-e,f+e,color=COLORS[0],alpha=.2)
        ax.plot(w,group['model'],color=COLORS[1],lw=2)
        ax.set_title(group['group']+f" / line SNR {group['snr']:.1f}")
        ax.set_xlim(w.min(),w.max());ax.set_ylabel('Counts (electrons)' if i==0 else '')
        ax.set_xlabel(r'Vacuum wavelength ($\mathrm{\AA}$)')
        image_ax=fig.add_subplot(grid[2,i]);rows=(wave>=w.min())&(wave<=w.max())
        columns=abs(x-np.median(trace[rows]))<=30
        image=extracted['rectified_sky_subtracted'][np.ix_(rows,columns)].T
        image_ax.pcolormesh(wave[rows],x[columns],image,shading='nearest',cmap=EVIDENCE_CMAP,
                            norm=_evidence_norm(image),rasterized=True)
        image_ax.plot(wave[rows],trace[rows],color=COLORS[1],ls='--',lw=1)
        image_ax.set_ylabel('Spatial pixel (raw -99)' if i==0 else '')
        image_ax.set_xlabel(r'Vacuum wavelength ($\mathrm{\AA}$)')
        image_ax.set_title('2D emission / dashed trace')
    if not groups:
        ax=fig.add_subplot(grid[1,:]);columns=abs(x-np.median(trace))<=30
        image=extracted['rectified_sky_subtracted'][:,columns].T
        ax.pcolormesh(wave,x[columns],image,shading='nearest',cmap=EVIDENCE_CMAP,
                      norm=_evidence_norm(image),rasterized=True)
        ax.plot(wave,trace,color=COLORS[1],ls='--',lw=1)
        ax.set_xlabel(r'Observed vacuum wavelength ($\mathrm{\AA}$)');ax.set_ylabel('Spatial pixel (raw -99)')
        ax.set_title('2D emission search near the selected trace')
    stem=save_qc(fig,directory,'redshift',record['object']);plt.close(fig)
    paths=[stem.with_suffix(s) for s in ('.pdf','.jpg')]+[Path(directory)/'redshift.png']
    return {str(p):sha256(p) for p in paths}
