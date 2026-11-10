#!/usr/bin/env python3
"""Reproduce wavelength failures and independent diagnostic comparisons for one night.

No measured shift is applied and no acceptance threshold is changed. The lamp
check uses previously identified lamp lines at the source's detector position;
it tests spatial mapping, not independent science-exposure flexure.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from astropy import units as u
from astropy.stats import sigma_clip
from scipy.optimize import curve_fit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.inventory import inspect_file, sha256
from efospec.native_calibration import calibration_key, save_json
from efospec.native_calibrations import load_calibrations, process_exposure, validate_associations
from efospec.native_reduction import arc_supported_rows
from efospec.native_sky import measure_flexure, SkyValidationError
from efospec.reduction_checks import correlate_sky


def lamp_at_source(bundle, position=548.):
    from pypeit.images.buildimage import ArcImage
    from pypeit.core.wave import vactoair
    files=list((bundle['directory']/'Calibrations').glob('Arc_*.fits'))
    if len(files)!=1:raise ValueError('ambiguous processed lamp')
    arc=ArcImage.from_file(files[0]).image
    wave=vactoair(bundle['wavevac']*u.AA).value
    refs=vactoair(np.asarray(bundle['record']['wavelength']['shared_acceptance']['reference_vacuum_angstrom'])*u.AA).value
    measurements=[]
    def gaussian(x,a,c,s,b,m):return a*np.exp(-.5*((x-c)/s)**2)+b+m*(x-c)
    for xcenter in (position-40,position,position+40):
        xcenter=int(xcenter);w=wave[:,xcenter]
        signal=np.mean([np.interp(w,wave[:,x],arc[:,x]) for x in range(xcenter-5,xcenter+6)],axis=0)
        step=float(np.median(np.diff(w)))
        for rest in refs:
            distances=abs(refs-rest)
            if not 5000<rest<7600 or np.any((distances>0)&(distances<90)):continue
            keep=abs(w-rest)<40;ww,ff=w[keep],signal[keep]
            if len(ww)<9:continue
            base=float(np.median(np.r_[ff[:2],ff[-2:]]))
            try:
                p,cov=curve_fit(gaussian,ww,ff,p0=[max(float(ff.max()-base),1),rest,2*step,base,0],
                    bounds=([0,rest-10,.25*step,-np.inf,-np.inf],[np.inf,rest+10,4*step,np.inf,np.inf]),maxfev=10000)
                err=float(np.sqrt(cov[1,1]));delta=float(p[1]-rest)
                measurements.append(dict(spatial_pixel=xcenter,reference_air_angstrom=float(rest),
                    residual_angstrom=delta,centroid_error_angstrom=err if np.isfinite(err) else None,
                    fit_samples=dict(wave=ww.tolist(),signal=ff.tolist(),model=gaussian(ww,*p).tolist())))
            except (ValueError,RuntimeError) as exc:
                measurements.append(dict(spatial_pixel=xcenter,reference_air_angstrom=float(rest),error=str(exc)))
    return dict(processed_lamp=str(files[0]),sha256=sha256(files[0]),measurements=measurements,
        interpretation='Diagnostic centroids of isolated fitted lamp IDs, not independent line identifications or science-flexure validation.')


def diagnose(parent, night, output):
    from pypeit.core.wave import vactoair
    from efospec.run_record import snapshot_sources
    parent=Path(parent).resolve();run=json.loads((parent/'run.json').read_text())
    if run['night']!=night or run.get('flux_calibration')!='same-night':raise ValueError('select the matching native nightly parent')
    associations={e['path']:e for e in json.loads((parent/'setup-checks.json').read_text())['exposures']}
    groups={}
    for result in run['results']:
        for p in result['calibration']['groups']:
            d=json.loads((Path(p)/'calibration.json').read_text())
            groups[calibration_key(dict(setup=d['setup'],raw_calibrations=d['associations']))]=Path(p)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    report=dict(night=night,parent_run=str(parent),parent_sha256=sha256(parent/'run.json'),
        source_sha256=snapshot_sources(output),script_sha256=sha256(Path(__file__)),
        applied=False,independent_science_validation=False,results=[],errors=[])
    for failure in run['errors']:
        if failure.get('code')!='wavelength_validation_failed':continue
        frame=inspect_file(Path(failure['path']));name=frame['metadata']['OBJECT']
        directory=output/Path(frame['path']).stem;directory.mkdir()
        try:
            association=associations[frame['path']];validate_associations(frame,association['raw_calibrations'])
            bundle=load_calibrations(groups[calibration_key(association)])
            image=process_exposure(frame,bundle)
            lo,hi=arc_supported_rows(bundle['wavevac'][4:1015,448:649],
                bundle['record']['wavelength']['shared_acceptance']['valid_wave_vacuum_angstrom']);lo+=4;hi+=4
            cols=np.flatnonzero(np.all(bundle['slitmask'][lo:hi]>=0,axis=0));margin=max(10,int(.1*len(cols)))
            xlo,xhi=int(cols[margin]),int(cols[-margin-1])+1;cut=np.s_[lo:hi,xlo:xhi]
            waves=vactoair(bundle['wavevac'][cut]*u.AA).value;data=image.image[cut]
            good=~image.fullmask.flagged()[cut];good &= abs(np.arange(xlo,xhi)[None,:]-548)>30
            slit=float(frame['setup']['slit'].removeprefix('slit'))/(float(image.detector['platescale'])*frame['setup']['binx'])
            try:
                shift,strict=measure_flexure(data,waves,slit_width_pixels=slit,good_pixels=good)
                strict.update(status='passed',candidate_shift=shift)
            except SkyValidationError as exc:strict=dict(status='failed',error=str(exc),**exc.diagnostics)
            wave=waves[:,waves.shape[1]//2];masked=np.where(good,data,np.nan)
            samples=np.array([np.interp(wave,waves[:,i],masked[:,i]) for i in range(10,data.shape[1]-10)])
            clipped=sigma_clip(samples,sigma=3,maxiters=5,axis=0,cenfunc='median',stdfunc='mad_std')
            sky=np.ma.mean(clipped,axis=0).filled(np.nan);sky[np.ma.count(clipped,axis=0)<20]=np.nan
            np.savez_compressed(directory/'sky-profile.npz',wave_air=wave,sky_electron=sky)
            comparisons=[]
            for region in ((5300,6500),(6500,6800),(6800,7400),(7400,8000)):
                try:
                    record,arrays=correlate_sky(wave,sky,fwhm_angstrom=float(slit*np.median(np.diff(wave))),wavelength_range=region)
                    path=directory/f'correlation-{region[0]}-{region[1]}.npz';np.savez_compressed(path,**arrays)
                    record.update(curves=str(path),curves_sha256=sha256(path),requested_range=list(region))
                except Exception as exc:record=dict(requested_range=list(region),status='unavailable',error=str(exc))
                comparisons.append(record)
            result=dict(object=name,raw=frame['path'],raw_sha256=frame['sha256'],strict_check=strict,
                calibration_manifest=str(bundle['directory']/'calibration.json'),
                calibration_manifest_sha256=sha256(bundle['directory']/'calibration.json'),
                lamp_check=lamp_at_source(bundle),correlations=comparisons,
                profile=str(directory/'sky-profile.npz'),profile_sha256=sha256(directory/'sky-profile.npz'),
                conclusion='Diagnostic comparisons only. No correction or new validation is inferred automatically.')
            save_json(directory/'diagnostic.json',result);report['results'].append(result)
            print(name,strict['status'],flush=True)
        except Exception as exc:
            import traceback
            (directory/'error.log').write_text(traceback.format_exc())
            report['errors'].append(dict(object=name,error=str(exc)))
        save_json(output/'diagnostics.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('parent')
    parser.add_argument('--night',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();r=diagnose(args.parent,args.night,args.output)
    print(json.dumps(dict(diagnostics=len(r['results']),errors=r['errors'])))
    raise SystemExit(bool(r['errors']))
