"""Measure EFOSC calibration diagnostics; never certify source identity or flux accuracy.

Run with the PyRAF environment on disposable reduction outputs. Reference AB
magnitudes and extinction come from this repository. Sky-line wavelengths are
air wavelengths. Sky residuals are internal checks, not held-out arc tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

import numpy as np
from astropy.io import fits
from scipy.optimize import curve_fit


def wavelength(header, n):
    return header['CRVAL1'] + (np.arange(n) + 1 - header.get('CRPIX1', 1)) * header['CD1_1']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sky_line(wave, flux, rest):
    use = np.abs(wave - rest) < 35
    x, y = wave[use] - rest, flux[use]
    if len(x) < 10 or not np.isfinite(y).all():
        return {'rest_air_A': rest, 'status': 'insufficient finite samples'}
    scale = np.ptp(y)
    if scale <= 0:
        return {'rest_air_A': rest, 'status': 'no signal'}
    y = y / scale
    def model(x, amp, offset, sigma, intercept, slope):
        return amp * np.exp(-0.5 * ((x-offset)/sigma)**2) + intercept + slope*x
    lower = [0, -20, 1, -np.inf, -np.inf]
    upper = [np.inf, 20, 20, np.inf, np.inf]
    try:
        p, cov = curve_fit(model, x, y, p0=[1, x[np.argmax(y)], 6, np.median(y), 0],
                           bounds=(lower, upper), maxfev=10000)
        residual = y-model(x, *p)
        snr = p[0]/max(np.std(residual), np.finfo(float).eps)
        constrained = abs(p[1]) > 19.9 or p[2] < 1.01 or p[2] > 19.9
        return dict(rest_air_A=rest, offset_A=float(p[1]), formal_error_A=float(np.sqrt(cov[1, 1])),
                    fwhm_A=float(2.35482*p[2]), peak_to_residual_rms=float(snr),
                    status='review' if constrained or snr < 5 else 'measured', bound_constrained=bool(constrained))
    except (RuntimeError, ValueError) as exc:
        return {'rest_air_A': rest, 'status': 'fit failed', 'reason': str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standards', required=True, type=Path)
    parser.add_argument('--science', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    standards, science, out = (p.resolve() for p in (args.standards, args.science, args.output))
    out.mkdir(parents=True, exist_ok=False)
    (out/'cache').mkdir()
    root = Path(__file__).resolve().parents[1]
    ref = root/'trunk/src/ntt/standard/MAB/ml745a.dat'
    sources = sorted(set(standards.glob('*.fits')) | set(science.glob('*.fits')) | set(science.glob('database/ap*')) | {ref,root/'trunk/src/ntt/standard/extinction/lasilla2.txt'})
    before = {str(p): sha(p) for p in sources}
    os.environ.update(PYRAF_NO_DISPLAY='1', MPLBACKEND='Agg', iraf='/usr/local/lib/iraf/',
                      PYRAF_CLCACHE_PATH=str(out/'cache'))
    os.chdir(out)
    from pyraf import iraf
    iraf.noao(_doprint=0); iraf.imred(_doprint=0); iraf.specred(_doprint=0)
    import ntt
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from plot_style import set_plotparams, styled_legend, savefig_light, HIROSHIGE

    report = dict(scientific_acceptance=False,inputs=before, flux_transfer=[], sky_lines=[], apertures=[], product_checks=[])
    reference = np.loadtxt(ref)
    reference_flux = 10**(-0.4*(reference[:, 1]+48.6))*2.99792458e18/reference[:, 0]**2
    # Diagnostic continuum windows only; no universal acceptance tolerance implied.
    windows = [(4500,4800), (5100,5500), (6000,6200), (8000,8400)]
    report['continuum_windows_A'] = windows
    fig, axes = plt.subplots(3, 1, figsize=(13, 15), sharex=True)
    for ax, (grism, filt) in zip(axes, [('Gr11','Free'), ('Gr13','Free'), ('Gr16','OG530')]):
        exposure = next(standards.glob(f'tL745a*{grism}_{filt}*_ex.fits'))
        shutil.copy2(exposure, out/exposure.name)
        h = fits.getheader(exposure)
        for j, star in enumerate(['l745a','vma2']):
            sensitivity = next(standards.glob(f'sens*{grism}_{filt}_{star}_*_1.fits'))
            shutil.copy2(sensitivity, out/sensitivity.name)
            target = f'cross_{grism}_{star}.fits'
            iraf.specred.calibrate(input=exposure.name, output=target, sensiti=sensitivity.name,
                                  extinct='yes', flux='yes', ignorea='yes', fnu='no',
                                  extinction=str(Path(ntt.__path__[0])/'standard/extinction/lasilla2.txt'),
                                  observatory='lasilla', airmass=ntt.util.readkey3(h,'airmass'),
                                  exptime=h['EXPTIME'])
            data, header = fits.getdata(target, header=True)
            wave = wavelength(header, data.shape[-1])
            expected = np.interp(wave, reference[:,0], reference_flux, left=np.nan, right=np.nan)
            ratio = data[0,0]/expected
            samples=[]
            for lo, hi in windows:
                mask=(wave>=lo)&(wave<=hi)&np.isfinite(ratio)
                if mask.sum()>=5:
                    samples.append(dict(lo_A=lo,hi_A=hi,n=int(mask.sum()),median_ratio=float(np.median(ratio[mask])),
                                        p16=float(np.percentile(ratio[mask],16)),p84=float(np.percentile(ratio[mask],84))))
            report['flux_transfer'].append(dict(grism=grism,filter=filt,target='L745a',calibrator=star,
                                               independent_standard=(star=='vma2'),sensitivity=sensitivity.name,bands=samples))
            np.savetxt(f'ratio_{grism}_{star}.csv',np.column_stack([wave,ratio]),delimiter=',',header='wavelength_A,flux_over_reference')
            valid=(wave>=4000)&(wave<=8500)&np.isfinite(ratio)
            ax.plot(wave[valid],ratio[valid],color=HIROSHIGE(float(0.15+0.6*j)),lw=1.4,
                    label='L745a response (self-check)' if star=='l745a' else 'vma2 response (transfer)')
        ax.axhline(1,color='0.4',ls='--',lw=1)
        for lo,hi in windows:ax.axvspan(lo,hi,color='0.5',alpha=0.07)
        ax.set_title(f'L745a: {grism}/{filt}')
        ax.set_ylabel('Flux / reference')
        ax.set_xlim(4000,8500)
        set_plotparams(ax,xticks=(1000,200),yticks=None)
        styled_legend(ax,loc='upper left')
    axes[-1].set_xlabel(r'Wavelength (\AA)')
    fig.tight_layout();savefig_light(fig,out/'standard_transfer');plt.close(fig)

    profiles=[]
    for exposure in sorted(science.glob('tAT*_ex.fits')):
        data,h=fits.getdata(exposure,header=True)
        wave=wavelength(h,data.shape[-1])
        lines=[sky_line(wave,data[2,0],rest) for rest in [5577.338,6300.304,6363.776]]
        report['sky_lines'].append(dict(file=exposure.name,object=h['OBJECT'],lines=lines))
        base=exposure.name.replace('_ex.fits','.fits')
        ap=science/'database'/('ap'+Path(base).stem)
        txt=ap.read_text()
        center=float(re.search(r'\n\s*center\s+(\S+)',txt)[1])
        bounds=[float(re.search(r'\n\s*'+key+r'\s+(\S+)',txt)[1]) for key in ['low','high']]
        image,ih=fits.getdata(science/base,header=True)
        # Median spatial profile of the central half of dispersion samples.
        strip=image[len(image)//4:3*len(image)//4].astype(float)
        profile=np.median(strip-np.median(strip,axis=1)[:,None],axis=0)
        record=dict(object=h['OBJECT'],center_pixel=center,lower_offset=bounds[0],upper_offset=bounds[1],
                    spatial_pixels=image.shape[1],identity_verified=False)
        report['apertures'].append(record);profiles.append((record,profile))
    fig,axes=plt.subplots(1,2,figsize=(17,6))
    for ax,(record,profile) in zip(axes,profiles):
        x=np.arange(len(profile))+1
        ax.plot(x,profile,color=HIROSHIGE(0.15),lw=1.3)
        ax.axvline(record['center_pixel'],color=HIROSHIGE(0.75),ls='--',label='Automatic aperture')
        ax.set_title(record['object']);ax.set_xlabel('Spatial pixel (IRAF, 1-based)');ax.set_ylabel('Median counts above row median')
        set_plotparams(ax,xticks=(200,50),yticks=None);styled_legend(ax)
    fig.tight_layout();savefig_light(fig,out/'automatic_apertures');plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,6))
    for j,entry in enumerate(report['sky_lines']):
        good=[p for p in entry['lines'] if p['status']=='measured']
        ax.plot([p['rest_air_A'] for p in good],[p['offset_A'] for p in good],ls='none',marker='o',
                mfc='white',mec=HIROSHIGE(float(0.15+j*0.6)),ms=10,mew=1.8,label=entry['object'])
    ax.axhline(0,color='0.4',ls='--');ax.set_xlabel(r'Air sky-line wavelength (\AA)');ax.set_ylabel(r'Centroid offset (\AA)')
    set_plotparams(ax,xticks=(200,50),yticks=None);styled_legend(ax)
    fig.tight_layout();savefig_light(fig,out/'sky_residuals');plt.close(fig)
    for path in sorted(science.glob('tAT*_e.fits')):
        data,h=fits.getdata(path,header=True)
        ascii_data=np.loadtxt(path.with_suffix('.asci'))
        uncorrected=fits.getdata(str(path).replace('_e.fits','_f.fits'))
        usable=np.abs(uncorrected[0,0])>0
        expected_sigma=uncorrected[3,0,usable]*(data[0,0,usable]/uncorrected[0,0,usable])
        report['product_checks'].append(dict(file=path.name,finite=bool(np.isfinite(data).all()),
             shape=list(data.shape),telluric_sigma_scales_with_flux=bool(np.allclose(data[3,0,usable],expected_sigma,rtol=2e-5,atol=0)),
             negative_sigma_pixels_0based=np.flatnonzero(data[3,0]<0).tolist(),sigma_nonnegative=bool(np.all(data[3]>=0)),
             ascii_flux_agrees=bool(np.allclose(ascii_data[:,1],data[0,0],rtol=1e-6,atol=0)),
             ascii_wavelength_agrees=bool(np.allclose(ascii_data[:,0],wavelength(h,data.shape[-1]),atol=0.01,rtol=0))))
    report['standard_cleaning_checks']=[]
    for path in sorted(standards.glob('t*_clean.fits')):
        original=standards/path.name.replace('_clean.fits','_ex.fits')
        atmosphere=standards/('atmo_'+original.name)
        if original.exists() and atmosphere.exists():
            expected=fits.getdata(original)[0,0]/fits.getdata(atmosphere)[0,0]
            report['standard_cleaning_checks'].append(dict(file=path.name,own_atmosphere_agrees=bool(np.allclose(fits.getdata(path)[0,0],expected,rtol=2e-5,atol=0))))
    report['sources_unchanged']=all(sha(Path(p))==digest for p,digest in before.items())
    report['limitations']=['No source-identity approval', 'Sky lines also inform pipeline shifts; not held-out calibration',
                           'Formal centroid errors exclude wavelength systematics', 'Narrow slit, transparency and extinction affect transfer',
                           'No absolute-flux or telluric acceptance threshold imposed']
    (out/'validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(out/'validation.json')


if __name__=='__main__':
    main()
