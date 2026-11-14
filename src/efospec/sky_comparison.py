"""Full-spectrum PypeIt sky comparison; diagnostic, never automatic acceptance."""
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
        record=dict(range_vacuum_angstrom=[lo,hi],samples=int(use.sum()))
        if use.sum()<60:
            record.update(status='insufficient_coverage');records.append(record);continue
        try:
            spectrum=OneSpec(vacuum[use],vacuum[use],sky[use],PYP_SPEC='ntt_efosc2',ext_mode='BOX',fluxed=False)
            result=spec_flex_shift(spectrum,sky_file='paranal_sky.fits',mxshft=10,excess_shft='crash')
            if result is None:raise ValueError('No measurable sky correlation')
            shift=float(result['shift'])
            record.update(status='measured',shift_pixels=shift,
                approximate_shift_angstrom=shift*float(np.median(np.diff(vacuum[use]))))
            arrays[f'correlation_{index}']=np.asarray(result['corr'])
            arrays[f'lags_{index}']=np.asarray(result['subpix'])
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
