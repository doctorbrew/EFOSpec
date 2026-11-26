import json
import pytest
from efospec.inventory import sha256
from efospec.nightly_comparison import comparison_section


def test_comparison_rejects_other_revision_and_changed_previous_product(tmp_path):
    revision=tmp_path/'revision';(revision/'reduction').mkdir(parents=True)
    run=revision/'reduction/run.json';run.write_text('{}')
    previous=tmp_path/'old.fits';previous.write_bytes(b'original')
    qc=revision/'QC/nightly-comparison';qc.mkdir(parents=True)
    record={'parent_sha256':'wrong','input_sha256':{str(previous):sha256(previous)},'science':[],'summary':[]}
    path=qc/'comparison.json';path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='another reduction'):comparison_section(None,revision)
    record['parent_sha256']=sha256(run);path.write_text(json.dumps(record));previous.write_bytes(b'changed')
    with pytest.raises(ValueError,match='input changed'):comparison_section(None,revision)


def test_no_comparison_leaves_existing_report_alone(tmp_path):
    assert comparison_section(None,tmp_path)==''


def test_archive_lists_prior_runs_but_omits_legacy_and_dependency_only_layouts(tmp_path):
    from efospec.epoch_report import EpochPage
    old=tmp_path/'2026-10-28/nightly/previous/reduction';old.mkdir(parents=True)
    (old/'run.json').write_text(json.dumps({'results':[{}], 'errors':[], 'skipped':[]}))
    current=tmp_path/'2026-10-28/efospec/nightly/current';current.mkdir(parents=True)
    content=EpochPage(tmp_path/'2026-10-28/efospec').archive(current)
    assert 'Retained legacy layout:' not in content
    assert (old/'run.json').is_file()
    prior=current.parent/'previous/reduction';(prior/'products').mkdir(parents=True)
    (prior/'run.json').write_bytes((old/'run.json').read_bytes())
    assert 'nightly/previous/reduction' in EpochPage(current.parent.parent).archive(current)
    (prior.parent/'retained-dependency.json').write_text('{}')
    assert 'nightly/previous/reduction' not in EpochPage(current.parent.parent).archive(current)
    assert (prior/'run.json').read_bytes()==(old/'run.json').read_bytes()
