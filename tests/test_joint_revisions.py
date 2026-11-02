import json
import numpy as np
import pytest
from astropy.io import fits
from test_revisions import saved_exposure


def recipe_for(exposure):
    r=exposure.default_recipe();r.update(schema_version=2,engine_version='efospec-joint-1',source_mode='manual',background_degree='auto')
    r['objects']=[dict(id=i,label=i,kind='point',spec=80.,spat=299.+x,fwhm=4.,radius=7.) for i,x in [('primary',48.),('host',98.)]]
    r['sky']={'mode':'regions','include':[[300,325],[421,438]],'exclude':[]}
    return r


def test_joint_revision_exports_covariance_and_replays(saved_exposure,tmp_path):
    from efospec.revisions import Exposure
    from efospec.joint_revisions import reextract_joint
    run,reference,truth=saved_exposure;e=Exposure(run,'test_f.fits',reference);r=recipe_for(e)
    result=reextract_joint(run,'test_f.fits',r,tmp_path/'joint',reference,render_report=True)
    assert len(result['results'])==2
    assert result['report']['status']=='complete',(tmp_path/'joint/report-generation.log').read_text()
    with np.load(tmp_path/'joint/native/joint-covariance.npz') as n:
        assert n['covariance'].shape==(160,2,2)
        assert np.all(n['fit_flags'][n['fit_valid']]=='ok')
        assert np.nanmedian(n['flux'][0]/truth['primary'])==pytest.approx(1,abs=.05)
    with fits.open(tmp_path/'joint/products/test_f.fits') as h:
        assert h[0].header['EXTRACT']=='JOINTFIX'
        assert h['VALID'].data[0].any()
        assert 'PypeIt sky, trace, optimal' not in str(h[0].header['HISTORY'])
    assert fits.getheader(result['results'][0]['native_spec1d'])['EXTRACT']=='JOINTFIX'
    # Same original detector pixels, new immutable outputs.
    fresh=Exposure(tmp_path/'joint','test_f.fits',reference)
    np.testing.assert_array_equal(fresh.context.data,e.context.data)
    replay=reextract_joint(run,'test_f.fits',r,tmp_path/'replay',reference,render_report=False)
    np.testing.assert_array_equal(fits.getdata(replay['results'][0]['product']),fits.getdata(result['results'][0]['product']))


def test_joint_validation_does_not_relax_point_engine(saved_exposure):
    from efospec.revisions import Exposure
    from efospec.joint_revisions import validate_joint_recipe
    from efospec.recipes import validate_recipe
    run,reference,_=saved_exposure;e=Exposure(run,'test_f.fits',reference);r=recipe_for(e)
    r['objects'][1]['spat']=r['objects'][0]['spat']+5
    assert validate_joint_recipe(r,e.window,e.hashes)['schema_version']==2
    r.pop('background_degree');r.update(schema_version=1,engine_version='1.14.0')
    with pytest.raises(ValueError,match='separated'):validate_recipe(r,e.window,e.hashes)


def test_joint_recipe_rejects_unsafe_companion_id(saved_exposure):
    from efospec.revisions import Exposure
    from efospec.joint_revisions import validate_joint_recipe
    run,reference,_=saved_exposure;e=Exposure(run,'test_f.fits',reference)
    r=recipe_for(e);r['objects'][1]['id']='../host'
    with pytest.raises(ValueError,match='simple identifiers'):validate_joint_recipe(r,e.window,e.hashes)
