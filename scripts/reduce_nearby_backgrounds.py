#!/usr/bin/env python3
"""Re-extract one night's provisional targets with nearest clean background bands."""
import argparse
import json
from pathlib import Path
import sys
import traceback

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.inventory import inspect_file,sha256
from efospec.native_calibration import save_json


def reduce(parent, rescue, output, night, aperture_padding=.5, objects=None):
    from pypeit.specobjs import SpecObjs
    from efospec.native_reduction import prepare
    from efospec.filtered_reduction import export_counts
    from efospec.run_record import snapshot_sources
    parent=Path(parent).resolve();rescue=Path(rescue).resolve();output=Path(output).resolve()
    old=json.loads((parent/'run.json').read_text());previous=json.loads((rescue/'run.json').read_text())
    if old['night']!=night or previous['night']!=night or previous['parent_sha256']!=sha256(parent/'run.json'):
        raise ValueError('select matching same-night parent and rescue')
    output.mkdir(parents=True,exist_ok=False)
    run=dict(night=night,method='native_optical_counts_diagnostic',status='running',results=[],errors=[],
        parent_run=str(parent),parent_sha256=sha256(parent/'run.json'),previous_rescue=str(rescue),
        previous_rescue_sha256=sha256(rescue/'run.json'),script_sha256=sha256(Path(__file__)),
        source_sha256=snapshot_sources(output),limitations=['Nearby background includes local extended light; no validated host deblending.','Arc-only wavelengths remain unvalidated.'])
    associations={e['path']:e['raw_calibrations'] for e in json.loads((parent/'setup-checks.json').read_text())['exposures']}
    reviews=[]
    for result in previous['results']:
        if objects and result['object'] not in objects:continue
        directory=output/'exposures'/Path(result['raw']).stem;directory.mkdir(parents=True)
        try:
            frame=inspect_file(Path(result['raw']));s=SpecObjs.from_fitsfile(result['native_spec1d'])[0]
            source=Path(result['native_spec1d']).parent/(Path(result['product']).name[:-7]+'_images.npz')
            if sha256(source)!=result['images_sha256']:raise ValueError('previous image changed')
            with np.load(source) as a:
                ylo=int(a['raw_y_origin']);xlo=int(a['spatial_origin'])+99
                y=len(a['trace'])//2;anchor=float(a['trace'][y]+xlo)
                # Reject saved neighbours that are not locally positive peaks:
                # use only the established separate neighbour of SN2026abgb.
                neighbours=[str(n) for n,t in zip(a['found_names'],a['found_traces'])
                    if result['object']=='SN2026abgb' and np.median(t)+xlo>590]
            # Preserve the manually specified narrow core for the extended
            # AT2026agvs case; do not use the galaxy's ~63-pixel fitted FWHM.
            core=4. if result['object']=='AT2026agvs' else float(np.median(s.FWHM))
            recipe=dict(schema_version=1,engine_version='3.0.0',coordinates='raw_detector_pixels_zero_based',
                input_sha256={'raw':frame['sha256']},source_mode='manual',
                objects=[dict(id='primary',label=result['object'],kind='point',spec=ylo+y,spat=anchor,
                              fwhm=core,radius=float(s.BOX_R_PIX))],
                sky=dict(mode='pypeit_local',include=[],exclude=[],degree=2,sigma_clip=4.,
                    placement='nearest_to_aperture',width_pixels=30,minimum_width_pixels=15,
                    aperture_padding_pixels=aperture_padding,
                    core_fwhm_pixels=core,neighbour_names=neighbours,neighbour_fwhm_pixels=10.,
                    trace_reference=dict(path=str(source),sha256=sha256(source),raw_sha256=frame['sha256'])))
            path=directory/'geometry-recipe.json';save_json(path,recipe)
            review=dict(raw_name=Path(frame['path']).name,raw_sha256=frame['sha256'],object=result['object'],
                parent_run=str(parent),recipe_path=str(path),recipe_sha256=sha256(path),
                identity=dict(candidate=result['target'].get('identity',{}).get('candidate',1),method='operator_background',
                    evidence='User requests closest supported background to the aperture; preserve prior selected trace, refit local extended light and sky; target identity unverified.'))
            reviews.append(review)
            prepared=prepare(frame,associations[frame['path']],directory,548.,cached=result['calibration']['groups'][0],
                arc_supported_only=True,arc_only_review=True,reviewed_source=review)
            counts,_=export_counts(prepared,directory);run['results'].append(counts)
            print('SUCCESS',result['object'],counts['background']['reduced_chi2'],flush=True)
        except Exception as exc:
            (directory/'error.log').write_text(traceback.format_exc())
            run['errors'].append(dict(raw=result['raw'],object=result['object'],error=str(exc),diagnostics=getattr(exc,'diagnostics',{})))
            print('FAILED',result['object'],str(exc),flush=True)
        save_json(output/'run.json',run)
    run['status']='partial' if run['errors'] else 'complete';save_json(output/'run.json',run)
    save_json(output/'reviewed-sources.json',dict(schema_version=1,sources=reviews))
    return run


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent');p.add_argument('--rescue',required=True)
    p.add_argument('--night',required=True);p.add_argument('--output',required=True)
    p.add_argument('--aperture-padding',type=float,default=.5)
    p.add_argument('--object',action='append',dest='objects');a=p.parse_args()
    r=reduce(a.parent,a.rescue,a.output,a.night,a.aperture_padding,a.objects)
    print(json.dumps(dict(results=len(r['results']),errors=r['errors'])))
