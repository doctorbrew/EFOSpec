"""Read-only spatial-profile previews of saved failed-extraction diagnostics."""
import json
from pathlib import Path
import numpy as np
from .inventory import sha256
from .native_calibration import save_json


def _check_hashes(hashes, message):
    for name, digest in hashes.items():
        if sha256(Path(name)) != digest:
            raise ValueError(message)


def load_failure_profile(run, raw):
    """Load the explicitly selected display revision, or the original preview."""
    run = Path(run).resolve()
    folder = run/'review-plots'/Path(raw).stem
    pointer = run/'failure-profile-selection.json'
    if pointer.exists():
        selected = json.loads(pointer.read_text())
        _check_hashes({selected['manifest']: selected['sha256']}, 'failed-profile selection changed')
        manifest = json.loads(Path(selected['manifest']).read_text())
        if manifest['parent_run_sha256'] != sha256(run/'run.json'):
            raise ValueError('failed-profile selection belongs to a different run')
        record = manifest['profiles'].get(str(raw))
        if record:
            _check_hashes({record['path']: record['sha256']}, 'failed-profile display changed')
            folder = Path(record['path']).parent
    path = folder/'profile-display.json'
    if not path.exists(): return None
    record = json.loads(path.read_text())
    if record['parent_run_sha256'] != sha256(run/'run.json'): return None
    if record['raw'] != str(raw): raise ValueError('failed-profile raw exposure mismatch')
    _check_hashes({record['diagnostic_file']: record['diagnostic_sha256']},
                  'failed-extraction profile input changed')
    if record.get('raw_sha256'):
        _check_hashes({record['raw']: record['raw_sha256']}, 'failed-profile raw exposure changed')
    _check_hashes(record.get('evidence_sha256', {}), 'failed-profile review evidence changed')
    _check_hashes(record['figures_sha256'], 'failed-extraction profile figure changed')
    if str(folder/'profiles.png') not in record['figures_sha256']:
        raise ValueError('failed-profile preview has no recorded hash')
    return folder, record


def plot_failure_profiles(run, *, review=None):
    from .profile_plot import draw_review_profiles, save_review_profile
    import matplotlib.pyplot as plt
    run=Path(run).resolve()
    manifest=json.loads((run/'run.json').read_text())
    choices = {}
    if review is not None:
        review = Path(review).resolve()
        request = json.loads(review.read_text())
        if request['parent_run_sha256'] != sha256(run/'run.json'):
            raise ValueError('failed-profile review belongs to a different run')
        choices = {item['raw']: item for item in request['sources']}
        if not choices or len(choices) != len(request['sources']):
            raise ValueError('failed-profile review needs distinct exposures')
        errors = {e['path']: e for e in manifest['errors']}
        for raw, choice in choices.items():
            if raw not in errors or errors[raw].get('diagnostics', {}).get('diagnostic_file') != choice['diagnostic_file']:
                raise ValueError('review must identify the saved failed-exposure diagnostic')
            _check_hashes({raw: choice['raw_sha256'], choice['diagnostic_file']: choice['diagnostic_sha256'],
                           **choice.get('evidence_sha256', {})}, 'failed-profile review input changed')
        if (review.parent/'profiles.json').exists():
            raise ValueError('save manual review changes in a new revision')
    inputs=json.loads((run/'inputs.json').read_text()) if (run/'inputs.json').exists() else {}
    frames={f['path']:f for f in inputs.get('frames',[])}
    records=[]
    for error in manifest['errors']:
        if review is not None and error['path'] not in choices: continue
        if review is None and (run/'failure-profile-selection.json').exists():
            selected = load_failure_profile(run, error['path'])
            if selected:
                records.append(selected[1]); continue
        diagnostic=error.get('diagnostics',{}).get('diagnostic_file')
        if not diagnostic: continue
        path=Path(diagnostic).resolve();path.relative_to(run)
        before=sha256(path)
        with np.load(path,allow_pickle=False) as saved:
            images={key:saved[key] for key in saved.files}
        frame=frames.get(error['path'],{})
        result=dict(object=error.get('object',Path(error['path']).stem),
            grism=error.get('setup',frame.get('setup',{})).get('grism','Unknown'),
            exptime_s=frame.get('metadata',{}).get('EXPTIME',0.))
        output=run/'review-plots'/Path(error['path']).stem
        choice = choices.get(error['path'], {})
        if review is not None: output=review.parent/'profiles'/Path(error['path']).stem
        fig,record=draw_review_profiles(images,result, selection=choice.get('selection'),
            candidate_notes=choice.get('candidate_notes'), supplemental_traces=choice.get('supplemental_traces', []),
            hidden_candidates=choice.get('hidden_candidates', []), candidate_labels=choice.get('candidate_labels'))
        save_review_profile(fig,output,result['object']);plt.close(fig)
        assert sha256(path)==before
        record.update(parent_run_sha256=sha256(run/'run.json'),diagnostic_file=str(path),
            diagnostic_sha256=before,raw=error['path'],
            raw_sha256=choice.get('raw_sha256'),caption=choice.get('caption',''),
            evidence_sha256={**choice.get('evidence_sha256', {}), **({str(review):sha256(review)} if review else {})},
            figures_sha256={str(p):sha256(p) for p in output.iterdir() if p.suffix in {'.png','.jpg','.pdf'}})
        save_json(output/'profile-display.json',record);records.append(record)
    if review is not None:
        index = review.parent/'profiles.json'
        paths = {raw:review.parent/'profiles'/Path(raw).stem/'profile-display.json' for raw in choices}
        save_json(index, dict(parent_run_sha256=sha256(run/'run.json'),
            profiles={raw:dict(path=str(path),sha256=sha256(path)) for raw,path in paths.items()}))
        save_json(run/'failure-profile-selection.json',dict(manifest=str(index),sha256=sha256(index)))
    return records


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    parser.add_argument('--review', help='Hash-bound operator review JSON; save figures in a new review revision')
    args = parser.parse_args()
    plot_failure_profiles(args.run, review=args.review)
