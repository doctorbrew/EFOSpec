#!/usr/bin/env python3
"""Audit a provisional rescue without certifying its science wavelengths."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from efospec.daily_reduction import matches
from efospec.inventory import inspect_file, sha256
from efospec.native_calibration import save_json
from efospec.native_calibrations import load_calibrations
from efospec.rescue import validate_counts


def verify(directory):
    from pypeit.specobjs import SpecObjs
    root=Path(directory).resolve()
    run=json.loads((root/'run.json').read_text())
    assert run['method']=='native_raw_calibration_provisional_rescue'
    assert run['wavelength_policy']=='provisional_arc_only'
    assert run['status']=='PROVISIONAL' and run['execution_status']!='running'
    parent=Path(run['parent_run'])/'run.json'
    assert sha256(parent)==run['parent_sha256']
    old=json.loads(parent.read_text())
    assert old['night']==run['night'] and old['flux_calibration']=='same-night'
    failures={e['path'] for e in old['errors'] if e.get('code')=='wavelength_validation_failed'}
    assert len({r['raw'] for r in run['results']})==len(run['results'])
    rows=[];groups={};raws={}
    for result in run['results']:
        assert result['raw'] in failures and result['status']=='PROVISIONAL'
        assert result['wavelength_validated'] is False
        assert result['independent_flux_validation'] is False
        assert result['sky_flexure']['held_out_6363_pass'] is False
        assert result['sky_flexure']['shift_angstrom']==0
        source=Path(result['counts_source'])
        assert sha256(source)==result['counts_source_sha256']
        saved=json.loads(source.read_text())
        records=saved.get('review_counts',[]) + saved.get('results',[])
        counts=next(r for r in records if r['raw']==result['raw'])
        frame=inspect_file(Path(result['raw']))
        validate_counts(counts,frame)
        standard=next(s for s in old['standards']
                      if s['frame']['path']==result['sensitivity']['standard_raw'])
        assert matches(frame,standard['frame'])
        assert standard['fit']['response']['sha256']==result['sensitivity']['sha256']
        for item in (result['sensitivity'],result['extinction']):
            assert sha256(Path(item['path']))==item['sha256']
        for path,digest in result['calibration']['raw_inputs'].items():
            if path not in raws:raws[path]=sha256(Path(path))
            assert raws[path]==digest
        for directory in result['calibration']['groups']:
            if directory not in groups:
                bundle=load_calibrations(directory)
                groups[directory]=sha256(bundle['directory']/'calibration.json')
        for path,digest in result['product_sha256'].items():
            assert sha256(Path(path))==digest
        assert sha256(Path(result['native_spec2d']))==result['native_spec2d_sha256']
        original=SpecObjs.from_fitsfile(counts['native_spec1d'])[0]
        exported=SpecObjs.from_fitsfile(result['native_spec1d'])[0]
        for kind in ('OPT','BOX'):
            for field in ('WAVE','COUNTS','COUNTS_IVAR','MASK'):
                assert np.array_equal(original[kind+'_'+field],exported[kind+'_'+field],equal_nan=True)
        product=Path(result['product'])
        with fits.open(product,checksum=True) as hdus:
            header=hdus[0].header;data=hdus[0].data[:,0];valid=hdus['VALID'].data.astype(bool)
            assert header['EPSTATUS']=='PROVISIONAL' and header['QUALITY']=='Provisional'
            assert header['WAVEVAL'] is False and header['FLXVALID'] is False
            assert header['WAVSHIFT']==0 and header['FLEXURE']=='UNVALIDATED'
            assert header['WAVEMED']=='air' and header['SPECSYS']=='TOPOCENT'
            assert header['FLUXCAL']=='NATIVE' and header['EXTRPRI'].lower()==result['primary_extraction']
            assert all(h.verify_checksum()==1 and h.verify_datasum()==1 for h in hdus)
            assert valid[0].any() and np.array_equal(valid[0],valid[3])
            assert np.all(np.isfinite(data[0,valid[0]]) & np.isfinite(data[3,valid[0]]) & (data[3,valid[0]]>0))
            wave=header['CRVAL1']+np.arange(data.shape[-1])*header['CD1_1']
            ascii_path=product.with_suffix('.asci');ascii_data=np.loadtxt(ascii_path)
            assert 'PROVISIONAL' in ascii_path.read_text().splitlines()[0]
            assert np.allclose(ascii_data[:,0],wave,rtol=1e-8,atol=0)
            assert np.allclose(ascii_data[:,1],data[0],rtol=1e-8,atol=0,equal_nan=True)
        bg=result['processing']['background_fit']
        assert bg['pypeit_exit_status']==0 and bg['minimum_side_samples']>=5
        image=root/'native'/(product.name[:-7]+'_images.npz')
        with np.load(image) as arrays:
            mask=arrays['sky_input_mask'].astype(bool);trace=arrays['trace']
            radius=float(exported.BOX_R_PIX);x=np.arange(mask.shape[1])[None,:]
            assert not np.any(mask & (abs(x-trace[:,None])<=radius))
            proximity=[]
            for side in (-1,1):
                selected=mask & ((x-trace[:,None])*side>radius)
                assert np.all(selected.sum(axis=1)>=5)
                gap=np.min(np.where(selected,abs(x-trace[:,None])-radius,np.inf),axis=1)
                proximity.append(dict(minimum_gap=float(gap.min()),median_gap=float(np.median(gap)),
                    maximum_gap=float(gap.max()),minimum_input_width=int(selected.sum(axis=1).min()),
                    maximum_input_width=int(selected.sum(axis=1).max())))
        rows.append(dict(object=result['object'],primary_extraction=result['primary_extraction'],
            standard=result['sensitivity']['standard_name'],valid_fraction=float(valid[0].mean()),
            supported_air_bounds=[float(wave[valid[0]].min()),float(wave[valid[0]].max())],
            unchanged_native_counts_and_wavelengths=True,background_minimum_side_samples=bg['minimum_side_samples'],
            background_gap_from_aperture_edge_pixels=proximity,no_background_aperture_overlap=True,
            product=str(product),product_sha256=sha256(product)))
    record=dict(status='passed',scientific_status='PROVISIONAL',wavelength_validation=False,
        independent_absolute_flux_validation=False,night=run['night'],
        run_sha256=sha256(root/'run.json'),audit_script_sha256=sha256(Path(__file__)),
        parent_unchanged=True,checked_raw_files=len(raws),calibration_manifest_sha256=groups,spectra=rows)
    save_json(root/'verification.json',record)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run')
    record=verify(parser.parse_args().run)
    print(json.dumps({k:record[k] for k in ('status','scientific_status','night','checked_raw_files')}))
