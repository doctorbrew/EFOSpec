import json
from pathlib import Path

import pytest

from efospec.desktop_session import resolve_session


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_dated_folder_resolves_current_reduction_and_matching_packets(tmp_path):
    night = tmp_path/'2026-10-28'
    revision = night/'nightly'/'processing-1'
    run = revision/'reduction'
    save(night/'nightly/current.json', {'night': night.name, 'revision': revision.name})
    save(revision/'night.json', {'night': night.name})
    save(run/'run.json', {'input_dir': '/data/2026-10-28', 'results': [], 'errors': []})
    packet = revision/'QC'/'exposure'/'review.json'
    save(packet, {'parent_run': str(run), 'raw_name': 'science.fits'})
    save(packet.parent/'recipes/review.json', {'parent_run': str(run)})
    save(revision/'QC'/'different-run'/'review.json', {'parent_run': str(tmp_path/'old'),'raw_name':'other.fits'})
    save(revision/'QC'/'incomplete'/'review.json', {'raw_name':'unfinished.fits'})
    for entry in (night, night/'nightly', revision, run, run/'run.json', packet):
        session = resolve_session(entry)
        assert session.selected == entry
        assert session.run == run
        assert session.night == night.name
        assert session.reviews == (packet,)
        assert len(session.warnings)==(0 if entry==packet else 1)


def test_current_pointer_cannot_escape_or_mislabel_the_night(tmp_path):
    save(tmp_path/'current.json', {'night': '2026-10-28', 'revision': '../outside'})
    with pytest.raises(ValueError, match='inside'):
        resolve_session(tmp_path)
    save(tmp_path/'current.json', {'night': '2026-10-28', 'revision': 'processing-1'})
    save(tmp_path/'processing-1/night.json', {'night': '2026-10-29'})
    with pytest.raises(ValueError, match='different observing night'):
        resolve_session(tmp_path)


def test_missing_or_non_reduction_record_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_session(tmp_path)
    save(tmp_path/'run.json', {'calibrations': []})
    with pytest.raises(ValueError, match='reduction run'):
        resolve_session(tmp_path)
