"""Background failures must remain reachable through the recovery entry point."""
import json

import pytest

from efospec import local_sky_trials


@pytest.mark.parametrize('code', ['source_selection_required', 'background_support_required'])
def test_recoverable_failure_reaches_hash_verified_exposure(tmp_path, monkeypatch, code):
    nightly = tmp_path/'runs/2026-10-28/nightly'
    run = nightly/'revision/reduction'
    run.mkdir(parents=True)
    (nightly/'current.json').write_text(json.dumps({'revision': 'revision'}))
    (run/'run.json').write_text(json.dumps({'errors': [{
        'object': 'AT2026agzp', 'path': '/raw.fits', 'code': code}]}))

    def verify(run_path, raw_name):
        assert run_path == run and raw_name == 'raw.fits'
        raise ValueError('raw input changed since source failure')

    monkeypatch.setattr(local_sky_trials, 'FailedExposure', verify)
    with pytest.raises(ValueError, match='raw input changed'):
        local_sky_trials.run_trials('2026-10-28', ['AT2026agzp'], tmp_path)
    assert not (nightly.parent/'QC').exists()
