"""A reviewed failed aperture is display evidence, never an accepted extraction."""
import json
from pathlib import Path

import numpy as np
import pytest

from efospec.failure_profiles import load_failure_profile, plot_failure_profiles
from efospec.inventory import sha256


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def reviewed_failure(tmp_path, monkeypatch):
    run = tmp_path/'reduction'; run.mkdir()
    raw = tmp_path/'raw.fits'; raw.write_bytes(b'original raw exposure')
    diagnostic = run/'failed.npz'
    shape = (30, 101)
    np.savez(diagnostic, data=np.full(shape, 100.), sky=np.zeros(shape),
        sky_input_mask=np.zeros(shape, bool), sky_mask_stage='source_finding_only_no_accepted_background_fit',
        waveair=np.broadcast_to(np.linspace(4000,7000,30)[:,None], shape),
        found_traces=np.array([np.full(30,20.), np.full(30,50.)]))
    write_json(run/'run.json', dict(results=[],skipped=[],errors=[dict(path=str(raw),object='SNtest',
        code='background_support_required',diagnostics=dict(diagnostic_file=str(diagnostic)))]))
    review = tmp_path/'QC/review-1/selection.json'
    write_json(review,dict(parent_run_sha256=sha256(run/'run.json'),sources=[dict(raw=str(raw),
        raw_sha256=sha256(raw),diagnostic_file=str(diagnostic),diagnostic_sha256=sha256(diagnostic),
        selection=dict(candidate=2,radius_pixels=7.,radius_source='review recipe',method='operator_visual'),
        caption='C2 selected; background unavailable; extraction remains failed.')]))
    def save_figure(fig, output, name):
        from PIL import Image
        output.mkdir(parents=True, exist_ok=True)
        Image.new('RGB',(32,32),'red').save(output/'profiles.png')
    monkeypatch.setattr('efospec.profile_plot.save_review_profile',save_figure)
    return run,raw,diagnostic,review


def test_selected_failed_plot_survives_rebuild_and_is_rendered(reviewed_failure):
    from efospec.epoch_report import EpochPage
    run,raw,diagnostic,review = reviewed_failure
    before={p:sha256(p) for p in (raw,diagnostic,run/'run.json')}
    records=plot_failure_profiles(run,review=review)
    folder,record=load_failure_profile(run,str(raw))
    assert folder.is_relative_to(review.parent)
    assert record['selection']['candidate']==2 and not record['extraction_accepted']
    assert plot_failure_profiles(run)==records
    assert all(sha256(p)==h for p,h in before.items())
    page=EpochPage(run.parent)
    html=page.spectra(run,json.loads((run/'run.json').read_text()))
    assert record['caption'] in html and '<img' in html
    # The Source QC section must not leave the superseded candidate drawings
    # visible alongside the current reviewed geometry.
    write_json(run.parent/'QC/old/review.json',dict(raw_name=raw.name,object='SNtest',
        parent_run=str(run.parent/'older'),candidates=[dict(number=3,anchor_raw_x=140.)]))
    qc,_=page.qc(run.parent,json.loads((run/'run.json').read_text()))
    assert record['caption'] in qc
    assert qc.index('Current reviewed aperture geometry') < qc.index('<details>')
    assert qc.index('<details>') < qc.index('C3: x=140.00') < qc.index('</details>')
    with pytest.raises(ValueError,match='new revision'):
        plot_failure_profiles(run,review=review)


@pytest.mark.parametrize('change', ['raw','diagnostic','selection','figure','run'])
def test_selected_failure_rejects_changed_inputs_or_evidence(reviewed_failure,change):
    run,raw,diagnostic,review=reviewed_failure
    plot_failure_profiles(run,review=review)
    folder,_=load_failure_profile(run,str(raw))
    path={'raw':raw,'diagnostic':diagnostic,'selection':review,'figure':folder/'profiles.png',
          'run':run/'run.json'}[change]
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='changed|different run'):
        load_failure_profile(run,str(raw))


def test_wrong_exposure_cannot_activate_a_review(reviewed_failure):
    run,raw,diagnostic,review=reviewed_failure
    payload=json.loads(review.read_text());payload['sources'][0]['diagnostic_file']=str(raw)
    write_json(review,payload)
    with pytest.raises(ValueError,match='saved failed-exposure diagnostic'):
        plot_failure_profiles(run,review=review)
    assert not (run/'failure-profile-selection.json').exists()
