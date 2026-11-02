import numpy as np
import pytest
from efospec.polynomial_background import fit_background


def setup_scene(nrows=30):
    x=np.arange(141)+478
    trace=np.linspace(548.,550.,nrows)
    background=300.+.7*(x-548)+.025*(x-548)**2
    data=np.broadcast_to(background,(nrows,141)).copy()
    for row,t in enumerate(trace):data[row]+=500*np.exp(-.5*((x-t)/1.3)**2)
    return x,trace,background,data


def test_curved_background_recovery_masks_aperture_and_rejects_cosmic_ray():
    x,trace,bg,data=setup_scene()
    data[4,x==525]+=5000
    result=fit_background(data,np.full_like(data,25.),trace,x_origin=478,radius=7,
                          regions=[[520,535],[555,575]],degree=2)
    assert result['valid'].all()
    assert not result['fit_mask'][4,x==525].any()
    assert not (result['fit_mask']&(result['aperture_weights']>0)).any()
    np.testing.assert_allclose(result['model'][:,(x>535)&(x<555)],
                               np.broadcast_to(bg,data.shape)[:,(x>535)&(x<555)],atol=.001)
    truth=np.sum(result['aperture_weights']*(data-bg),axis=1)
    np.testing.assert_allclose(result['counts'],truth,atol=.01)


def test_boxcar_variance_includes_correlated_background_fit_uncertainty():
    _,trace,bg,data=setup_scene(600)
    trace[:]=549.
    mean=np.broadcast_to(bg,data.shape).copy()
    rng=np.random.default_rng(203)
    variance=np.full_like(mean,36.)
    observed=mean+rng.normal(0,6,mean.shape)
    result=fit_background(observed,variance,trace,x_origin=478,radius=7,
                          regions=[[520,535],[555,575]],degree=2,sigma_clip=8.)
    assert result['valid'].all()
    standardized=result['counts']/np.sqrt(result['variance'])
    assert abs(np.mean(standardized))<.15
    assert .9<np.std(standardized)<1.1
    marginal=np.sum(result['aperture_weights']**2*(variance+result['model_variance']),axis=1)
    assert np.all(result['variance']>marginal*1.2)


def test_missing_side_and_invalid_aperture_are_not_silently_extrapolated():
    x,trace,bg,data=setup_scene(3)
    good=np.ones_like(data,dtype=bool);good[0,x>550]=False;good[1,x==549]=False
    result=fit_background(data,np.full_like(data,25.),trace,x_origin=478,radius=7,
                          regions=[[520,535],[555,575]],good=good)
    assert result['valid'].tolist()==[False,False,True]
    assert np.isnan(result['counts'][:2]).all()
