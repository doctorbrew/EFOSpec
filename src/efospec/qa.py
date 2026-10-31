"""Auditable comparison plots for an experimental rapid run; never alter spectra."""
import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time

from .archive_calibration import rebin_density
from .inventory import sha256


def read_flux(path):
    data,h=fits.getdata(path,header=True)
    wave=h['CRVAL1']+(np.arange(data.shape[-1])+1-h.get('CRPIX1',1))*h['CD1_1']
    return wave,data[:,0,:],h


def compare_legacy(result, legacy_root):
    matches=list(Path(legacy_root).rglob(Path(result['product']).name))
    if not matches:
        return None
    unique={sha256(p):p for p in matches}
    if len(unique)!=1:
        raise ValueError('conflicting legacy comparisons')
    old=next(iter(unique.values()))
    w,b,h=read_flux(result['product']);ow,ob,oh=read_flux(old)
    # Legacy products sometimes round the raw DATE-OBS by 1 ms.
    if abs((Time(h['DATE-OBS'])-Time(oh['DATE-OBS'])).sec)>0.01:
        raise ValueError('legacy comparison exposure mismatch')
    legacy,_,valid=rebin_density(ow,ob[0],ob[3]**2,np.isfinite(ob[0]),w)
    good=valid & np.isfinite(b[0]) & (w>4300)&(w<6800)&(legacy>0)
    for lo,hi in ((5530,5625),(6250,6400),(6500,6625)):
        good &= ~((w>lo)&(w<hi))
    ratio=b[0][good]/legacy[good]
    return {'path':str(old.resolve()),'sha256':sha256(old),
            'ratio_p16_p50_p84':np.percentile(ratio,[16,50,84]).tolist(),
            'comparison':'4300-6800 A, positive legacy flux; exclude sky lines and Halpha; no renormalization',
            'n_bins':int(good.sum())}


def make_report(run_directory, legacy_root, standards_directory=None, reference_root='trunk/src/ntt'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    output=Path(run_directory).resolve()
    run=json.loads((output/'run.json').read_text())
    results=run['results']
    summary={'n_science':len(results),'n_errors':len(run['errors']),
             'n_historical_apertures':sum(r['target']['association']=='historical_aperture' for r in results),
             'n_independent_sky_checks':sum(r['sky_flexure']['held_out_6363_pass'] for r in results),
             'comparisons':{},'standards':[]}
    for r in results:
        summary['comparisons'][r['object']]=compare_legacy(r,legacy_root)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'figure.facecolor':'white','savefig.facecolor':'white'})
    blue,orange='#205b81','#bf613b'
    nrows=int(np.ceil(len(results)/3))
    fig,axes=plt.subplots(nrows,3,figsize=(14,2.65*nrows),layout='constrained')
    for ax,r in zip(axes.flat,results):
        w,b,h=read_flux(r['product'])
        ax.plot(w,b[0]/1e-16,color=blue,lw=.65)
        ax.fill_between(w,(b[0]-b[3])/1e-16,(b[0]+b[3])/1e-16,color=blue,alpha=.12,lw=0)
        old=summary['comparisons'][r['object']]
        if old:
            ow,ob,_=read_flux(old['path']);ax.plot(ow,ob[0]/1e-16,color=orange,lw=.7,alpha=.75)
        label='aperture confirmed' if r['target']['association']=='historical_aperture' else 'target unverified'
        ax.set_title(f"{r['object']} · {r['grism']}\nS/N {r['median_native_snr_4000_8500']:.1f} · {label}",fontsize=10,loc='left')
        good=np.isfinite(b[0])&(w>4000)&(w<8500)
        lo,hi=np.percentile(b[0][good]/1e-16,[2,98]); span=max(hi-lo,0.01)
        ax.set_ylim(lo-.2*span,hi+.2*span);ax.set_xlim(3900,9100 if r['grism']=='Gr13' else 7450)
        ax.axhline(0,lw=.4,color='gray');ax.grid(alpha=.12)
    for ax in list(axes.flat)[len(results):]:ax.set_visible(False)
    fig.supylabel(r'$F_\lambda$ [$10^{-16}$ erg s$^{-1}$ cm$^{-2}$ $\AA^{-1}$]')
    fig.supxlabel(r'Observed air wavelength [$\AA$]')
    fig.suptitle('EFOSC2 · 14 November 2024 · experimental rapid reduction\nBlue: PypeIt extraction + archived calibration   |   Orange: existing IRAF spectrum',fontsize=13)
    for ext in ('png','pdf'):fig.savefig(output/('night-overview.'+ext),dpi=170)
    plt.close(fig)

    example=next(r for r in results if r['object']=='SN2023xxj')
    w,b,h=read_flux(example['product']);old=summary['comparisons'][example['object']]
    ow,ob,_=read_flux(old['path'])
    images=np.load(output/'native'/(Path(example['product']).name[:-7]+'_images.npz'))
    fig=plt.figure(figsize=(11,8.2),layout='constrained')
    gs=fig.add_gridspec(3,1,height_ratios=[1.35,.9,1.])
    ax=fig.add_subplot(gs[0]);ax.plot(w,b[0]/1e-16,c=blue,lw=.9,label='PypeIt + archive bridge')
    ax.fill_between(w,(b[0]-b[3])/1e-16,(b[0]+b[3])/1e-16,color=blue,alpha=.17,lw=0,label='Propagated 1σ')
    ax.plot(ow,ob[0]/1e-16,c=orange,lw=.85,alpha=.8,label='Existing IRAF reduction')
    ax.set(xlim=(3900,9100),ylim=(-.05,1.4),ylabel=r'$F_\lambda$ [$10^{-16}$ cgs / $\AA$]')
    ax.legend(frameon=False,ncol=3,fontsize=9)
    ax.set_title(f"SN2023xxj · Gr13 · 2700 s · median S/N {example['median_native_snr_4000_8500']:.1f}/pixel\nUnscaled comparison; median new/legacy flux = {old['ratio_p16_p50_p84'][1]:.3f} in the stated continuum windows",loc='left')
    ax.grid(alpha=.15)
    ax=fig.add_subplot(gs[1],sharex=ax)
    trace=np.median(images['trace']);lo=max(0,int(trace)-22);hi=min(images['data'].shape[1],int(trace)+23)
    residual=images['data']-images['sky']
    wav=images['waveair'][:,int(trace)]
    v=np.percentile(residual[:,lo:hi],[5,99])
    ax.imshow(residual[:,lo:hi].T,origin='lower',aspect='auto',extent=[wav[0],wav[-1],lo,hi],
              vmin=v[0],vmax=v[1],cmap='gray_r',interpolation='nearest')
    ax.plot(wav,images['trace'],lw=.7,color=orange,alpha=.9,label='PypeIt trace')
    ax.set_ylabel('Spatial pixel\n(cropped frame)');ax.legend(loc='upper right',frameon=False,fontsize=8)
    ax.set_title('Sky-subtracted detector strip; horizontal axis is approximate before rectification',fontsize=9,loc='left')
    ax=fig.add_subplot(gs[2])
    for grism,color in [('Gr13',blue),('Gr11',orange)]:
        selected=[r for r in results if r['grism']==grism and r['sky_flexure']['held_out_6363_residual_angstrom'] is not None]
        ax.scatter([float(Time(r['date_obs']).datetime.hour+Time(r['date_obs']).datetime.minute/60) for r in selected],
                   [r['sky_flexure']['held_out_6363_residual_angstrom'] for r in selected],s=32,c=color,label=grism)
    ax.axhline(0,lw=.8,c='gray');ax.axhspan(-3,3,color=blue,alpha=.06)
    ax.set(xlabel='15 November 2024 · UTC hour',ylabel='[O I] 6363 residual [Å]',ylim=(-3.2,3.2))
    ax.set_title('Independent sky-line check after correcting with 5577 and 6300 Å (11 measurable exposures)',fontsize=10,loc='left')
    ax.legend(frameon=False,ncol=2);ax.grid(alpha=.15)
    for ext in ('png','pdf'):fig.savefig(output/('SN2023xxj-validation.'+ext),dpi=180)
    plt.close(fig)

    if standards_directory:
        standards=json.loads((Path(standards_directory)/'run.json').read_text())
        refpath=Path(reference_root)/'standard/MAB/ml745a.dat'
        ref=np.loadtxt(refpath); reference_flux=10**(-.4*(ref[:,1]+48.6))*2.99792458e18/ref[:,0]**2
        fig,axes=plt.subplots(2,1,figsize=(10,6),layout='constrained',sharex=True)
        for r,color in zip(standards['results'],[orange,blue]):
            if r['object']!='L745a':continue
            sw,sb,sh=read_flux(r['product']);expected=np.interp(sw,ref[:,0],reference_flux)
            ratio=sb[0]/expected;good=np.isfinite(ratio)&(sw>4300)&(sw<6800)
            stats=np.percentile(ratio[good],[16,50,84]).tolist()
            summary['standards'].append({'object':r['object'],'grism':r['grism'],
                'median_ratio':stats[1],'ratio_p16_p50_p84':stats,'range_air_angstrom':[4300,6800],
                'reference':str(refpath.resolve()),'reference_sha256':sha256(refpath),
                'conversion':'AB magnitude -> Fnu -> Flambda using c=2.99792458e18 A/s',
                'limitation':'Narrow-slit comparison includes slit losses; source association remains nominal.'})
            axes[0].plot(sw,sb[0]/1e-14,c=color,lw=.8,label=f"{r['grism']} extracted")
            axes[1].plot(sw,ratio,c=color,lw=.8,label=f"{r['grism']}: median {stats[1]:.3f}")
        axes[0].plot(ref[:,0],reference_flux/1e-14,c='black',ls='--',lw=.8,label='Archived L745a reference')
        axes[0].set(ylabel=r'$F_\lambda$ [$10^{-14}$ cgs / $\AA$]',title='L745a · independent reference-flux check · no renormalization')
        axes[1].set(xlim=(4000,8500),ylim=(.6,1.3),ylabel='Extracted / reference',xlabel='Observed air wavelength [Å]')
        axes[1].axhline(1,c='gray',lw=.7)
        for ax in axes:ax.legend(frameon=False);ax.grid(alpha=.15)
        for ext in ('png','pdf'):fig.savefig(output/('standard-validation.'+ext),dpi=170)
        plt.close(fig)
        summary['standard_attempts']={'reduced':len(standards['results']),'failed':len(standards['errors']),
                                      'skipped':len(standards['skipped'])}
    (output/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary
