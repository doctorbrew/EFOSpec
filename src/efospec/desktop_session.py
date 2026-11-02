"""Resolve observer-facing night folders without changing saved reductions."""
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class DesktopSession:
    selected: Path
    run: Path
    night: str
    reviews: tuple
    manifest: dict
    warnings: tuple = ()


def resolve_session(path):
    """Accept a run, dated workflow folder, processing revision or review packet.

    Automatic discovery only includes QC packets bound to the resolved run.
    A current-revision pointer must stay inside its nightly directory.
    """
    selected = Path(path).expanduser().resolve()
    packet = selected if selected.name == 'review.json' and selected.is_file() else None
    if packet:
        review = json.loads(packet.read_text())
        run = Path(review['parent_run']).resolve()
    else:
        root = selected.parent if selected.name == 'run.json' and selected.is_file() else selected
        if (root/'run.json').is_file():
            run = root
        elif (root/'reduction/run.json').is_file():
            run = root/'reduction'
        else:
            nightly = root/'nightly' if (root/'nightly/current.json').is_file() else root
            pointer = json.loads((nightly/'current.json').read_text())
            revision = (nightly/pointer['revision']).resolve()
            if revision.parent != nightly.resolve():
                raise ValueError('The current revision must be inside this night folder.')
            record = json.loads((revision/'night.json').read_text())
            if record['night'] != pointer['night']:
                raise ValueError('The current revision belongs to a different observing night.')
            run = revision/'reduction'
    run = run.resolve()
    manifest = json.loads((run/'run.json').read_text())
    if not isinstance(manifest.get('results'), list) or not isinstance(manifest.get('errors'), list):
        raise ValueError('Select a reduction run or a dated workflow folder with a run.json record.')
    night = Path(manifest.get('input_dir', '')).name or run.name
    candidates = [packet] if packet else sorted({
        *list((run/'QC').glob('*/review.json')),
        *list((run.parent/'QC').glob('*/review.json')),
    })
    reviews = [];warnings = []
    for candidate in candidates:
        try:
            info = json.loads(candidate.read_text())
            if not isinstance(info.get('raw_name'),str):raise ValueError('missing raw exposure name')
            if Path(info['parent_run']).resolve() == run:reviews.append(candidate)
        except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
            if packet:raise ValueError('Invalid source-review packet: '+str(exc)) from exc
            warnings.append(f'Skipped unreadable QC packet {candidate.parent.name}: {exc}')
    return DesktopSession(selected, run, night, tuple(reviews), manifest,tuple(warnings))
