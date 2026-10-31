import json
from pathlib import Path
import shutil

import numpy as np
import pytest
from astropy.io import fits

from efospec.inventory import sha256
from test_revisions import saved_exposure


def test_sky_replay_recovers_the_original_selection_and_rejects_changed_defaults(saved_exposure):
    from efospec.sky_regions import recover_sky_selection
    from efospec import pypeit_adapter
    run,_,_=saved_exposure
    manifest=json.loads((run/'run.json').read_text());result=manifest['results'][0]
    manifest['source_sha256']={'pypeit_adapter.py':sha256(Path(pypeit_adapter.__file__))}
    (run/'run.json').write_text(json.dumps(manifest))
    assert recover_sky_selection(result,run)['status']=='already captured in reduction'
    images=run/'native/test_images.npz'
    with np.load(images) as saved:
        original=saved['sky_input_mask'].copy()
        arrays={key:saved[key] for key in saved.files if not key.startswith('sky_') and key!='onslit'}
    np.savez_compressed(images,**arrays)
    before=sha256(images)
    record=recover_sky_selection(result,run)
    assert record['candidate_positions_reproduced'] and record['input_files_unchanged']
    assert sha256(images)==before
    with np.load(record['sidecar']) as sidecar:
        np.testing.assert_array_equal(sidecar['sky_input_mask'],original)
    manifest['source_sha256']['pypeit_adapter.py']='0'*64
    (run/'run.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='defaults changed'):recover_sky_selection(result,run)


def test_legacy_comparison_requires_same_exposure_and_unique_content(saved_exposure,tmp_path):
    from efospec.qa import compare_legacy
    run,_,_=saved_exposure
    result=json.loads((run/'run.json').read_text())['results'][0]
    legacy=tmp_path/'legacy';legacy.mkdir()
    assert compare_legacy(result,legacy) is None
    product=Path(result['product']);old=legacy/product.name;shutil.copyfile(product,old)
    with fits.open(old,mode='update') as hdus:hdus[0].data/=2
    comparison=compare_legacy(result,legacy)
    assert comparison['ratio_p16_p50_p84']==pytest.approx([2,2,2])
    with fits.open(old,mode='update') as hdus:hdus[0].header['DATE-OBS']='2020-01-01T00:00:00'
    with pytest.raises(ValueError,match='exposure mismatch'):compare_legacy(result,legacy)
    (legacy/'duplicate').mkdir();shutil.copyfile(product,legacy/'duplicate'/product.name)
    with pytest.raises(ValueError,match='conflicting'):compare_legacy(result,legacy)


def test_validation_report_measures_standard_flux_without_changing_products(saved_exposure,tmp_path):
    from efospec.qa import make_report
    run,reference,_=saved_exposure
    manifest=json.loads((run/'run.json').read_text());result=manifest['results'][0]
    result['object']='SN2023xxj'
    result['sky_flexure'].update(held_out_6363_pass=True,held_out_6363_residual_angstrom=.1)
    (run/'run.json').write_text(json.dumps(manifest))
    legacy=tmp_path/'legacy';legacy.mkdir();shutil.copyfile(run/'products/test_f.fits',legacy/'test_f.fits')
    standards=tmp_path/'standards';(standards/'products').mkdir(parents=True);(standards/'native').mkdir()
    shutil.copyfile(run/'products/test_f.fits',standards/'products/test_f.fits')
    shutil.copyfile(run/'native/spec1d_test.fits',standards/'native/spec1d_test.fits')
    standard=dict(result,object='L745a');standard_manifest=dict(manifest,results=[standard])
    (standards/'run.json').write_text(json.dumps(standard_manifest))
    folder=reference/'standard/MAB';folder.mkdir()
    wavelength=np.linspace(3000,10000,100)
    expected=np.nanmedian(fits.getdata(run/'products/test_f.fits')[0])
    ab=-2.5*np.log10(expected*wavelength**2/2.99792458e18)-48.6
    np.savetxt(folder/'ml745a.dat',np.column_stack([wavelength,ab]))
    before=sha256(run/'products/test_f.fits')
    report=make_report(run,legacy,standards,reference)
    assert report['n_science']==1 and report['n_independent_sky_checks']==1
    assert report['standards'][0]['median_ratio']==pytest.approx(1.,abs=.01)
    assert report['comparisons']['SN2023xxj']['ratio_p16_p50_p84']==pytest.approx([1,1,1])
    assert sha256(run/'products/test_f.fits')==before
    for stem in ['night-overview','SN2023xxj-validation','standard-validation']:
        assert (run/(stem+'.pdf')).stat().st_size>1000
