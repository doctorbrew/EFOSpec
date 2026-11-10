#!/usr/bin/env python3
"""Audit one saved same-night reduction without recomputing its science."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from efospec.inventory import sha256
from efospec.native_calibration import save_json
from efospec.native_calibrations import load_calibrations
from efospec.daily_reduction import matches


def verify(run_dir):
    root=Path(run_dir).resolve(); run=json.loads((root/'run.json').read_text())
    if run.get('flux_calibration')!='same-night' or run['execution_status']=='running':
        raise ValueError('select one completed same-night reduction')
    frames={f['path']:f for f in json.loads((root/'inputs.json').read_text())['frames']}
    raw_checked={}; groups={}; products={}; rows=[]
    for result in run['results']:
        frame=frames[result['raw']]; response=result['sensitivity']
        standard=frames[response['standard_raw']]
        if not matches(frame,standard):raise ValueError('response night/setup mismatch')
        for path,digest in result['calibration']['raw_inputs'].items():
            if path not in raw_checked:raw_checked[path]=sha256(Path(path))
            if raw_checked[path]!=digest:raise ValueError('raw input changed: '+path)
        for field in ('sensitivity','extinction'):
            item=result[field]
            if sha256(Path(item['path']))!=item['sha256']:raise ValueError(field+' changed')
        for group in result['calibration']['groups']:
            if group not in groups:
                bundle=load_calibrations(group)
                groups[group]=bundle['record']['wavelength']['shared_acceptance']
        product=Path(result['product'])
        with fits.open(product,checksum=True) as hdus:
            header=hdus[0].header; flux=hdus[0].data[0,0]; sigma=hdus[0].data[3,0]
            valid=hdus['VALID'].data[0].astype(bool)
            if not (header['FLUXCAL']=='NATIVE' and header['WAVEMED']=='air' and header['SPECSYS']=='TOPOCENT'):
                raise ValueError('incorrect flux or wavelength convention')
            if not np.all(np.isfinite(flux[valid])&np.isfinite(sigma[valid])&(sigma[valid]>0)):
                raise ValueError('invalid delivered statistical flux/error samples')
            if not valid.any() or any(h.verify_checksum()!=1 or h.verify_datasum()!=1 for h in hdus):
                raise ValueError('invalid spectrum support or FITS checksum')
            wave=header['CRVAL1']+np.arange(len(flux))*header['CD1_1']
        if frame['role']=='science' and result['sky_flexure'].get('held_out_6363_pass') is not True:
            raise ValueError('science lacks independent sky-line validation')
        bg=result['processing']['background_fit']
        if bg['minimum_side_samples']<5:raise ValueError('background lost two-sided support')
        products[str(product)]=sha256(product)
        rows.append(dict(object=result['object'],role=frame['role'],grism=result['grism'],slit=result['slit'],
            standard=response['standard_name'],standard_raw=response['standard_raw'],
            valid_fraction=float(valid.mean()),supported_air_bounds=[float(wave[valid].min()),float(wave[valid].max())],
            source_association=result['target']['association'],minimum_background_side_samples=bg['minimum_side_samples']))
    outcomes=[Path(r.get('raw',r.get('path'))).name for k in ('results','errors','skipped') for r in run[k]]
    if len(set(outcomes))!=len(outcomes):raise ValueError('duplicate exposure outcomes')
    if not run.get('targets'):
        expected={Path(f['path']).name for f in frames.values() if
                  f['role'] in {'science','standard_candidate'} and 'duplicate_of' not in f}
        if set(outcomes)!=expected:raise ValueError('nightly exposures lack unique recorded outcomes')
    counts=[]
    for result in run.get('review_counts',[]):
        if result['flux_calibrated'] or result['science_validated']:
            raise ValueError('unvalidated review counts were promoted')
        for path,digest in result['product_sha256'].items():
            if sha256(Path(path))!=digest:raise ValueError('review count product changed')
        if sha256(Path(result['raw']))!=result['raw_sha256']:raise ValueError('review raw input changed')
        with fits.open(result['product']) as hdus:
            if hdus[0].header['FLUXCAL']!='NONE' or hdus[0].header['BUNIT']!='electron':
                raise ValueError('incorrect review-count units')
        counts.append(dict(object=result['object'],product=result['product'],
                           status='counts_only_wavelength_unvalidated',failure=result['wavelength_validation_error']))
    record=dict(status='passed',night=run['night'],run=str(root),run_sha256=sha256(root/'run.json'),
        audit_script_sha256=sha256(Path(__file__)),checked_raw_files=len(raw_checked),calibration_groups=groups,
        product_sha256=products,spectra=rows,review_counts=counts,errors=run['errors'],skipped=run['skipped'],
        independent_absolute_flux_validation=False)
    save_json(root/'verification.json',record)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run')
    args=parser.parse_args();r=verify(args.run)
    print(json.dumps(dict(status=r['status'],night=r['night'],spectra=len(r['spectra']),
                          raw_files=r['checked_raw_files'],groups=len(r['calibration_groups']))))
