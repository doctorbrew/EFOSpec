"""Replay saved background failures in a fresh, wider archive-calibrated window."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from efospec.archive_calibration import fit_arc
from efospec.inventory import sha256
from efospec.rapid import extract_frame
from efospec.revisions import FailedExposure
from efospec.run_record import snapshot_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('night')
    parser.add_argument('--target', action='append', required=True)
    parser.add_argument('--half-width', type=int, default=120)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from datetime import date
    if date.fromisoformat(args.night).isoformat() != args.night:
        raise ValueError('use one ISO observing date')
    root = Path(__file__).resolve().parents[1]
    night = root/'runs'/args.night
    pointer = json.loads((night/'nightly/current.json').read_text())
    parent = night/'nightly'/pointer['revision']/'reduction'
    manifest = json.loads((parent/'run.json').read_text())
    cases = [r for r in manifest['errors'] if r['object'] in args.target
             and r['code']=='background_support_required']
    if set(args.target)-{r['object'] for r in cases}:
        raise ValueError('target is not a saved background failure in this night')
    output = args.output.resolve(); output.relative_to(night.resolve())
    output.mkdir(parents=True, exist_ok=False)
    result = dict(night=args.night, parent_run=str(parent),
        parent_sha256=sha256(parent/'run.json'), half_width_pixels=args.half_width,
        source_sha256=snapshot_sources(output), results=[], errors=[],
        scientific_status='EXPERIMENTAL', accepted_science_delivery=False)
    for case in cases:
        directory = output/Path(case['path']).stem
        directory.mkdir()
        with (directory/'execution.log').open('w') as stream, redirect_stdout(stream), redirect_stderr(stream):
            try:
                exposure = FailedExposure(parent, Path(case['path']).name)
                context = exposure.context
                wave, arc = fit_arc(context.arc_qa['arc'])
                for sub in ('products','native','qa','QA/PNGs'):
                    (directory/sub).mkdir(parents=True)
                row = extract_frame(exposure.frame, context.reference_root, directory,
                    context.hint, context.hint_info, wave, arc, context.sensitivity,
                    context.shift, context.sky_qa, spatial_half_width=args.half_width)
                result['results'].append(row)
            except Exception as exc:
                traceback.print_exc()
                result['errors'].append(dict(object=case['object'], raw=case['path'],
                    error=str(exc), code=getattr(exc,'code',type(exc).__name__),
                    diagnostics=getattr(exc,'diagnostics',{})))
        (output/'run.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'output':str(output), 'extracted':len(result['results']),
                      'errors':[(r['object'],r['error']) for r in result['errors']]}))


if __name__ == '__main__':
    main()
