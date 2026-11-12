"""Window expansion may add calibrated room, never relax scientific gates."""
import json
import pytest

from efospec import native_reduction
from efospec.local_sky import BackgroundSupportError


def test_native_window_expands_only_for_unplaceable_bands(tmp_path, monkeypatch):
    calls=[]
    def prepare(frame, associations, directory, position, cached, **options):
        width=options['spatial_half_width'];calls.append((width,cached))
        if width==100:
            (directory/'calibration').mkdir()
            (directory/'calibration/calibration.json').write_text('{}')
            raise BackgroundSupportError('insufficient room',trials=[dict(status='geometry_unavailable')])
        return dict(engine=dict(background_fit={}))
    monkeypatch.setattr(native_reduction,'_prepare_window',prepare)
    result=native_reduction.prepare({}, {}, tmp_path, 548., adaptive_window=True)
    assert calls==[(100,None),(150,tmp_path/'calibration')]
    saved=json.loads((tmp_path/'window-attempts.json').read_text())
    assert [a['status'] for a in saved]==['failed','extracted']
    assert result['engine']['background_fit']['window_attempts']==saved


@pytest.mark.parametrize('review,trial', [(None,'fit_failed'), ({'explicit':True},'geometry_unavailable')])
def test_solver_failure_and_reviewed_geometry_do_not_resize(tmp_path, monkeypatch, review, trial):
    calls=[]
    def prepare(*args, **options):
        calls.append(options['spatial_half_width'])
        raise BackgroundSupportError('scientific check failed',trials=[dict(status=trial)])
    monkeypatch.setattr(native_reduction,'_prepare_window',prepare)
    with pytest.raises(BackgroundSupportError) as caught:
        native_reduction.prepare({}, {}, tmp_path, 548., adaptive_window=True, reviewed_source=review)
    assert calls==[100]
    # Failure evidence remains serializable; no self-referential diagnostics.
    assert json.loads(json.dumps(caught.value.diagnostics))['window_attempts'][0]['status']=='failed'
