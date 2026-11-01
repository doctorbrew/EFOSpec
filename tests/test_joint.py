"""Recovery, degeneracy, and covariance of conditional SN/host extraction."""
import numpy as np
import pytest


def scene(seed=17, curved=True, curvature=120.):
    rng = np.random.default_rng(seed)
    x = np.arange(81.)
    sn = np.exp(-.5*((x-38.)/2.)**2)
    host = np.exp(-.5*((x-42.)/8.)**2)
    profiles = np.array([sn/sn.sum(), host/host.sum()])[:,None,:]
    profiles = np.repeat(profiles,60,axis=1)
    truth = np.array([np.linspace(1500,2200,60), np.linspace(2400,1800,60)]).T
    background = 100.+(curvature*((x-40)/40)**2 if curved else np.zeros_like(x))
    expected = np.einsum('ys,syx->yx',truth,profiles)+background
    variance = expected+8.**2
    data = expected+rng.normal(size=expected.shape)*np.sqrt(variance)
    sky = np.broadcast_to((x<15)|(x>68),data.shape)
    return data,variance,profiles,sky,truth


def test_joint_recovers_overlapping_point_and_extended_source_and_covariance():
    from efospec.joint import extract_joint
    data,var,profiles,sky,truth=scene()
    result=extract_joint(data,var,profiles,sky,background_degree=2)
    assert result['valid'].all()
    assert np.all(abs(np.median(result['flux']/truth,axis=0)-1)<.03)
    assert np.all(result['covariance'][:,0,1]<0)
    np.testing.assert_allclose(result['covariance'],result['covariance'].swapaxes(1,2))
    assert result['uncertainty_scope']=='conditional_on_fixed_profiles_and_selected_background'


@pytest.mark.parametrize('curved,expected',[(False,0),(True,2)])
def test_background_order_uses_held_out_sky_not_source_pixels(curved,expected):
    from efospec.joint import choose_background_degree
    data,var,_,sky,_=scene(curved=curved)
    result=choose_background_degree(data,var,sky)
    assert result['degree']==expected
    data[:,~sky[0]]=1e12
    assert choose_background_degree(data,var,sky)==result


def test_indistinguishable_components_do_not_become_two_measurements():
    from efospec.joint import extract_joint
    data,var,p,sky,_=scene()
    p[1]=p[0]
    result=extract_joint(data,var,p,sky,background_degree=1)
    assert not result['valid'].any()
    assert np.isnan(result['flux']).all()
    assert set(result['flags'])=={'degenerate_profiles'}


def test_formal_flux_uncertainty_predicts_noise_scatter():
    from efospec.joint import extract_joint
    residuals=[]
    for seed in range(12):
        data,var,p,sky,truth=scene(seed)
        r=extract_joint(data,var,p,sky,background_degree=2)
        sigma=np.sqrt(np.diagonal(r['covariance'],axis1=1,axis2=2))
        residuals.extend(((r['flux']-truth)/sigma).tolist())
    z=np.array(residuals)
    assert np.all(abs(z.mean(axis=0))<.12)
    assert np.all(abs(z.std(axis=0)-1)<.12)


def test_bad_inputs_and_missing_background_are_rejected():
    from efospec.joint import extract_joint
    data,var,p,sky,_=scene()
    with pytest.raises(ValueError,match='background'):
        extract_joint(data,var,p,np.zeros_like(sky),background_degree=2)
    with pytest.raises(ValueError,match='profile'):
        extract_joint(data,var,-p,sky,background_degree=1)
    with pytest.raises(ValueError,match='degree'):
        extract_joint(data,var,p,sky,background_degree=7)


def test_weak_curvature_is_reported_as_ambiguous_not_proven_flat():
    from efospec.joint import choose_background_degree
    data,var,_,sky,_=scene(curvature=30.)
    result=choose_background_degree(data,var,sky)
    assert result['degree']==0
    assert 2 in result['admissible_degrees']
    assert result['background_model_uncertain']


def test_severe_profile_mismatch_cannot_be_hidden_by_rejecting_the_source():
    from efospec.joint import extract_joint
    x=np.arange(81.)
    actual=np.exp(-.5*((x-40)/5)**2);actual/=actual.sum()
    wrong=np.exp(-.5*((x-40)/1.5)**2)
    data=np.broadcast_to(100+actual*1e6,(30,81)).copy()
    variance=np.full_like(data,100.)
    sky=np.broadcast_to((x<20)|(x>60),data.shape)
    profiles=np.broadcast_to(wrong,(1,30,81))
    result=extract_joint(data,variance,profiles,sky,background_degree=0)
    assert not result['valid'].any()
    assert set(result['flags'])=={'unmodelled_structure'}
