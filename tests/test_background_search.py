import numpy as np
import pytest
from efospec.background_search import search


def fixture():
    rng=np.random.default_rng(123)
    ny,nx=90,100;x=np.arange(nx)
    data=100+.015*(x-50)**2+80*np.exp(-.5*((x-50)/2)**2)+rng.normal(0,1,(ny,nx))
    wave=np.broadcast_to(np.arange(ny)[:,None]+5000.,data.shape)
    recipe={'objects':[{'radius':6.,'fwhm':4.7}], 'sky':{'include':[[22,37],[63,78]],'exclude':[],'sigma_clip':4.}}
    return data,np.ones_like(data),wave,np.full(ny,50.),recipe,0


def test_search_preserves_core_and_recovers_curved_background():
    args=fixture();recipe,fit,record=search(*args)
    assert len(record['trials'])==6
    assert not fit['input_mask'][:,44:57].any()
    assert abs(np.median(fit['sky'][:,50])-100)<1
    assert fit['valid_rows'].all()
    assert recipe['objects']==args[4]['objects']
    assert args[4]['sky']['include']==[[22,37],[63,78]]
    assert all(np.isfinite(t['holdout_mean_square']) for t in record['trials'])


def test_search_refuses_unbounded_trials():
    with pytest.raises(ValueError,match='five pixels'):
        search(*fixture(),offsets=(-20,0,20))
