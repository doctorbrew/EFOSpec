"""Measured native-delivery diagnostics, separate from scientific approval."""
import json
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.io import fits

from .inventory import sha256


def wavelength_coverage(wave, valid, *, lower=4000., upper=8500., width=500.):
    """Count support, including empty wavelength intervals, without filling gaps."""
    wave, valid = np.asarray(wave, float), np.asarray(valid, bool)
    if wave.ndim != 1 or wave.shape != valid.shape or not np.all(np.diff(wave)>0):
        raise ValueError('coverage requires matching, increasing one-dimensional arrays')
    rows=[]
    for lo in np.arange(lower,upper,width):
        hi=min(lo+width,upper); selected=(wave>=lo)&(wave<hi)
        count=int(selected.sum()); supported=int((selected&valid).sum())
        rows.append(dict(lower_air_angstrom=float(lo),upper_air_angstrom=float(hi),
                         samples=count,valid_samples=supported,
                         valid_fraction=float(supported/count) if count else 0.))
    return rows


def standard_recovery(frame, spectrum, response, reference):
    """Evaluate a separately recorded standard; distinguish training from holdout.

    Ratios are diagnostic: different slit losses/transparency and unresolved
    reference features prevent interpreting them as absolute accuracy alone.
    """
    from pypeit.core.wave import vactoair
    from .native_flux import response_factor
    wavevac=np.asarray(spectrum.OPT_WAVE,float)
    air=vactoair(wavevac*u.AA).value
    h=frame['metadata']
    factor,support=response_factor(air,response,h['EXPTIME'],h['ESO TEL AIRM START'])
    refvac=np.asarray(reference['wave'],float)
    refair=vactoair(refvac*u.AA).value
    # Reference flux is PypeIt's 1e-17 cgs per vacuum-A convention.
    truth=np.interp(air,refair,np.asarray(reference['flux'],float)*1e-17
                    *np.gradient(refvac)/np.gradient(refair),left=np.nan,right=np.nan)
    flux=np.asarray(spectrum.OPT_COUNTS)*factor
    valid=support&spectrum.OPT_MASK&(spectrum.OPT_COUNTS_IVAR>0)&np.isfinite(flux)&(truth>0)
    ratio=np.divide(flux,truth,out=np.full_like(flux,np.nan),where=valid)
    record=json.loads(Path(response).with_suffix('.json').read_text())
    independent=frame['sha256']!=record['standard_sha256']
    from pypeit.core import flux_calib
    from .flux_validation import transfer_summary
    # Overall closure can hide colour errors and telluric absorption. Use the
    # same explicit stellar/atmospheric masks as response fitting for continuum QA.
    if valid.any():
        bad,stellar,telluric=flux_calib.get_mask(wavevac,np.asarray(spectrum.OPT_COUNTS),
            np.asarray(spectrum.OPT_COUNTS_IVAR),valid.copy(),mask_hydrogen_lines=True,
            mask_helium_lines=True,mask_telluric=True,hydrogen_mask_wid=40.)
        continuum=valid&bad&stellar&telluric
    else:
        continuum=np.zeros_like(valid)
    transfer=transfer_summary(air,ratio,valid,continuum)
    bins=[]
    for lo,hi in ((4600,4800),(5100,5300),(5600,5800),(6000,6200),
                  (6600,6800),(7000,7200),(8000,8200)):
        m=continuum&(air>=lo)&(air<hi)
        bins.append(dict(band_air_angstrom=[lo,hi],samples=int(m.sum()),
                         median_ratio=float(np.median(ratio[m])) if m.any() else None))
    return dict(raw=frame['path'],raw_sha256=frame['sha256'],
                reference_name=reference['name'],independent_exposure=independent,
                interpretation='held-out exposure' if independent else 'training-standard closure only',
                valid_samples=int(valid.sum()),continuum_bands=bins,
                median_ratio=float(np.median(ratio[valid])) if valid.any() else None,
                median_ratio_scope='All supported samples, including absorption; use continuum_transfer for colour/scale QA.',
                continuum_transfer=transfer,
                independent_reference_star=(reference['name']!=record.get('standard_name'))
                    if record.get('standard_name') else None,
                science_validated=False), dict(waveair=air,ratio=ratio,valid=valid,continuum=continuum)


def assess_run(run):
    """Recheck raw identity and quantify supported delivery and sky residuals."""
    from pypeit.wavecalib import WaveCalib
    from .native_wavelength import validate_solution
    run=Path(run);manifest=json.loads((run/'run.json').read_text())
    if manifest.get('method')!='native_raw_calibration_with_PypeIt_extraction':
        raise ValueError('acceptance diagnostics require a native raw-calibration run')
    if len(manifest['results'])!=1 or manifest['errors']:
        raise ValueError('acceptance diagnostics require one completed native exposure')
    result=manifest['results'][0];groups=[]
    for directory in result['calibration']['groups']:
        directory=Path(directory);record=json.loads((directory/'calibration.json').read_text())
        for name,digest in record['processed_files'].items():
            path=(directory/name).resolve()
            if not path.is_relative_to(directory.resolve()) or sha256(path)!=digest:
                raise ValueError('native calibration product changed')
        files=list((directory/'Calibrations').glob('WaveCalib_*.fits'))
        if len(files)!=1:raise ValueError('ambiguous native wavelength calibration')
        fit=WaveCalib.from_file(files[0]).wv_fits[0]
        groups.append(validate_solution(fit,record['setup']['grism'],filter_name=record['setup']['filter']))
    hashes=result['calibration']['raw_inputs']
    unchanged=all(sha256(Path(p))==digest for p,digest in hashes.items())
    if not unchanged:raise ValueError('raw calibration/science input changed')
    product=Path(result['product'])
    with fits.open(product) as hdus:
        h=hdus[0].header;flux=hdus[0].data[0,0];sigma=hdus[0].data[3,0]
        wave=h['CRVAL1']+np.arange(len(flux))*h['CD1_1']
        valid=hdus['VALID'].data[0].astype(bool)
        consistent=bool(np.all(np.isfinite(flux[valid])&np.isfinite(sigma[valid])&(sigma[valid]>0)))
        conventions=bool(h['WAVEMED']=='air' and h['FLUXCAL']=='NATIVE' and hdus[0].data.shape[:2]==(4,1))
    coverage=wavelength_coverage(wave,valid)
    image_path=run/'native'/(product.name[:-7]+'_images.npz')
    if sha256(image_path)!=result['images_sha256']:raise ValueError('saved detector planes changed')
    with np.load(image_path) as n:
        keep=n['sky_input_mask']&(n['mask']==0)&(n['ivar']>0)
        pulls=(n['data']-n['sky']-n['object_model'])*np.sqrt(n['ivar'])
        keep&=np.isfinite(pulls)
        values=pulls[keep];median=float(np.median(values)) if values.size else None
        scatter=float(1.4826*np.median(abs(values-median))) if values.size else None
    return dict(schema_version=1,run=str(run.resolve()),product=str(product),
                raw_hashes_unchanged=unchanged,arc_groups=groups,
                sky=result['sky_flexure'],coverage=coverage,
                valid_flux_fraction=float(valid.mean()),valid_flux_and_sigma_finite=consistent,
                delivery_conventions_preserved=conventions,
                residual_noise=dict(samples=int(values.size),median_pull=median,robust_sigma=scatter,
                    interpretation='in-sample sky/model residuals, not independent uncertainty coverage'),
                diagnostic_targets=dict(band_air_angstrom=[4000,8500],minimum_fraction_per_500A_bin=.8),
                broad_band_coverage_pass=all(row['valid_fraction']>=.8 for row in coverage),
                science_validated=False,
                limitations=['Target position remains an unverified operator hypothesis.',
                    'Flux accuracy needs independent standards and slit/transparency assessment.',
                    'Statistical errors omit response, profile and calibration systematics.'])


def plot_acceptance(report, standard_arrays, output):
    from .figure_style import house_style,save_qc,COLORS
    import matplotlib.pyplot as plt
    @house_style
    def draw():
        fig,axes=plt.subplots(2,1,figsize=(12,9),layout='constrained')
        rows=report['coverage'];x=[(r['lower_air_angstrom']+r['upper_air_angstrom'])/2 for r in rows]
        axes[0].bar(x,[r['valid_fraction'] for r in rows],width=450,color=COLORS[0])
        axes[0].axhline(.8,color='0.4',ls='--');axes[0].set_ylim(0,1.05)
        axes[0].set_ylabel('Valid flux fraction');axes[0].set_title('Native calibration support')
        for index,(label,arrays) in enumerate(standard_arrays):
            axes[1].plot(arrays['waveair'],arrays['ratio'],label=label,lw=1.4,
                         color=COLORS[index%len(COLORS)])
        axes[1].axhline(1,color='0.4',ls='--');axes[1].set_ylabel('Recovered / reference flux')
        for ax in axes:ax.set_xlim(4000,8500);ax.set_xlabel('Air wavelength (Å)')
        save_qc(fig,output,'native-acceptance','EFOSC2');plt.close(fig)
    draw()
