#!/usr/bin/env python3
"""Plot retained native-sample atmospheric transfers and separate science previews."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.figure_style import house_style, save_qc, COLORS
from efospec.inventory import sha256
import matplotlib.pyplot as plt
import numpy as np


@house_style
def draw(path):
    r=json.loads(path.read_text());root=path.parent
    fig,axes=plt.subplots(1,2,figsize=(19,7),layout='constrained')
    ax=axes[0]
    for band,marker,col,label in zip(('O2_B','H2O_7200','O2_A'),('o','s','^'),COLORS,
                                   (r'O$_2$ B',r'H$_2$O 7200',r'O$_2$ A')):
        rows=[x['bands'][band] for x in r['transfers'] if 'bands' in x and 'rms_after' in x['bands'][band]]
        x=np.array([q['rms_before'] for q in rows])*100;y=np.array([q['rms_after'] for q in rows])*100
        ax.plot(x,y,ls='none',marker=marker,ms=9,mfc='white',mec=col,mew=1.6,label=label)
        failed=np.array([not q['passed'] for q in rows]);ax.plot(x[failed],y[failed],'x',color=col,ms=9)
    ax.plot([0,10],[0,10],ls='--',color='.65',lw=1.)
    ax.text(12.,8.7,'Crossed points fail the transfer gate',fontsize=15,ha='center')
    ax.set(xlim=(0,27),ylim=(0,10),xlabel='RMS before correction (percent)',ylabel='RMS after correction (percent)',
           title='2026-10-28 / 14 directed standard transfers')
    # Choose the earlier-to-later, different-star pair matching both science setups.
    train=next(f for f in r['fits'] if f['object'].lower()=='vma2' and
               f['setup']['grism']=='Gr13' and f['setup']['filter']=='Free' and f['setup']['slit']=='slit1.0')
    transfer=next(t for t in r['transfers'] if t['training_raw']==train['raw'] and t['independent_star'])
    file=root/transfer['arrays']
    if sha256(file)!=transfer['arrays_sha256']:raise ValueError('transfer arrays changed')
    a=np.load(file);w=a['wave_air'];valid=a['valid']
    before=np.where(valid,a['ratio'],np.nan);after=np.where(valid,a['corrected'],np.nan)
    sigma=np.sqrt(a['variance']);ax=axes[1]
    ax.plot(w,before,color=COLORS[0],lw=1.7,label='Before')
    ax.plot(w,after,color=COLORS[1],lw=1.7,label='After')
    ax.fill_between(w,after-sigma,after+sigma,color=COLORS[1],alpha=.18,label=r'Stat. + fit $1\sigma$')
    ax.axhline(1.,ls='--',color='.6',lw=1.)
    domain=(w>=7500)&(w<=7820)&valid
    ymin=min(np.nanmin(before[domain]),np.nanmin(after[domain]-sigma[domain]))-.04
    ax.set(xlim=(7500,7820),ylim=(ymin,1.17),xlabel=r'Air wavelength ($\mathrm{\AA}$)',ylabel='Observed / stellar continuum',
           title=r'VMa2 model on L745a / Gr13 / slit1.0')
    save_qc(fig,root,'telluric-transfers','EFOSC2');plt.close(fig)
    if not r['products']:return
    from astropy.io import fits
    fig,axes=plt.subplots(len(r['products']),1,figsize=(15,6*len(r['products'])),squeeze=False,layout='constrained')
    for ax,p in zip(axes[:,0],r['products']):
        if sha256(Path(p['product']))!=p['sha256']:raise ValueError('science preview changed')
        with fits.open(p['product']) as h:
            w=h['TELLURIC'].data['WAVE_AIR'];v=h['VALID'].data[0].astype(bool)
            unit=1e-17
            ax.plot(w,h['UNCORRECTED'].data[0,0]/unit,color=COLORS[0],lw=1.4,label='Original')
            f=np.where(v,h[0].data[0,0]/unit,np.nan);s=h[0].data[3,0]/unit
            ax.plot(w,f,color=COLORS[1],lw=1.4,label='Review correction')
            ax.fill_between(w,f-s,f+s,color=COLORS[1],alpha=.18,label=r'Propagated $1\sigma$')
            domain=(w>=7450)&(w<=7850)&v
            original=h['UNCORRECTED'].data[0,0]/unit
            lo=min(np.nanmin(original[domain]),np.nanmin(f[domain]-s[domain]))
            hi=max(np.nanmax(original[domain]),np.nanmax(f[domain]+s[domain]));pad=(hi-lo)*.1
            ax.set(xlim=(7450,7850),ylim=(lo-pad,hi+pad),xlabel=r'Air wavelength ($\mathrm{\AA}$)',
                   ylabel=r'$F_\lambda$ ($10^{-17}$ cgs / $\mathrm{\AA}$)',
                   title=str(h[0].header.get('OBJECT',Path(p['product']).name))+' / REVIEW: airmass extrapolation')
    save_qc(fig,root,'telluric-science','EFOSC2');plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path)
    draw(p.parse_args().run)
