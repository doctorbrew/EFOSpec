import numpy as np
import pytest

from efospec.joint_validation import synthetic_validation
from test_revisions import saved_exposure


def test_conditional_benchmark_recovers_flux_and_reports_mismatch_limits():
    report=synthetic_validation()
    assert report['conditional_tests_passed']
    assert len(report['matched_cases'])==12
    assert report['identical_profiles_rejected']
    assert not report['science_validated']
    assert len(report['mismatch_cases'])==4
    # Imperfect morphology is not silently filtered out of the validation report.
    assert any(c['valid_fraction']<.9 or np.max(np.abs(c['mean_pull']))>.5
               for c in report['mismatch_cases'])
    assert {c['host_to_sn_width'] for c in report['matched_cases']}=={1.,3.}
    with pytest.raises(ValueError,match='64'):
        synthetic_validation(rows=8)


def test_observed_diagnostics_preserve_inputs_and_keep_profile_sensitivity(saved_exposure):
    from efospec.revisions import Exposure
    from efospec.joint_validation import observed_injections,observed_sensitivity
    from test_joint_revisions import recipe_for
    run,reference,_=saved_exposure;e=Exposure(run,'test_f.fits',reference)
    before=e.context.data.copy();hashes=dict(e.hashes)
    e.images['sky_input_mask']=np.zeros(e.context.data.shape,bool)
    with pytest.raises(ValueError,match='No common'):observed_injections(e)
    e.images['sky_input_mask'][:,:35]=True
    report=observed_injections(e,trials=2)
    assert len(report['trials'])==2 and report['input_sha256']==hashes
    assert report['raw_spatial_band'][1]-report['raw_spatial_band'][0]==35
    result=observed_sensitivity(e,recipe_for(e))
    assert len(result['variants'])==7
    assert result['variants'][0]['status']=='fit'
    np.testing.assert_allclose(result['variants'][0]['relative_integrated_change'],0,atol=1e-10)
    assert all(v.get('reason') for v in result['variants'] if v['status']=='rejected')
    assert any(v['status']=='rejected' or abs(v['relative_integrated_change'][1])>.01
               for v in result['variants'])
    np.testing.assert_array_equal(e.context.data,before)
    assert Exposure(run,'test_f.fits',reference).hashes==hashes


def test_validation_exports_machine_record_and_publication_figures(tmp_path):
    from efospec.joint_validation import save_validation
    import json
    from PIL import Image
    output=tmp_path/'validation'
    report=save_validation(output)
    assert json.loads((output/'validation.json').read_text())==report
    jpg,=output.glob('FitQC_*.jpg')
    assert jpg.with_suffix('.pdf').is_file()
    with Image.open(jpg) as image:assert image.info['dpi']==(300,300)
    with pytest.raises(FileExistsError):save_validation(output)
