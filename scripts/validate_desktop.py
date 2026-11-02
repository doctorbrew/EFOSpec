"""Exercise a real GUI revision and exact CLI replay without editing its parent.

Run with the EFOSpec environment and an explicitly dated output directory.
Private FITS, screenshots and detailed paths remain in the local dated run.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import numpy as np
from astropy.io import fits
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from efospec.desktop import ExtractionWindow
from efospec.inventory import sha256
from efospec.revisions import Exposure


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--product',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--reference-root')
    parser.add_argument('--timeout',type=float,default=300)
    args=parser.parse_args()
    exposure=Exposure(args.run,args.product,args.reference_root)
    night=Path(exposure.manifest['input_dir']).name
    output=args.output.resolve()
    if night not in output.parts:raise ValueError('The output path must include the observing date: '+night)
    output.mkdir(parents=True,exist_ok=False)
    originals={str(p):sha256(p) for p in args.run.rglob('*') if p.is_file() and 'revisions' not in p.relative_to(args.run).parts}
    for p in (Path(exposure.result['raw']),exposure.context.sensitivity):originals[str(p)]=sha256(p)
    copied=output/'saved-run'
    shutil.copytree(args.run,copied,ignore=shutil.ignore_patterns('revisions'))
    app=QApplication([]);window=ExtractionWindow(copied,args.reference_root)
    index=window.exposures.findData(args.product)
    if index<0:raise ValueError('The requested exposure was not loaded.')
    window.exposures.setCurrentIndex(index);window.show()
    baseline=deepcopy(window.source_values())
    window.sources.fields['spat'].setValue(baseline[0]['spat']+.25)
    window.sources.fields['radius'].setValue(baseline[0]['radius']+.5)
    window.sky_auto.setChecked(False)
    request=deepcopy(window.recipe());recipe_path=output/'recipe.json'
    window.save_recipe(recipe_path);window.load_recipe(recipe_path)
    assert window.recipe()==request
    window.grab().save(str(output/'gui-request.png'))
    window.start_job()
    start=time.monotonic();state={};timer=QTimer();timer.setInterval(250)
    def poll():
        try:
            if time.monotonic()-start>args.timeout:raise TimeoutError('GUI extraction timed out')
            job=window.backend.job_status()
            if job is None:raise RuntimeError(window.notice.text())
            if job['status']=='running':return
            if job['status']!='complete':raise RuntimeError(job.get('log',job['status']))
            window.poll_job();state['revision']=job['directory']
            window.show_revision()
            assert window.exposure is not None
            state['opened_revision']=str(window.backend.run)
            window.grab().save(str(output/'gui-revision.png'))
            timer.stop();window.close();app.exit(0)
        except Exception:
            state['error']=traceback.format_exc();timer.stop();window.close();app.exit(1)
    timer.timeout.connect(poll);timer.start();code=app.exec()
    if code:
        (output/'failure.json').write_text(json.dumps(state,indent=2));raise RuntimeError(state.get('error','GUI failed'))
    replay=output/'cli-replay'
    command=[sys.executable,'-m','efospec','reextract',str(copied),'--product',args.product,
             '--recipe',str(recipe_path),'--output',str(replay),'--skip-report']
    if args.reference_root:command+=['--reference-root',args.reference_root]
    with (output/'replay.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=args.timeout)
    gui_file=Path(state['revision'])/'products'/args.product
    replay_file=replay/'products'/args.product
    with fits.open(gui_file) as gui, fits.open(replay_file) as cli:
        exact=np.array_equal(gui[0].data,cli[0].data,equal_nan=True)
        exact_mask=np.array_equal(gui['VALID'].data,cli['VALID'].data)
        assert exact and exact_mask
        assert gui[0].header['CRVAL1']==cli[0].header['CRVAL1']
        assert gui[0].header['CD1_1']==cli[0].header['CD1_1']
    unchanged=all(sha256(Path(p))==digest for p,digest in originals.items())
    assert unchanged
    result=dict(night=night,object=exposure.result['object'],product=args.product,
                original_source=baseline,requested_recipe=request,gui_revision=state['revision'],
                cli_replay=str(replay),exact_flux_and_uncertainty=exact,exact_valid_mask=exact_mask,
                parent_hashes_unchanged=unchanged,original_hashes=originals,qt_platform=app.platformName())
    (output/'validation.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'requested_recipe','original_hashes','original_source'}},indent=2))


if __name__=='__main__':main()
