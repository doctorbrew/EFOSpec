import numpy as np
import pytest


def test_bin_overlap_preserves_counts_and_propagates_squared_weights():
    from efospec.joint_revisions import rectify_counts
    wave=np.broadcast_to(np.arange(12.)[:,None]+5000,(12,2)).copy()
    data=np.full((12,2),10.);variance=np.full((12,2),4.)
    grid=wave[1:-1,0]+.5
    result=rectify_counts(data,variance,wave,np.ones_like(data,dtype=bool),grid)
    np.testing.assert_allclose(result['data'],10.)
    np.testing.assert_allclose(result['variance'],2.)
    assert result['valid'].all()
    assert result['spectral_covariance']=='adjacent output bins correlated; diagonal only'


def test_rectification_does_not_interpolate_over_bad_pixels():
    from efospec.joint_revisions import rectify_counts
    wave=np.broadcast_to(np.arange(12.)[:,None]+5000,(12,2)).copy()
    good=np.ones_like(wave,dtype=bool);good[4,0]=False
    result=rectify_counts(np.ones_like(wave),np.ones_like(wave),wave,good,wave[1:-1,0]+.5)
    assert not result['valid'][2:4,0].any()
    assert result['valid'][:,1].all()
