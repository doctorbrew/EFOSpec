"""Reproducible wavelength-failure evidence; diagnostic trials never accept shifts."""
import json
from pathlib import Path
import numpy as np
from .inventory import sha256
from .native_calibration import save_json


def summarize(record, *, corrected=False):
    """Explain full-sky-v1 gates without replacing its acceptance decision."""
    from .sky_comparison import quality_passed
    rows=record.get('ranges',[]);checks=[]
    for row in rows:
        q=row.get('quality',{});reasons=[]
        for key,limit,minimum in [('peak_correlation',.5,True),
                ('separated_peak_margin',.05,True),('pypeit_peak_disagreement_pixels',1.,False)]:
            value=q.get(key,float('nan'))
            if not np.isfinite(value) or (value<limit if minimum else value>limit):reasons.append(key)
        if row.get('status')!='measured':reasons.append('not_measured')
        if row.get('coverage_fraction',0)<.9:reasons.append('coverage')
        offset=row.get('approximate_shift_angstrom',float('nan'))
        if not np.isfinite(offset) or abs(offset)>20:reasons.append('shift_bound')
        if not q.get('concave_peak') or q.get('edge_peak',True):reasons.append('peak_shape_or_edge')
        if corrected and (not np.isfinite(offset) or abs(offset)>1.5):reasons.append('corrected_residual')
        checks.append(dict(interval=row.get('range_vacuum_angstrom'),offset_angstrom=float(offset) if np.isfinite(offset) else None,
                           failed_checks=reasons))
    shifts=np.array([c['offset_angstrom'] for c in checks],dtype=float);spread=None;discrepant=[]
    if len(shifts)==4 and np.isfinite(shifts).all():
        spread=float(np.ptp(shifts[1:]));discrepant=[i for i in range(1,4) if abs(shifts[i]-shifts[0])>3]
    regional_bad={i for i in range(1,len(checks)) if checks[i]['failed_checks']}|set(discrepant)
    warning=(len(checks)==4 and not checks[0]['failed_checks'] and len(regional_bad)==1
             and np.ptp([shifts[i] for i in range(1,4) if i not in regional_bad])<=3)
    return dict(quality_policy='full-sky-v1',ranges=checks,regional_spread_angstrom=spread,
        regional_spread_limit_angstrom=3.,regions_outside_full_range_tolerance=discrepant,
        localized_warning_candidate=bool(warning),
        accepted=bool(quality_passed(record) and not any(c['failed_checks'] for c in checks)),
        interpretation='Warning candidate identifies localized evidence for review; it does not certify wavelengths or permit a correction.')


def save_failure_packet(output,error,data,waveair,good,*,raw,raw_sha256,target):
    """Called by native reduction only when full-spectrum validation fails."""
    import pypeit
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    arrays=dict(input_data=data,input_waveair=waveair,input_good=good)
    for stage,values in error.sky_diagnostic_arrays.items():
        arrays.update({stage+'__'+key:value for key,value in values.items()})
    np.savez_compressed(output/'arrays.npz',**arrays)
    record=dict(schema_version=1,target=target,raw=raw,raw_sha256=raw_sha256,
        pypeit_version=pypeit.__version__,error=str(error),diagnostics=error.diagnostics,
        arrays_sha256=sha256(output/'arrays.npz'),
        source_sha256={p.name:sha256(p) for p in (Path(__file__),Path(__file__).with_name('sky_comparison.py'))},
        assessment=summarize(error.diagnostics['full_sky']),trial_only=True)
    if 'corrected_full_sky' in error.diagnostics:
        record['corrected_assessment']=summarize(error.diagnostics['corrected_full_sky'],corrected=True)
    save_json(output/'packet.json',record)
    return dict(path=str(output/'packet.json'),sha256=sha256(output/'packet.json'))


def fit_peak(correlation, points=7):
    """Small, diagnostic-only fits on the same integer-lag samples."""
    c=np.asarray(correlation);centre=len(c)//2
    if len(c)<30 or not np.isfinite(c).all():raise ValueError('invalid diagnostic correlation')
    peak=int(np.argmax(c[centre-10:centre+10]))+centre-10
    x=np.arange(peak-points//2,peak+points//2+1)-centre
    a,b,_=np.polyfit(x,c[x+centre],2)
    if a>=0:raise ValueError('diagnostic peak is not concave')
    shift=float(-b/(2*a))
    if not np.isfinite(shift) or abs(shift)>10:raise ValueError('diagnostic peak outside search bounds')
    return shift


def clipping_trials(arrays,index):
    """Reconstruct PypeIt 3.0 processing and require agreement before ablations."""
    import pypeit
    from pypeit.core import arc
    from pypeit.core.flexure import get_percentile_clipping
    if pypeit.__version__!='3.0.0':return dict(status='unsupported_pypeit_version'),{}
    a=np.array(arrays[f'observed_{index}'],copy=True);b=np.array(arrays[f'template_{index}'],copy=True)
    def processed(f,initial_clip=False,ceiling=True):
        if initial_clip:
            lo,hi=get_percentile_clipping(f,percent=90.);f=np.clip(f,lo,hi)
        if not np.isfinite(f).all() or f.mean()<=0:raise ValueError('invalid sky normalization')
        _,amplitude,_,_,_,_,result,_=arc.detect_lines(f/f.mean(),sigdetect=5.)
        if ceiling and len(amplitude):
            lo,hi=get_percentile_clipping(amplitude,percent=50.);result=np.clip(result,lo,hi)
        return result
    aa=processed(a,True);bb=processed(b);corr=np.correlate(bb,aa,'same');centre=len(corr)//2
    indices=np.asarray(arrays[f'lags_{index}'],dtype=int)
    # PypeIt's returned sample positions are absolute indices into its correlation.
    if int(arrays[f'correlation_centre_{index}'])!=centre or not np.allclose(
            corr[indices],arrays[f'correlation_{index}'],rtol=1e-7,atol=1e-10):
        return dict(status='baseline_reconstruction_mismatch'),{}
    saved=arrays[f'fit_coefficients_{index}'];expected=float(-.5*saved[1]/saved[2]-centre)
    if abs(fit_peak(corr)-expected)>1e-6:return dict(status='baseline_peak_mismatch'),{}
    trials={};vectors=dict(reconstructed_correlation=corr,lags=np.arange(len(corr))-centre)
    def attempt(name,curve,points=7):
        try:trials[name]=dict(status='measured',shift_pixels=fit_peak(curve,points))
        except ValueError as exc:trials[name]=dict(status='failed',reason=str(exc))
    for points in (3,5,7):attempt(f'peak_fit_{points}_points',corr,points)
    for trim in (2,5,10,20):attempt(f'trim_{trim}_edges',np.correlate(bb[trim:-trim],aa[trim:-trim],'same'))
    for name,obs,temp in [('without_initial_observed_clip',processed(a),bb),
                          ('without_line_amplitude_ceiling',processed(a,True,False),processed(b,False,False))]:
        curve=np.correlate(temp,obs,'same');vectors[name]=curve;attempt(name,curve)
    return dict(status='baseline_reproduced',production_shift_pixels=expected,trials=trials),vectors


def diagnose(packet,output,*,trial_correction=False):
    """Read-only QC entrypoint; new output directory, no science export or activation."""
    from contextlib import redirect_stdout,redirect_stderr
    from .sky_comparison import compare
    from .run_record import snapshot_sources
    packet=Path(packet).resolve();record=json.loads(packet.read_text());array_path=packet.parent/'arrays.npz'
    if record.get('schema_version')!=1:raise ValueError('unsupported sky diagnostic schema')
    if sha256(array_path)!=record['arrays_sha256']:raise ValueError('sky diagnostic arrays changed')
    if sha256(Path(record['raw']))!=record['raw_sha256']:raise ValueError('raw exposure changed')
    protected={str(p):sha256(p) for p in (packet,array_path,Path(record['raw']))}
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    with np.load(array_path,allow_pickle=False) as f:arrays={k:f[k] for k in f.files}
    report=dict(packet=str(packet),packet_sha256=sha256(packet),target=record['target'],
        source_sha256=snapshot_sources(output),trial_only=True,correction_applied=False,stages={},errors=[])
    with (output/'execution.log').open('w') as log,redirect_stdout(log),redirect_stderr(log):
        stages={'before':record['diagnostics']['full_sky']}
        if 'corrected_full_sky' in record['diagnostics']:stages['after']=record['diagnostics']['corrected_full_sky']
        if trial_correction and 'after' not in stages:
            first=stages['before']['ranges'][0];assessment=summarize(stages['before'])
            if assessment['ranges'][0]['failed_checks']:
                report['trial_correction_skipped']='Full-range quality checks failed.'
            else:
                shift=first['approximate_shift_angstrom'];after,values=compare(
                    arrays['input_data'],arrays['input_waveair']+shift,arrays['input_good'])
                stages['after']=after;arrays.update({'after__'+k:v for k,v in values.items()})
                report['trial_shift_air_angstrom']=shift
        for stage,summary in stages.items():
            values={k.split('__',1)[1]:v for k,v in arrays.items() if k.startswith(stage+'__')}
            entry=dict(measurements=summary,assessment=summarize(summary,corrected=stage=='after'),regions=[])
            for i,row in enumerate(summary['ranges']):
                if row.get('status')!='measured':entry['regions'].append(dict(index=i,status='not_measured'));continue
                try:
                    trial,vectors=clipping_trials(values,i)
                    np.savez_compressed(output/f'{stage}-region-{i}.npz',**vectors)
                    from .sky_diagnostic_plots import plot_region
                    figures=plot_region(values,i,row,trial,vectors,output,stage,record['target'])
                    entry['regions'].append(dict(index=i,**trial,figures=figures))
                except Exception as exc:
                    report['errors'].append(dict(stage=stage,index=i,error=str(exc)))
            report['stages'][stage]=entry
    np.savez_compressed(output/'diagnostic-arrays.npz',**arrays)
    report['arrays_sha256']=sha256(output/'diagnostic-arrays.npz')
    if any(sha256(Path(p))!=h for p,h in protected.items()):raise ValueError('diagnostic input changed')
    report.update(status='partial' if report['errors'] else 'complete',protected_inputs=protected)
    save_json(output/'diagnosis.json',report)
    return report


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packet',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--trial-correction',action='store_true')
    args=p.parse_args();r=diagnose(args.packet,args.output,trial_correction=args.trial_correction)
    print(json.dumps(dict(status=r['status'],errors=r['errors'],output=str(args.output))))
    return int(bool(r['errors']))


if __name__=='__main__':raise SystemExit(main())
