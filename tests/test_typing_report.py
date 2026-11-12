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
    assert '0.073' not in html and 'Published z:' not in html
    assert 'Catalogue z:' not in html and 'Adopted z:' not in html


def test_verification_preserves_links_evidence_and_exact_spectrum_identity(tmp_path):
    r=record(host_name='<Galaxy>',preferred_crossmatch=dict(name='<Galaxy>',rationale='Selection evidence',caveat='Ambiguous'),
             verification_links=[dict(label='NED',url='https://ned.ipac.caltech.edu/byname?objname=a&x=b'),
                                 dict(label='Unsafe',url='javascript:alert(1)')])
    page=SimpleNamespace(typing_annotations={r['path']:r},typing_run=tmp_path,download=lambda *a:'JSON download')
    html=verification_section(page)
    assert review_anchor(r) in html
    assert acquisition_metadata(page,'ATtest')==''
    assert acquisition_metadata(page,'Other')==''
    assert 'Selection evidence' not in html and '&lt;Galaxy&gt;' in html
    assert 'Metadata and review history' not in html and 'JSON download' not in html
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


def test_astronote_claims_and_review_history_are_not_in_host_evidence():
    from copy import deepcopy
    from efospec.typing_report import verification_details
    r=record(host_name='Galaxy',preferred_crossmatch=dict(name='Galaxy',catalogue='NED',separation_arcsec=2.5,
        rationale='Matches AstroNote published z=0.073'),
        verification_links=[dict(label='AstroNote',url='https://www.wis-tns.org/astronotes/2026-300'),
                            dict(label='NED',url='https://ned.ipac.caltech.edu/byname?objname=Galaxy')],
        redshift_candidates=[dict(preferred=True,redshift=.073,kind='transient_spectral')],
        review={'reviewer':'Private history'})
    before=deepcopy(r)
    html=verification_details(SimpleNamespace(),r)
    assert 'AstroNote' not in html and 'astronote' not in html and '0.073' not in html
    assert 'Private history' not in html and 'Metadata and review history' not in html
    assert 'NED positional candidate: Galaxy' in html and '2.50 arcsec' in html
    assert r==before


def test_ned_and_measured_host_emission_are_independent_and_not_assigned_to_neighbours():
    from efospec.typing_report import ned_cell,emission_cell,verification_details
    r=record(host_name='Galaxy')
    r['provenance']=[dict(kind='efospec_reduction',raw='/raw/a.fits')]
    r['host_candidates']=[dict(name='Galaxy',catalogue='NED',metadata={'z':.025,'zflag':'SUN'})]
    measurement=dict(raw='/raw/a.fits',ned={'candidate':None,'status':'ok'},
        spectral=dict(z_heliocentric=.024,z_heliocentric_error=.0001,wavelength_validated=True,status='candidate'))
    page=SimpleNamespace(redshift_records={'a.fits':measurement})
    assert '0.025' in ned_cell(r) and '0.024' not in ned_cell(r)
    assert '0.0240' in emission_cell(page,r,'Galaxy')
    assert emission_cell(page,r,'Neighbour')=='Not associated'
    html=verification_details(page,r,show_candidates=True)
    assert '<th>z (NED)</th>' in html and '<th>z (Host Emission)</th>' in html
    page.redshift_records={};page.previous_redshift_raws={'a.fits'}
    assert emission_cell(page,r,'Galaxy')=='Previous revision'
    assert '0.025' in ned_cell(r)
