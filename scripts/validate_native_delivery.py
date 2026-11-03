"""Run one explicit observing-night experiment with legacy-file access blocked."""
import argparse
from contextlib import redirect_stderr,redirect_stdout
import json
from pathlib import Path
import sys
import traceback
import hashlib


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('night',type=Path)
    parser.add_argument('--science',required=True)
    parser.add_argument('--standard',required=True)
    parser.add_argument('--science-position',required=True,type=float)
    parser.add_argument('--standard-position',required=True,type=float)
    parser.add_argument('--check-standard')
    parser.add_argument('--check-position',type=float)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if bool(args.check_standard)!=(args.check_position is not None):
        parser.error('--check-standard and --check-position must be supplied together')
    night=args.night.resolve();output=args.output.resolve()
    if night.name not in output.parts:parser.error('output must include the explicit observing date')
    paths={role:(night/value).resolve() for role,value in
           [('science',args.science),('standard',args.standard),('check',args.check_standard)] if value}
    if any(not p.is_relative_to(night) for p in paths.values()):
        parser.error('all exposures must belong to the selected night')
    output.mkdir(parents=True,exist_ok=False)
    blocked=[]
    def audit(event,values):
        if event=='open' and isinstance(values[0],(str,bytes)):
            path=str(values[0]).replace('\\','/')
            if any(part in path for part in ('trunk/src/ntt','/archive/efosc/','/database/')):
                blocked.append(path);raise RuntimeError('Legacy calibration file access is forbidden')
        if event=='import' and values[0].split('.')[0] in {'pyraf','iraf'}:
            blocked.append(values[0]);raise RuntimeError('IRAF/PyRAF import is forbidden')
    # A fresh process owns this audit hook; no files or environments are hidden/renamed.
    sys.addaudithook(audit)
    report={};arrays=[]
    invocation=dict(night=str(night),exposures={k:str(v) for k,v in paths.items()},
        science_position=args.science_position,standard_position=args.standard_position,
        check_position=args.check_position,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with (output/'execution.log').open('w') as log,redirect_stdout(log),redirect_stderr(log):
        try:
            from efospec.native_reduction import reduce_pair,prepare
            from efospec.native_acceptance import assess_run,standard_recovery,plot_acceptance
            from efospec.standard_reference import standard_reference
            from efospec.inventory import inspect_file,inventory
            from efospec.native_readiness import assess_native_readiness
            from pypeit.specobjs import SpecObjs
            reduce_pair(night,paths['science'],paths['standard'],output/'reduction',
                        science_position=args.science_position,standard_position=args.standard_position,
                        render_report=False)
            report=assess_run(output/'reduction')
            response=output/'reduction/response.fits'
            std=inspect_file(paths['standard'])
            physical=standard_reference(std,output/'physical-references')
            counts=SpecObjs.from_fitsfile(str(output/'reduction/standard/standard-counts.fits'))[0]
            closure,values=standard_recovery(std,counts,response,physical)
            report['training_standard']=closure;arrays.append(('Training standard',values))
            if args.check_standard:
                check=inspect_file(paths['check'])
                if check['role']!='standard_candidate' or check['sha256']==std['sha256']:
                    raise ValueError('held-out standard must be a distinct raw standard exposure')
                if any(check['setup'][k]!=std['setup'][k] for k in ('grism','filter','binx','biny','readout')):
                    raise ValueError('held-out standard setup is incompatible')
                readiness=assess_native_readiness(inventory([str(night)]))
                association=next(r['raw_calibrations'] for r in readiness['exposures'] if r['path']==check['path'])
                prepared=prepare(check,association,output/'held-out-standard',args.check_position)
                prepared['engine']['objects']['primary'].write_to_fits(
                    {'PYP_SPEC':'ntt_efosc2_epessto','TARGET':check['metadata']['OBJECT']},
                    str(output/'held-out-standard/standard-counts.fits'),overwrite=False)
                physical=standard_reference(check,output/'physical-references')
                validation,values=standard_recovery(check,prepared['engine']['objects']['primary'][0],response,physical)
                validation['slit_widths']=[std['setup']['slit'],check['setup']['slit']]
                report['held_out_standard']=validation;arrays.append(('Held-out standard',values))
            plot_acceptance(report,arrays,output)
            import numpy as np
            np.savez_compressed(output/'standard-diagnostics.npz',
                **{f'standard_{index}_{key}':value for index,(_,a) in enumerate(arrays)
                   for key,value in a.items()})
            report['execution_status']='complete'
        except Exception as exc:
            traceback.print_exc();report.update(execution_status='failed',error=str(exc),science_validated=False)
        finally:
            report['invocation']=invocation
            report['legacy_access_guard']={'active':True,'blocked_attempts':blocked,
                'scope':'Python file-open and import audit events in this validation process'}
            (output/'validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ('execution_status','science_validated','error','broad_band_coverage_pass') if k in report}))
    return 1 if report['execution_status']=='failed' else (0 if report['broad_band_coverage_pass'] else 2)


if __name__=='__main__':sys.exit(main())
