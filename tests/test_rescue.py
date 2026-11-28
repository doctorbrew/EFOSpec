"""A provisional route cannot silently bypass data or background failures."""
from copy import deepcopy

import pytest

from efospec.inventory import sha256
from efospec.rescue import validate_counts


@pytest.fixture
def counts(tmp_path):
    frame=dict(path='/raw/science.fits',sha256='unchanged',setup={'grism':'Gr11'},metadata={'OBJECT':'SN-test'})
    record=dict(raw=frame['path'],raw_sha256=frame['sha256'],setup=frame['setup'],object='SN-test',
        flux_calibrated=False,science_validated=False,
        sky_flexure=dict(held_out_6363_pass=False,shift_angstrom=0.),
        background=dict(pypeit_exit_status=0,minimum_side_samples=5),product_sha256={})
    for key in ('native_spec1d','product','images','native_spec2d','ascii'):
        path=tmp_path/key;path.write_bytes(key.encode());record[key]=str(path)
        record['product_sha256'][str(path)]=sha256(path)
    calibration=tmp_path/'calibration';calibration.mkdir()
    manifest=calibration/'calibration.json';manifest.write_text('{}')
    record.update(calibration_directory=str(calibration),calibration_manifest_sha256=sha256(manifest))
    return record,frame


def test_auditable_unvalidated_counts_are_allowed(counts):
    validate_counts(*counts)


@pytest.mark.parametrize('field,value', [('pypeit_exit_status',1),('minimum_side_samples',4)])
def test_background_failure_cannot_be_promoted(counts,field,value):
    record,frame=counts;record['background'][field]=value
    with pytest.raises(ValueError,match='background'):validate_counts(record,frame)


@pytest.mark.parametrize('field,value', [('shift_angstrom',3.),('held_out_6363_pass',True)])
def test_rescue_requires_explicit_unchanged_arc_counts(counts,field,value):
    record,frame=counts;record['sky_flexure'][field]=value
    with pytest.raises(ValueError,match='unshifted'):validate_counts(record,frame)


def test_wrong_setup_is_rejected(counts):
    record,frame=counts;record=deepcopy(record);record['setup']['grism']='Gr13'
    with pytest.raises(ValueError,match='exposure/setup'):validate_counts(record,frame)


def test_missing_required_artifact_hash_is_rejected(counts):
    record,frame=counts;del record['product_sha256'][record['native_spec2d']]
    with pytest.raises(ValueError,match='required product hashes'):validate_counts(record,frame)


def test_pending_red_requires_opt_in_and_available_response():
    from efospec.rescue import rescue_candidates
    row=dict(raw='red.fits',object='SN-test',role='science',route='red',
             setup=dict(grism='Gr16',filter='OG530'),
             sky_flexure=dict(status='unvalidated'),selected_response={'path':'response.fits'})
    run=dict(errors=[],review_counts=[row])
    assert rescue_candidates(run)=={}
    assert rescue_candidates(run,include_pending_red=True)['red.fits']['code']=='wavelength_validation_pending'
    del row['selected_response']
    assert rescue_candidates(run,include_pending_red=True)=={}


def test_pending_red_cannot_promote_standards_or_other_routes():
    from efospec.rescue import rescue_candidates
    for role,route in [('standard_candidate','red'),('science','optical')]:
        row=dict(raw='other.fits',object='other',role=role,route=route,
                 setup=dict(grism='Gr16',filter='OG530'),
                 sky_flexure=dict(status='unvalidated'),selected_response={'path':'response.fits'})
        assert rescue_candidates(dict(errors=[],review_counts=[row]),include_pending_red=True)=={}


def test_standard_export_requires_both_opt_ins_and_available_response():
    from efospec.rescue import rescue_candidates
    row=dict(raw='standard.fits',object='Feige110',role='standard_candidate',route='red',
             setup=dict(grism='Gr16',filter='OG530'),
             sky_flexure=dict(status='unvalidated'),selected_response={'path':'response.fits'})
    run=dict(errors=[],review_counts=[row])
    assert rescue_candidates(run,include_standards=True)=={}
    assert 'standard.fits' in rescue_candidates(run,include_pending_red=True,include_standards=True)
    del row['selected_response']
    assert rescue_candidates(run,include_pending_red=True,include_standards=True)=={}


def test_confirm_saved_aperture_preserves_identity_and_original_record():
    from efospec.rescue import confirmed_selection
    record=dict(selection=dict(identity_confirmed=False,candidates=[dict(name='trace1')]))
    selected=confirmed_selection(record,'trace1',confirm_saved_source='trace1')
    assert selected['aperture_review']['candidate']=='C1'
    assert selected['identity_confirmed'] is False
    assert 'aperture_review' not in record['selection']


@pytest.mark.parametrize('names,actual,requested', [(['trace1'],'trace1','trace2'),
    (['trace2'],'trace1','trace1'), (['trace1','trace2'],'trace1','trace1')])
def test_confirm_saved_aperture_rejects_mismatched_or_ambiguous_source(names,actual,requested):
    from efospec.rescue import confirmed_selection
    record=dict(selection=dict(candidates=[dict(name=n) for n in names]))
    with pytest.raises(ValueError,match='single saved extracted source'):
        confirmed_selection(record,actual,confirm_saved_source=requested)
