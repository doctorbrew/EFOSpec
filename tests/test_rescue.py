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
