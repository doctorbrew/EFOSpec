"""Host review is explicit, revision-bound, lossless and independent of extraction."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from efospec import typing_metadata as tm
from efospec.inventory import sha256
from test_epoch_report import epoch_page


@pytest.fixture
def typing_run(tmp_path):
    run = tmp_path/'runs/2026-10-28/nightly/revision-1/reduction'
    (run/'products').mkdir(parents=True)
    source = run/'products/ATtest.asci'; source.write_text('4000 1\n5000 2\n')
    product = source.with_suffix('.fits'); product.write_bytes(b'original spectrum')
    (run/'run.json').write_text(json.dumps(dict(night='2026-10-28', results=[dict(
        object='ATtest', product=str(product), role='science')], errors=[])))
    return run


def candidate(doc):
    r = doc['spectra'][0]
    r.update(host_status='candidate', host_name='Galaxy <one>', host_redshift=.03,
             host_source='NED record 123', host_redshift_uncertainty=.001, host_redshift_method='spectroscopic',
             host_reference_frame='heliocentric', host_separation_arcsec=4.2,
             host_candidates=[dict(name='nearer galaxy', separation_arcsec=1., catalogue='NED',
                                   uncertainty=.004, method='photometric', reference='record 122'),
                              dict(name='Galaxy <one>', separation_arcsec=4.2, reference='record 123')],
             provenance=[dict(note='Reviewed against transient coordinates')])
    return r


def adopt(r, kind='host_catalogue'):
    r.update(host_status='accepted', adopted_redshift=.03, adopted_redshift_kind=kind,
             redshift_status='accepted', adopted_redshift_source='Reviewed record 123')


def test_candidates_never_adopt_and_roundtrip_keeps_evidence(typing_run):
    before = {p:sha256(p) for p in typing_run.rglob('*') if p.is_file()}
    d = tm.skeleton(typing_run); r = candidate(d)
    saved = tm.save(typing_run, d, 'Observer')
    assert saved['spectra'][0]['host_candidates'] == r['host_candidates']
    assert saved['spectra'][0]['host_status'] == 'candidate'
    assert 'adopted_redshift' not in saved['spectra'][0]
    assert tm.load(typing_run) == saved
    assert all(sha256(p) == h for p,h in before.items())


@pytest.mark.parametrize('kind', tm.KINDS)
def test_adoption_needs_explicit_acceptance_and_review(typing_run, kind):
    d = tm.skeleton(typing_run); r = candidate(d); adopt(r, kind)
    with pytest.raises(ValueError, match='Explicit acceptance'):
        tm.save(typing_run, d, 'Observer')
    saved = tm.save(typing_run, d, 'Observer', accept_hosts=[r['path']], accept_redshifts=[r['path']])
    result = saved['spectra'][0]
    assert result['host_review']['reviewer'] == 'Observer'
    assert result['redshift_review']['reviewed_at'].endswith('+00:00')
    changed = deepcopy(saved); changed['spectra'][0]['adopted_redshift'] = .04
    with pytest.raises(ValueError, match='Explicit acceptance'):
        tm.save(typing_run, changed, 'Other', expected_revision=saved['revision_id'])


def test_host_adoption_requires_same_z_and_accepted_host(typing_run):
    d = tm.skeleton(typing_run); r = candidate(d); adopt(r); r['host_status']='candidate'
    with pytest.raises(ValueError, match='accepted host'):
        tm.save(typing_run, d, 'Observer', accept_redshifts=[r['path']])
    r['host_redshift'] = .04
    with pytest.raises(ValueError, match='identical'):
        tm.save(typing_run, d, 'Observer', accept_hosts=[r['path']], accept_redshifts=[r['path']])


def test_narrow_lines_need_no_host_and_zero_is_valid(typing_run):
    d = tm.skeleton(typing_run); r = d['spectra'][0]
    r.update(adopted_redshift=0, adopted_redshift_kind='narrow_lines', adopted_redshift_source='Line fit')
    saved = tm.save(typing_run, d, 'Observer', accept_redshifts=[r['path']])
    assert saved['spectra'][0]['host_status'] == 'unreviewed'
    assert saved['spectra'][0]['adopted_redshift'] == 0


@pytest.mark.parametrize('change', ['manifest','spectrum','object','path','revision'])
def test_stale_and_identity_mismatches_rejected(typing_run, change):
    d = tm.skeleton(typing_run)
    if change == 'manifest':
        p=typing_run/'run.json'; p.write_text(p.read_text()+'\n')
    elif change == 'spectrum': (typing_run/'products/ATtest.asci').write_text('changed')
    elif change == 'object': d['spectra'][0]['object_id']='Other'
    elif change == 'path': d['spectra'][0]['path']='../old/ATtest.asci'
    else: d['reduction_manifest_path']='/older/reduction/run.json'
    with pytest.raises(ValueError): tm.save(typing_run, d, 'Observer')
    assert not (typing_run/'typing-metadata.json').exists()


def test_revisions_and_concurrent_edit_protection(typing_run):
    original = tm.save(typing_run, tm.skeleton(typing_run), 'Observer')
    old_bytes = (typing_run/'typing-metadata.json').read_bytes()
    d=deepcopy(original); candidate(d)
    saved = tm.save(typing_run, d, 'Other', expected_revision=original['revision_id'])
    history = typing_run/'typing-metadata-revisions'
    assert (history/(original['revision_id']+'.json')).read_bytes() == old_bytes
    with pytest.raises(ValueError, match='changed while editing'):
        tm.save(typing_run, d, 'Observer', expected_revision=original['revision_id'])
    assert tm.load(typing_run) == saved


@pytest.mark.parametrize('key,value', [('host_redshift',float('nan')), ('adopted_redshift',-1),
    ('host_redshift_uncertainty',-.01), ('host_separation_arcsec',True),
    ('spectrum_url','file:///tmp/spectrum'), ('spectrum_url','javascript:alert(1)')])
def test_invalid_values_rejected(typing_run, key, value):
    d=tm.skeleton(typing_run);d['spectra'][0][key]=value
    with pytest.raises(ValueError): tm.save(typing_run,d,'Observer')


def test_cli_and_html_use_same_reviewed_record(typing_run, capsys):
    from efospec.__main__ import main
    from efospec.typing_report import records_for_run, spectrum_metadata
    assert main(['typing-metadata','init',str(typing_run),'--reviewer','Observer']) == 0
    assert main(['typing-metadata','edit',str(typing_run),'--reviewer','Observer','--spectrum','ATtest.asci',
                 '--set','host_name=Galaxy <one>','--set','host_source=Catalogue record',
                 '--set','host_redshift=0.03','--set','adopted_redshift=0.03',
                 '--set','adopted_redshift_kind=host_catalogue','--set','adopted_redshift_source=Catalogue record',
                 '--accept-host','--accept-redshift']) == 0
    html = spectrum_metadata(None, records_for_run(typing_run)['products/ATtest.asci'])
    assert 'Galaxy &lt;one&gt;' in html and 'host catalogue' in html and 'Observer' not in html
    assert '0.03' in html
    with pytest.raises(SystemExit) as exc:
        main(['typing-metadata','edit',str(typing_run),'--reviewer','Observer','--spectrum','ATtest.asci',
              '--set','adopted_redshift=0.04'])
    assert exc.value.code == 2


def test_old_host_measurements_rejected_without_modification(typing_run, tmp_path):
    evidence=tmp_path/'redshifts.json'; evidence.write_text(json.dumps(dict(night='2026-10-28',
        parent_run_sha256={'/old/run.json':'old'}, results=[])))
    d=tm.skeleton(typing_run)
    with pytest.raises(ValueError, match='older or different'):
        tm.import_evidence(typing_run, d, evidence)
    assert not (typing_run/'typing-metadata.json').exists()


def test_nightly_html_includes_export_and_rejects_stale_metadata(epoch_page):
    from efospec.epoch_report import build_epoch_page
    project, root, product = epoch_page
    run=product.parent.parent
    manifest=json.loads((run/'run.json').read_text());manifest['night']=root.name
    manifest['results'][0]['role']='science';(run/'run.json').write_text(json.dumps(manifest))
    product.with_suffix('.asci').write_text('4000 1\n5000 2\n')
    d=tm.skeleton(run);candidate(d)
    tm.save(run,d,'Observer')
    build_epoch_page(root.name,project)
    html=(root/'index.html').read_text()
    assert 'Host verification' in html and 'Galaxy &lt;one&gt;' in html
    assert 'host-tags' not in html.split('<section class="target" id="spectra">')[1].split('</section>')[0]
    assert 'Typing metadata JSON' in html and 'Not adopted' not in html
    assert html.index('id="host-verification"') > html.index('id="archive"')
    manifest['new_revision']='changed';(run/'run.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='different reduction revision'):
        build_epoch_page(root.name,project)



def test_current_evidence_preserves_all_candidates_and_measurements(typing_run, tmp_path):
    record=dict(object='ATtest', product=str(typing_run/'products/ATtest.fits'))
    for key in ('raw','images','diagnostic_arrays'):
        path=tmp_path/(key+'.dat');path.write_bytes(key.encode());record[key]=str(path)
    for key in ('product','raw','images','diagnostic_arrays'):
        record[key+'_sha256']=sha256(Path(record[key]))
    query=tmp_path/'query.json';query.write_text('{}')
    candidates=[dict(name='Near', separation_arcsec=1., method='photometric', uncertainty=.02, reference='record 1'),
                dict(name='Far', separation_arcsec=5., method='spectroscopic', uncertainty=.001, reference='record 2')]
    record['ned']=dict(candidate=candidates[0],candidates=candidates,query_file=str(query),query_sha256=sha256(query))
    record['spectral']=dict(z=.031, uncertainty=.001, reference_frame='heliocentric', method='narrow lines')
    path=tmp_path/'redshift.json';path.write_text(json.dumps(record))
    evidence=tmp_path/'redshifts.json';evidence.write_text(json.dumps(dict(night='2026-10-28',
        parent_run_sha256={str(typing_run/'run.json'):sha256(typing_run/'run.json')},
        results=[dict(path=str(path),sha256=sha256(path))])))
    d=tm.import_evidence(typing_run, tm.skeleton(typing_run), evidence)
    saved=tm.save(typing_run,d,'Observer');r=saved['spectra'][0]
    assert r['host_candidates']==candidates
    assert r['provenance'][-1]['record']==record
    assert r['host_status']=='unreviewed' and 'adopted_redshift' not in r


def test_withdrawal_preserves_previous_acceptance(typing_run):
    d=tm.skeleton(typing_run);r=candidate(d);adopt(r)
    saved=tm.save(typing_run,d,'First observer',accept_hosts=[r['path']],accept_redshifts=[r['path']])
    revision=saved['revision_id'];r=saved['spectra'][0]
    r.update(host_status='rejected',redshift_status='rejected',adopted_redshift=None)
    withdrawn=tm.save(typing_run,saved,'Second observer',expected_revision=revision)
    assert withdrawn['spectra'][0]['redshift_review']['reviewer']=='Second observer'
    old=tm.read(typing_run/'typing-metadata-revisions'/(revision+'.json'))
    assert old['spectra'][0]['redshift_status']=='accepted'
