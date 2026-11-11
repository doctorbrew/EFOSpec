"""Host tags sit below acquisition figures; proposals never masquerade as adoption."""
from types import SimpleNamespace
from efospec.typing_report import acquisition_metadata, spectrum_metadata, verification_section, review_anchor


def record(**kwargs):
    return dict(object_id='ATtest',path='products/test.asci',host_status='unreviewed',
                redshift_status='unreviewed',host_candidates=[],provenance=[],**kwargs)


def test_uninitialized_fields_and_reviewer_are_not_tags():
    r=record(review=dict(reviewer='EFOSpec metadata initialization',reviewed_at='2026-11-11'))
    assert spectrum_metadata(None,r)==''


def test_positional_counterpart_is_not_labelled_a_host():
    r=record(preferred_crossmatch=dict(name='WISEA counterpart',kind='positional_counterpart',separation_arcsec=.9))
    html=spectrum_metadata(None,r)
    assert 'Positional counterpart: WISEA counterpart' in html and 'Proposed host:' not in html
    assert '0.90 arcsec' in html and 'Verify cross-match' in html


def test_reported_template_redshift_stays_distinct_from_host_and_adoption():
    r=record(host_name='Galaxy',redshift_candidates=[dict(preferred=True,redshift=.073,kind='transient_spectral')])
    html=spectrum_metadata(None,r)
    assert 'Published z: 0.073' in html and 'transient spectral (not adopted)' in html
    assert 'Catalogue z:' not in html and 'Adopted z:' not in html


def test_verification_preserves_links_evidence_and_exact_spectrum_identity(tmp_path):
    r=record(host_name='<Galaxy>',preferred_crossmatch=dict(name='<Galaxy>',rationale='Selection evidence',caveat='Ambiguous'),
             verification_links=[dict(label='NED',url='https://ned.ipac.caltech.edu/byname?objname=a&x=b'),
                                 dict(label='Unsafe',url='javascript:alert(1)')])
    page=SimpleNamespace(typing_annotations={r['path']:r},typing_run=tmp_path,download=lambda *a:'JSON download')
    html=verification_section(page)
    assert review_anchor(r) in acquisition_metadata(page,'ATtest')
    assert acquisition_metadata(page,'Other')==''
    assert 'Selection evidence' in html and '&lt;Galaxy&gt;' in html
    assert 'href="https://ned.ipac.caltech.edu/byname?objname=a&amp;x=b"' in html
    assert 'href="javascript:' not in html
    assert 'target="_blank" rel="noopener noreferrer"' in html


def test_acquisition_plot_precedes_tags(tmp_path,monkeypatch):
    import json
    from efospec.catalogue_report import catalogue_qc
    from efospec.inventory import sha256
    root=tmp_path/'2026-10-28';root.mkdir();qc=root/'QC';qc.mkdir()
    raw=root/'acq.fits';raw.write_bytes(b'raw')
    science=root/'science.fits';science.write_bytes(b'science')
    preview=root/'preview.png';preview.write_bytes(b'preview')
    wcs=root/'wcs.fits';wcs.write_bytes(b'wcs')
    field=dict(object='ATtest',raw=str(raw),raw_sha256=sha256(raw),status='ok',
               science_raws=[dict(path=str(science),sha256=sha256(science))],
               figures_sha256={},preview=str(preview),preview_sha256=sha256(preview),
               astrometry=dict(wcs=str(wcs),wcs_sha256=sha256(wcs),matched_stars=10,rms_pixel=1.),
               queries=[],sources=[])
    path=qc/'field.json';path.write_text(json.dumps(field))
    (qc/'catalogue-current.json').write_text(json.dumps(dict(night=root.name,fields={'acq':dict(path='QC/field.json',sha256=sha256(path))})))
    r=record(host_name='Galaxy')
    page=SimpleNamespace(root=root,typing_annotations={r['path']:r},read=lambda p:json.loads(p.read_text()),
                         figure=lambda *a,**kw:'<figure>ACQUISITION</figure>',download=lambda *a:'')
    html=catalogue_qc(page,dict(results=[dict(raw=str(science))]))[0][1]
    assert html.index('ACQUISITION')<html.index('Proposed host: Galaxy')
    assert 'Not assigned' not in html and 'Host review:' not in html
