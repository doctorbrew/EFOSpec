"""Full-spectrum PypeIt sky diagnostics and explicit quality-gated acceptance."""
from pathlib import Path
import numpy as np


def compare(data, waveair, good, *, ranges=((5200.,9000.),(5200.,6800.),(6800.,7900.),(7900.,9000.))):
    from astropy import units as u
    from astropy.stats import sigma_clip
    from pypeit.core.wave import airtovac
    from pypeit.core.flexure import spec_flex_shift
    from pypeit.onespec import OneSpec
    from pypeit import dataPaths
    from .inventory import sha256
    if data.shape!=waveair.shape or good.shape!=data.shape or data.ndim!=2:
        raise ValueError('Sky comparison arrays must share a two-dimensional grid')
    if not np.all(np.diff(waveair,axis=0)>0):raise ValueError('Wavelength grid must increase')
    wave=waveair[:,data.shape[1]//2]
    samples=[]
    for col in range(data.shape[1]):
        valid=good[:,col]&np.isfinite(data[:,col])
        # Invalid pixels remain NaN; do not interpolate across masked gaps.
        samples.append(np.interp(wave,waveair[:,col],np.where(valid,data[:,col],np.nan),left=np.nan,right=np.nan))
    clipped=sigma_clip(np.array(samples),sigma=3,maxiters=5,axis=0,cenfunc='median',stdfunc='mad_std')
    sky=np.ma.mean(clipped,axis=0).filled(np.nan);support=np.ma.count(clipped,axis=0)
    valid=np.isfinite(sky)&(support>=10)
    vacuum=airtovac(wave*u.AA).value
    template=dataPaths.sky_spec.get_file_path('paranal_sky.fits')
    records=[];arrays=dict(wave_vacuum=vacuum,sky_electron=sky,valid=valid)
    for index,(lo,hi) in enumerate(ranges):
        use=valid&(vacuum>=lo)&(vacuum<=hi)
        record=dict(range_vacuum_angstrom=[lo,hi],samples=int(use.sum()),coverage_fraction=float(use.sum()/max(1,np.sum((vacuum>=lo)&(vacuum<=hi)))))
        if use.sum()<60:
            record.update(status='insufficient_coverage');records.append(record);continue
        try:
            spectrum=OneSpec(vacuum[use],vacuum[use],sky[use],PYP_SPEC='ntt_efosc2',ext_mode='BOX',fluxed=False)
            result=spec_flex_shift(spectrum,sky_file='paranal_sky.fits',mxshft=10,excess_shft='crash')
            if result is None:raise ValueError('No measurable sky correlation')
            shift=float(result['shift'])
            record.update(status='measured',shift_pixels=shift,quality=correlation_quality(result),
                dispersion_angstrom_per_pixel=float(np.median(np.diff(vacuum[use]))),
                approximate_shift_angstrom=shift*float(np.median(np.diff(vacuum[use]))))
            arrays[f'correlation_{index}']=np.asarray(result['corr'])
            arrays[f'lags_{index}']=np.asarray(result['subpix'])
            # Public PypeIt return values, copied before any diagnostic processing.
            for key,value in dict(matched_wave=result['sky_spec'].wave,
                    observed=result['sky_spec'].flux,template=result['arx_spec'].flux,
                    fit_coefficients=result['polyfit'].fitc,
                    correlation_centre=result['corr_cen']).items():
                arrays[f'{key}_{index}']=np.array(value,copy=True)
        except (ValueError,RuntimeError) as exc:record.update(status='failed',reason=str(exc))
        records.append(record)
    return dict(method='pypeit.core.flexure.spec_flex_shift',template=str(template),template_sha256=sha256(template),
        wavelength_medium='vacuum',ranges=records,status='diagnostic_only',applied=False,
        limitations=['Full-spectrum correlation is not a line-by-line acceptance test.',
            'Regional shifts test consistency; discrepancies can indicate blends, sky variability, contamination or wavelength distortion.',
            'No new wavelength correction or flux acceptance is applied by this diagnostic.']),arrays


def run_comparison(run, raw, recipe, output):
    """Hash-bound full-sky diagnostic from the reviewed local background bands."""
    from .revisions import FailedExposure
    from .recipes import validate_recipe, sky_mask
    from .native_calibration import save_json
    from .inventory import sha256
    from .run_record import snapshot_sources
    e=FailedExposure(run,raw);recipe=validate_recipe(recipe,e.window,e.hashes)
    if e.context.processed is None:raise ValueError('Native calibrated pixels required')
    if len(recipe['sky']['include'])!=2:raise ValueError('Select two reviewed sky bands')
    good=sky_mask(recipe,e.window)&~e.context.processed['bad_pixels'].astype(bool)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    record,arrays=compare(e.context.data,e.context.waveair,good)
    record.update(parent_run=str(e.run),parent_sha256=sha256(e.run/'run.json'),
        raw_sha256=e.frame['sha256'],target=e.result['object'],input_sha256=e.hashes,
        source_sha256=snapshot_sources(output))
    save_json(output/'recipe.json',recipe)
    np.savez_compressed(output/'comparison.npz',**arrays)
    if FailedExposure(run,raw).hashes!=e.hashes:raise ValueError('Sky comparison inputs changed')
    save_json(output/'comparison.json',record)
    return record


def correlation_quality(result):
    """Independent normalized correlation checks; thresholds are versioned below."""
    from scipy.ndimage import gaussian_filter1d
    observed=np.asarray(result['sky_spec'].flux,float)
    template=np.asarray(result['arx_spec'].flux,float)
    # Remove broad continuum; retain resolved sky features, not the host pedestal.
    a=observed-gaussian_filter1d(observed,15.)
    b=template-gaussian_filter1d(template,15.)
    x=np.arange(len(a));lags=np.arange(-10.,10.01,.25);scores=[]
    for lag in lags:
        shifted=np.interp(x+lag,x,b,left=np.nan,right=np.nan)
        use=(x>=20)&(x<len(x)-20)&np.isfinite(a)&np.isfinite(shifted)
        aa=a[use]-np.mean(a[use]);bb=shifted[use]-np.mean(shifted[use])
        norm=np.linalg.norm(aa)*np.linalg.norm(bb)
        scores.append(float(aa@bb/norm) if norm>1e-12 else 0.)
    scores=np.array(scores);best=int(np.argmax(scores));shift=float(result['shift'])
    competitors=abs(lags-lags[best])>=4
    margin=float(scores[best]-scores[competitors].max())
    return dict(peak_correlation=float(scores[best]),peak_lag_pixels=float(lags[best]),
        separated_peak_margin=margin,pypeit_peak_disagreement_pixels=float(abs(lags[best]-shift)),
        concave_peak=bool(result['polyfit'].fitc[2]<0),edge_peak=bool(abs(lags[best])>=9.5))


def quality_passed(record):
    """Conservative explicit policy v1; evaluated again when accepting products."""
    ranges=record.get('ranges',[])
    if len(ranges)!=4:return False
    for r in ranges:
        q=r.get('quality',{})
        values=[r.get('approximate_shift_angstrom',np.nan),q.get('peak_correlation',np.nan),
                q.get('separated_peak_margin',np.nan),q.get('pypeit_peak_disagreement_pixels',np.nan)]
        if (r.get('status')!='measured' or not np.isfinite(values).all()
                or r.get('coverage_fraction',0)<.9 or abs(values[0])>20
                or values[1]<.5 or values[2]<.05 or values[3]>1.
                or not q.get('concave_peak') or q.get('edge_peak',True)):return False
    shifts=[r['approximate_shift_angstrom'] for r in ranges]
    return bool(np.ptp(shifts[1:])<=3 and max(abs(np.array(shifts[1:])-shifts[0]))<=3)


def localized_acceptance(before,after):
    """V2: one estimator outlier, corroborated across all normalized sky regions.

    This is cross-estimator consistency on the same sky, not independent data.
    Keep v1 unchanged for replay of historical acceptance records.
    """
    excluded=set()
    for record,corrected in ((before,False),(after,True)):
        rows=record.get('ranges',[])
        if len(rows)!=4:return None
        # Reuse every v1 per-region quality gate, without the inter-region veto.
        if any(not quality_passed({'ranges':[r]*4}) for r in rows):return None
        shifts=np.array([r['approximate_shift_angstrom'] for r in rows])
        normalized=[]
        for r in rows:
            q=r['quality'];disp=r.get('dispersion_angstrom_per_pixel',np.nan)
            lag=q.get('peak_lag_pixels',np.nan)
            if not np.isfinite([disp,lag]).all() or disp<=0:return None
            normalized.append(disp*lag)
        normalized=np.array(normalized)
        if np.ptp(normalized)>3 or np.max(abs(normalized-shifts[0]))>3:return None
        if corrected:
            if abs(shifts[0])>1.5 or np.max(abs(normalized))>1.5:return None
            bad={i for i in range(1,4) if abs(shifts[i])>1.5 or abs(shifts[i]-shifts[0])>3}
        else:bad={i for i in range(1,4) if abs(shifts[i]-shifts[0])>3}
        excluded.update(bad)
        if len(excluded)>1:return None
        retained=[shifts[i] for i in range(1,4) if i not in excluded]
        if np.ptp(retained)>3:return None
    # Recheck both stages against the same exclusion, never pick different subsets.
    if not excluded:return None
    i=next(iter(excluded))
    for record in (before,after):
        shifts=[r['approximate_shift_angstrom'] for j,r in enumerate(record['ranges']) if j!=i]
        if np.ptp(shifts)>3:return None
    return [dict(code='localized_sky_estimator_disagreement',region_index=i,
        range_vacuum_angstrom=before['ranges'][i]['range_vacuum_angstrom'],
        message='One regional PypeIt estimate disagrees; full-range and two regions pass, with normalized correlations consistent in all regions before and after correction.')]


def validation_warnings(before,after):
    if quality_passed(before) and quality_passed(after) and max(abs(r['approximate_shift_angstrom']) for r in after['ranges'])<=1.5:
        return []
    return localized_acceptance(before,after)


def measure_validated(data,waveair,good):
    from .native_sky import SkyValidationError
    before,before_arrays=compare(data,waveair,good)
    rows=before.get('ranges',[])
    if len(rows)!=4 or not quality_passed({'ranges':[rows[0]]*4}):
        error=SkyValidationError('Full-sky correlation quality or regional consistency failed',[])
        error.diagnostics['full_sky']=before
        error.sky_diagnostic_arrays={'before':before_arrays}
        raise error
    shift=before['ranges'][0]['approximate_shift_angstrom']
    # Existing native products use a scalar air-Angstrom flexure correction.
    # Remeasure on exactly that map; never substitute a pixel-shift approximation silently.
    after,after_arrays=compare(data,waveair+shift,good)
    warnings=validation_warnings(before,after)
    if warnings is None:
        error=SkyValidationError('Corrected full-sky residual check failed',[])
        error.diagnostics.update(full_sky=before,corrected_full_sky=after)
        error.sky_diagnostic_arrays={'before':before_arrays,'after':after_arrays}
        raise error
    return float(shift),dict(validation_policy='full-spectrum',quality_policy='full-sky-v2',warnings=warnings,
        validation_passed=True,shift_angstrom=float(shift),held_out_6363_pass=False,lines=[],
        full_sky=before,corrected_full_sky=after,
        policy='Full-spectrum correction remeasured; at most one regional estimator warning with all normalized residuals checked; 6363 not independently certified')
