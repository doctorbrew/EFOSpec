"""Fit responses and test held-out standards from one night's saved counts."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
from pypeit.specobjs import SpecObjs
from efospec.inventory import inspect_file, sha256
from efospec.filtered_reduction import fit_standard_response
from efospec.native_acceptance import standard_recovery
from efospec.standard_reference import standard_reference
from efospec.run_record import snapshot_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('night')
    parser.add_argument('--parent', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from datetime import date
    night = date.fromisoformat(args.night)
    if night.isoformat() != args.night:
        raise ValueError('use one ISO observing night')
    root = Path(__file__).resolve().parents[1]/'runs'/args.night
    output = args.output.resolve(); output.relative_to(root.resolve())
    entries = []; parents = {}
    for parent in args.parent:
        parent = parent.resolve(); parent.relative_to(root.resolve())
        manifest = json.loads((parent/'run.json').read_text())
        if manifest.get('night') != args.night:
            raise ValueError('all parent counts must belong to the requested night')
        parents[str(parent)] = sha256(parent/'run.json')
        for row in manifest['results']:
            frame = inspect_file(Path(row['raw']))
            if frame['role'] != 'standard_candidate':
                continue
            if frame['sha256'] != row['raw_sha256']:
                raise ValueError('raw standard changed')
            if frame['night'] != night.strftime('%Y%m%d'):
                raise ValueError('raw standard is outside the observing night')
            for name, digest in row['product_sha256'].items():
                if sha256(Path(name)) != digest:
                    raise ValueError('saved count product changed')
            entries.append((frame, row))
    if not entries or len({f['sha256'] for f,_ in entries}) != len(entries):
        raise ValueError('select nonempty, distinct standard exposures')
    output.mkdir(parents=True, exist_ok=False)
    summary = dict(night=args.night, parent_manifests=parents,
        source_sha256=snapshot_sources(output), script_sha256=sha256(Path(__file__)),
        responses=[], held_out=[], errors=[], independent_flux_validation=False,
        limitations=['Held-out exposures test repeatability and cross-standard transfer, not an external absolute scale.',
                     'Narrow-slit losses, transparency, reference sampling and unmeasured flexure can affect ratios.',
                     'No second-order or telluric correction; no accepted science product is replaced.'])
    objects = {}; references = {}; responses = {}
    with (output/'execution.log').open('w') as stream, redirect_stdout(stream), redirect_stderr(stream):
        for frame, row in entries:
            name = Path(frame['path']).stem
            directory = output/name; directory.mkdir()
            obj = SpecObjs.from_fitsfile(row['native_spec1d'])
            record = fit_standard_response(frame, obj, directory)
            summary['responses'].append(dict(raw=frame['path'], raw_sha256=frame['sha256'],
                object=frame['metadata']['OBJECT'], setup=frame['setup'], result=record))
            if record['status'] != 'response_built_unvalidated':
                continue
            objects[name] = obj
            references[name] = standard_reference(frame, directory/'physical-references')
            responses[name] = record['response']['path']
        keys = ('grism','filter','slit','binx','biny','readout')
        for training, _ in entries:
            train_name = Path(training['path']).stem
            if train_name not in responses:
                continue
            for test, _ in entries:
                test_name = Path(test['path']).stem
                if test_name == train_name or test_name not in objects:
                    continue
                if any(training['setup'][key] != test['setup'][key] for key in keys):
                    continue
                try:
                    qa, arrays = standard_recovery(test, objects[test_name][0],
                                                   responses[train_name], references[test_name])
                    qa.update(training_raw=training['path'], training_object=training['metadata']['OBJECT'],
                              test_object=test['metadata']['OBJECT'], setup=test['setup'])
                    path = output/(train_name+'__'+test_name+'.npz')
                    np.savez_compressed(path, **arrays)
                    qa.update(arrays=str(path), arrays_sha256=sha256(path))
                    summary['held_out'].append(qa)
                except Exception as exc:
                    traceback.print_exc()
                    summary['errors'].append(dict(training=train_name,test=test_name,error=str(exc)))
    (output/'responses.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'output':str(output), 'responses':[(r['object'],r['result']['status'])
        for r in summary['responses']], 'held_out':len(summary['held_out']), 'errors':summary['errors']}))


if __name__ == '__main__':
    main()
