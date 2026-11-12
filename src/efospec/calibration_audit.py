"""One-night, immutable calibration review from recorded standards and raw data.

Experimental response splices are saved only here and never selected for science.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.io import fits

from .inventory import sha256
from .native_calibration import save_json


def telluric_residuals(arrays):
    """Measure band depressions against adjacent continuum, not a transmission model."""
    wave,ratio,valid=arrays['waveair'],arrays['ratio'],arrays['valid']
    bands=[]
    for name,lo,hi,left,right in [
        ('O2 B',6860,6950,(6750,6820),(7000,7070)),
        ('H2O',7160,7340,(7050,7120),(7400,7470)),
        ('O2 A',7590,7700,(7480,7550),(7780,7850))]:
        windows=[valid&(wave>=a)&(wave<b)&np.isfinite(ratio)&(ratio>0)
                 for a,b in (left,(lo,hi),right)]
        usable=all(m.sum()>=5 and np.ptp(wave[m])>=.7*(b-a)
                   for m,(a,b) in zip(windows,(left,(lo,hi),right)))
        relative=None
        if usable:
            l,m,r=windows
            baseline=np.interp(wave[m],[np.median(wave[l]),np.median(wave[r])],
                               [np.median(ratio[l]),np.median(ratio[r])])
            relative=float(np.median(ratio[m]/baseline))
        bands.append(dict(name=name,band_air_angstrom=[lo,hi],relative_band_ratio=relative,
            status='measured_depression_not_model' if usable else 'insufficient_coverage'))
    return bands


def standard_sky(entry):
    """Reprocess the full slit without extracting or modifying a saved product."""
    from pypeit.core.wave import vactoair
    from .native_calibrations import load_calibrations, process_exposure
    from .native_sky import exposure_flexure
    frame,c=entry['frame'],entry['counts']
    if frame['setup']['grism']=='Gr16':
        return dict(status='not_tested',reason='Optical three-line gate does not cover Gr16; retain separate red diagnostics.')
    bundle=load_calibrations(c['calibration_directory'])
    image=process_exposure(frame,bundle)
    with np.load(c['images']) as n:
        ylo=int(n['raw_y_origin']);yhi=ylo+n['data'].shape[0]
    cols=np.flatnonzero(np.all(bundle['slitmask'][ylo:yhi]>=0,axis=0))
    margin=max(10,int(.1*len(cols)));xlo,xhi=int(cols[margin]),int(cols[-margin-1])+1
    cut=np.s_[ylo:yhi,xlo:xhi]
    wave=vactoair(bundle['wavevac'][cut]*u.AA).value
    good=~image.fullmask.flagged()[cut]
    good &= abs(np.arange(xlo,xhi)[None,:]-c['median_trace_raw_pixel'])>30.
    width=float(frame['setup']['slit'][4:])/(float(image.detector['platescale'])*frame['setup']['binx'])
    shift,qa=exposure_flexure(image.image[cut],wave,required=False,
                            slit_width_pixels=width,good_pixels=good)
    return dict(qa,candidate_shift_angstrom=shift if qa['held_out_6363_pass'] else None,applied_shift_angstrom=None,
                measurement_raw_bounds_yx=[ylo,yhi,xlo,xhi],
                review_only=True,point_source_slit_centring_validated=False)


def write_pair(free, filtered, output):
    from .flux_validation import paired_zeropoint
    a,b=free['fit']['response'],filtered['fit']['response']
    with fits.open(a['path']) as h1, fits.open(b['path']) as h2:
        x,y=h1['RESPONSE'].data,h2['RESPONSE'].data
        z,valid,qa=paired_zeropoint(x['WAVE'],x['ZEROPOINT'],x['VALID'],
                                  y['WAVE'],y['ZEROPOINT'],y['VALID'])
        header=h1[0].header.copy();header['EPEXPER']=True
        header['HISTORY']='Experimental filtered response splice; no science correction adopted.'
        fits.HDUList([fits.PrimaryHDU(header=header),fits.BinTableHDU.from_columns([
            fits.Column(name='WAVE',format='D',array=x['WAVE']),
            fits.Column(name='ZEROPOINT',format='D',array=z),
            fits.Column(name='VALID',format='L',array=valid)],name='RESPONSE')]).writeto(output,checksum=True)
    record=dict(a,path=str(output),sha256=sha256(output),trial=qa,
        paired_response=dict(path=b['path'],sha256=b['sha256']),
        selection='Isolated calibration audit trial; NOT selected by nightly pipeline')
    save_json(output.with_suffix('.json'),record)
    return record


def audit(run_path, output, *, night, measure_sky=False):
    from pypeit.specobjs import SpecObjs
    from .daily_reduction import matches
    from .native_acceptance import standard_recovery
    from .standard_reference import standard_reference
    run_path=Path(run_path).resolve();run=json.loads(run_path.read_text())
    if run['night']!=night:raise ValueError('audit must name exactly the saved observing night')
    standards=[s for s in run['standards'] if s['fit']['status']=='response_built_unvalidated']
    if not standards:raise ValueError('no saved standard responses')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    from .run_record import snapshot_sources
    import pypeit
    import sys
    source_hashes=snapshot_sources(output)
    protected={str(run_path):sha256(run_path)}
    for s in standards:
        f,c,r=s['frame'],s['counts'],s['fit']['response']
        protected.update(c['product_sha256'])
        protected.update({f['path']:f['sha256'],r['path']:r['sha256'],
                          r['extinction']['path']:r['extinction']['sha256']})
        cal=Path(c['calibration_directory']);record=json.loads((cal/'calibration.json').read_text())
        protected[str(cal/'calibration.json')]=c['calibration_manifest_sha256']
        protected.update(record['raw_inputs'])
        protected.update({str(cal/k):v for k,v in record['processed_files'].items()})
        protected[str(cal/'wavelength-map.npz')]=record['wavelength_map_sha256']
        reference=Path(r['reference_file'])
        if not reference.is_file():raise ValueError('saved physical reference missing')
        digest=sha256(reference)
        recorded=r.get('reference_details',{}).get('reference_sha256')
        if recorded and recorded!=digest:raise ValueError('saved physical reference changed')
        protected[str(reference)]=digest
    for p,digest in protected.items():
        if sha256(Path(p))!=digest:raise ValueError('saved audit input changed: '+p)
    save_json(output/'inputs.json',protected)
    report=dict(night=night,source_run=str(run_path),status='running',python=sys.executable,
        pypeit_version=pypeit.__version__,source_sha256=source_hashes,
        standard_checks=[],transfers=[],paired_response_trials=[],
        absolute_flux_validated=False,science_products_modified=False,
        scope='Diagnostic review; no slit-loss, atmospheric or science-order correction adopted.')
    save_json(output/'audit.json',report)
    objects={};references={}
    with (output/'execution.log').open('w') as stream, redirect_stdout(stream),redirect_stderr(stream):
        for s in standards:
            f=s['frame'];key=f['path']
            obj=SpecObjs.from_fitsfile(s['counts']['native_spec1d'])[0];objects[key]=obj
            reference=standard_reference(f,output/'physical-references');references[key]=reference
            if sha256(Path(reference['cal_file']))!=protected[str(Path(s['fit']['response']['reference_file']))]:
                raise ValueError('reselected physical reference differs from saved response reference')
            closure,arrays=standard_recovery(f,obj,s['fit']['response']['path'],reference)
            h=f['metadata']
            row=dict(raw=key,object=h['OBJECT'],setup=f['setup'],exptime=h['EXPTIME'],
                airmass=h['ESO TEL AIRM START'],closure=closure,telluric_bands=telluric_residuals(arrays),
                reference_sha256=sha256(Path(reference['cal_file'])),
                sky=standard_sky(s) if measure_sky else dict(status='not_run'))
            report['standard_checks'].append(row);save_json(output/'audit.json',report)
        for train in standards:
            a=train['frame']
            for test in standards:
                b=test['frame']
                if a['sha256']==b['sha256'] or not matches(a,b):continue
                qa,_=standard_recovery(b,objects[b['path']],train['fit']['response']['path'],references[b['path']])
                report['transfers'].append(dict(qa,training_raw=a['path'],setup=b['setup']))
        for free in standards:
            a=free['frame'];setup=a['setup']
            if (setup['grism'],setup['filter'])!=('Gr13','Free'):continue
            candidates=[]
            for filtered in standards:
                b=filtered['frame']
                same=all(b['setup'][k]==v for k,v in setup.items() if k!='filter')
                dt=abs(a['metadata']['MJD-OBS']-b['metadata']['MJD-OBS'])*1440
                if same and b['night']==a['night'] and b['metadata']['OBJECT']==a['metadata']['OBJECT'] and b['setup']['filter']=='GG495' and dt<=15:
                    candidates.append((dt,filtered))
            if not candidates:continue
            candidates.sort(key=lambda pair:pair[0])
            if len(candidates)>1 and np.isclose(candidates[0][0],candidates[1][0]):
                raise ValueError('ambiguous paired-filter standard')
            dt,filtered=candidates[0]
            response=write_pair(free,filtered,output/f'paired-response-{len(report["paired_response_trials"])+1}.fits')
            trial=dict(free_raw=a['path'],filtered_raw=filtered['frame']['path'],minutes_apart=dt,
                       response=response,held_out=[])
            for test in standards:
                b=test['frame']
                if a['sha256']==b['sha256'] or not matches(a,b):continue
                qa,_=standard_recovery(b,objects[b['path']],response['path'],references[b['path']])
                trial['held_out'].append(qa)
            report['paired_response_trials'].append(trial)
    if not all(sha256(Path(p))==d for p,d in protected.items()):raise ValueError('audit modified a protected input')
    report.update(protected_file_count=len(protected),protected_inputs_unchanged=True,status='complete')
    save_json(output/'audit.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('night');p.add_argument('--run',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--measure-sky',action='store_true')
    a=p.parse_args();r=audit(a.run,a.output,night=a.night,measure_sky=a.measure_sky)
    print(json.dumps({k:r[k] for k in ('night','status','protected_file_count','protected_inputs_unchanged')}))


if __name__=='__main__':main()
