"""Catalogue associations, reference frames, and honest table statuses."""
import json
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from efospec.redshift_run import ned_candidate,heliocentric
from efospec.redshift_report import redshift_cells


def test_failed_science_gets_one_catalogue_search_and_no_false_nondetection(tmp_path):
    from efospec.redshift_run import catalogue_only_sources
    frames=[dict(path=str(tmp_path/name),sha256=name,role=role,metadata={'OBJECT':name})
            for name,role in [('failed','science'),('recovered','science'),('standard','standard_candidate')]]
    (tmp_path/'inputs.json').write_text(json.dumps({'frames':frames}))
    failures=[dict(path=f['path'],error='Wavelength failed') for f in frames]
    failures.append(dict(path=frames[0]['path'],error='Trace failed'))
    selected=[(tmp_path,dict(raw=frames[1]['path']))]
    result=catalogue_only_sources([(tmp_path,dict(errors=failures))],selected)
    assert len(result)==1 and result[0]['object']=='failed'
    assert result[0]['reasons']==['Wavelength failed','Trace failed']
    cells=redshift_cells(dict(raw=frames[0]['path'],ned=dict(status='ok',candidate=None),
                            spectral=dict(status='reduction_unavailable')))
    assert 'No galaxy within 30 arcsec' in cells[0]
    assert 'Not measured: reduction failed' in cells[1]
    assert 'No Host Lines' not in cells[1]


def test_review_counts_are_searchable_without_promoting_wavelengths(tmp_path):
    from efospec.redshift_run import selected_science
    from efospec.native_sky import wavelength_accepted
    raw=str(tmp_path/'science.fits')
    (tmp_path/'inputs.json').write_text(json.dumps({'frames':[dict(path=raw,role='science')]}))
    counts=dict(raw=raw,raw_sha256='rawhash',product='counts.fits',images='images.npz',
                product_sha256={'images.npz':'imagehash'},setup={'grism':'Gr13'},
                sky_flexure=dict(status='unvalidated',held_out_6363_pass=False,lines=[]))
    run=dict(results=[],review_counts=[counts])
    selected,_=selected_science([(tmp_path,run)],[])
    assert len(selected)==1 and selected[0][1]['evidence_kind']=='review_counts'
    assert not wavelength_accepted(selected[0][1]['sky_flexure'])
    rescue=dict(results=[dict(counts,role='science',product='rescued-flux.fits')])
    selected,_=selected_science([(tmp_path,run),(tmp_path/'rescue',rescue)],[])
    assert len(selected)==1 and selected[0][1]['product']=='rescued-flux.fits'
    run['results']=[dict(counts,role='science',product='flux.fits')]
    selected,_=selected_science([(tmp_path,run)],[])
    assert len(selected)==1 and selected[0][1]['product']=='flux.fits'


def test_nearest_galaxy_without_z_never_borrows_farther_redshift(tmp_path,monkeypatch):
    centre=SkyCoord(10*u.deg,20*u.deg,frame='fk5').icrs
    def fetch(catalogue,point,radius,directory,timeout):
        directory.mkdir()
        result=dict(status='ok',rows=[dict(name='nearest',ra=centre.ra.deg,dec=centre.dec.deg,
            galaxy_candidate=True,metadata=dict(z=None,zflag='')),
            dict(name='farther',ra=centre.ra.deg+.002,dec=centre.dec.deg,
            galaxy_candidate=True,metadata=dict(z=.2,zflag='SUN'))])
        (directory/'NED.json').write_text(json.dumps(result));return result
    monkeypatch.setattr('efospec.field_catalogues.fetch_catalogue',fetch)
    r=ned_candidate(dict(RA=10.,DEC=20.),tmp_path/'catalogue')
    assert r['candidate']['name']=='nearest' and r['candidate']['metadata']['z'] is None
    assert len(r['candidates'])==2
    cells=redshift_cells(dict(ned=r,spectral=dict(status='no_reliable_line_system'),raw='raw.fits'))
    assert 'no catalogued redshift' in cells[0] and '0.2' not in cells[0]
    assert 'Insufficient matching lines' in cells[1]


def test_heliocentric_correction_is_multiplicative(monkeypatch):
    monkeypatch.setattr(SkyCoord,'radial_velocity_correction',lambda *a,**kw:30*u.km/u.s)
    r=heliocentric(.2,dict(RA=10.,DEC=20.,**{'ESO TEL GEOLON':-70.,'ESO TEL GEOLAT':-29.,
        'ESO TEL GEOELEV':2377.,'MJD-OBS':61000.,'EXPTIME':1000.}))
    assert r['z_heliocentric']==pytest.approx(1.2*(1+30/299792.458)-1,abs=1e-12)
    assert r['mid_exposure_mjd']==pytest.approx(61000+500/86400)


def test_provisional_spectral_and_photometric_catalogue_statuses_are_separate():
    r=dict(raw='science.fits',ned=dict(candidate=dict(name='galaxy',metadata=dict(z=.074716,zflag='PUN'),
        separation_arcsec=6.1)),spectral=dict(z_heliocentric=.023834,wavelength_validated=False,status='provisional_wavelength'))
    ned,spectral=redshift_cells(r)
    assert 'photometric' in ned and '0.074716' in ned and 'candidate host' in ned
    assert '0.0238' in spectral and 'provisional wavelength' in spectral
    assert redshift_cells(None,standard=True)==['—','—']


def test_host_nondetection_label_does_not_hide_unidentified_lines():
    row=dict(raw='science.fits',ned=dict(candidate=None,status='ok'))
    cell=redshift_cells(dict(row,spectral=dict(status='no_host_lines')))[1]
    assert 'No Host Lines Found' in cell
    cell=redshift_cells(dict(row,spectral=dict(status='no_reliable_line_system')))[1]
    assert 'Insufficient matching lines' in cell and 'No Host Lines Found' not in cell


def test_redshifts_from_previous_reduction_are_not_labelled_never_measured(tmp_path):
    from efospec.epoch_report import EpochPage
    from efospec.redshift_report import load_redshifts
    from efospec.inventory import sha256
    root=tmp_path/'2026-10-28';run=root/'nightly/new/reduction';run.mkdir(parents=True)
    (run/'run.json').write_text('{}')
    qc=root/'QC';qc.mkdir()
    manifest=qc/'old.json';manifest.write_text(json.dumps(dict(night=root.name,
        parent_run_sha256={'old/run.json':'previous'},results=[dict(raw='/raw/old-science.fits')])))
    (qc/'redshift-current.json').write_text(json.dumps(dict(night=root.name,path='QC/old.json',sha256=sha256(manifest))))
    page=EpochPage(root)
    assert load_redshifts(page,run)=={}
    assert page.redshift_status=='previous_revision'
    assert page.previous_redshift_raws=={'old-science.fits'}
    assert redshift_cells(None,previous_revision=True)==['Previous revision','Previous revision']
    assert redshift_cells(None,previous_revision=True,standard=True)==['—','—']


def test_dated_revision_redshift_paths_are_confined(tmp_path):
    from efospec.redshift_report import evidence_inside_night
    root=tmp_path/'night'
    assert evidence_inside_night(root/'QC/new/redshifts.json',root)
    assert evidence_inside_night(root/'nightly/revision/QC/new/redshifts.json',root)
    assert not evidence_inside_night(root/'nightly/revision/reduction/run.json',root)
    assert not evidence_inside_night(root/'QC/../../outside.json',root)


def test_redshift_provenance_survives_folder_rename_but_rejects_changed_run(tmp_path):
    from efospec.epoch_report import EpochPage
    from efospec.redshift_report import load_redshifts
    from efospec.inventory import sha256
    old = tmp_path/'runs/2026-10-28/efosc'
    run = old/'nightly/revision/reduction'
    run.mkdir(parents=True)
    (run/'run.json').write_text('{}')
    qc = old/'QC';qc.mkdir()
    manifest = qc/'redshifts.json'
    manifest.write_text(json.dumps(dict(night='2026-10-28', results=[],
        parent_run_sha256={str(run/'run.json'): sha256(run/'run.json')})))
    (qc/'redshift-current.json').write_text(json.dumps(dict(night='2026-10-28',
        path='QC/redshifts.json', sha256=sha256(manifest))))
    new = old.with_name('efospec')
    old.rename(new);old.symlink_to('efospec', target_is_directory=True)
    page = EpochPage(new)
    load_redshifts(page, run.resolve())
    assert page.redshift_status == 'current'
    (run/'run.json').write_text('{"changed": true}')
    load_redshifts(page, run.resolve())
    assert page.redshift_status == 'previous_revision'


def test_redshift_uses_selected_manual_once_instead_of_main_and_rescue(tmp_path):
    from efospec.redshift_run import selected_science
    row=dict(raw=str(tmp_path/'science.fits'),raw_sha256='unchanged',role='science')
    folders=[tmp_path/name for name in ['main','manual','rescue']]
    runs=[(p,dict(results=[dict(row,product=str(p/'flux.fits'))])) for p in folders]
    selected,superseded=selected_science(runs,[folders[1]])
    assert len(selected)==1 and selected[0][0]==folders[1]
    assert {r['product'] for r in superseded}=={str(folders[i]/'flux.fits') for i in [0,2]}


@pytest.mark.parametrize('failure',['hash','priority','filename'])
def test_redshift_selection_rejects_ambiguous_inputs(tmp_path,failure):
    from efospec.redshift_run import selected_science
    row=dict(raw=str(tmp_path/'science.fits'),raw_sha256='unchanged',role='science',product='flux.fits')
    other=dict(row)
    if failure=='hash':other['raw_sha256']='changed'
    if failure=='filename':other['raw']=str(tmp_path/'elsewhere/science.fits')
    folders=[tmp_path/'main',tmp_path/'manual']
    manuals=folders if failure=='priority' else folders[1:]
    with pytest.raises(ValueError,match={'hash':'conflicting raw hashes','priority':'ambiguous science','filename':'output collision'}[failure]):
        selected_science([(folders[0],dict(results=[row])),(folders[1],dict(results=[other]))],manuals)


def test_catalogue_summary_uses_nearest_galaxy_without_borrowing_redshift():
    from efospec.catalogue_report import nearest_catalogue_redshift,field_redshifts
    from types import SimpleNamespace
    query=dict(status='ok',rows=[dict(name='near',ra=10.,dec=20.,galaxy_candidate=True,metadata=dict(z=None,zflag='')),
        dict(name='far',ra=10.001,dec=20.,galaxy_candidate=True,metadata=dict(z=.2,zflag='S'))])
    field=dict(object='SN',target_position=dict(icrs_deg=[10.,20.]),science_raws=[dict(path='/data/science.fits')])
    label=nearest_catalogue_redshift(query,field)
    assert 'near' in label and 'no catalogued redshift' in label and '0.2' not in label
    page=SimpleNamespace(redshift_records={'yes':dict(object='SN',raw='/data/science.fits'),
        'wrong':dict(object='SN',raw='/data/other.fits')})
    assert list(field_redshifts(page,field))==['yes']
